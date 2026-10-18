import io
import secrets
import tempfile
import unittest
import os
from unittest.mock import patch
from pathlib import Path

from PIL import Image

from roadproof.costs import estimate
from roadproof.database import Database, duplicate_pairs
from roadproof.images import MAX_BYTES, clean_image, road_illustration, save_image


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ,{"ROADPROOF_BACKEND":"sqlite","SUPABASE_URL":"","SUPABASE_SECRET_KEY":""})
        self.environment.start()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = Database(self.root / "test.sqlite3")
        self.before = save_image(road_illustration(), self.root / "images")
        self.token = secrets.token_urlsafe(32)
        self.id = self.create()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def create(self):
        return self.db.create_report(token=self.token, lat=15.8281, lon=78.0373,
            location="Test location",description="A pothole near the edge of the road.",
            image_path=self.before,ai_status="Not connected",email="private@example.test",consent=True)

    def progress(self):
        for status in ["Under Review", "Assigned", "Repair in Progress"]:
            self.db.update_status(self.id,status,"Test progress note",authorized=True)

    def pending(self):
        self.progress()
        after = save_image(road_illustration(True),self.root/"images")
        self.db.add_evidence(self.id,after,"Repair evidence test",authorized=True)
        for status in ["Repair Claimed Complete","Verification Pending"]:
            self.db.update_status(self.id,status,"Test repair claim",authorized=True)

    def test_private_tracking_and_public_redaction(self):
        self.assertEqual(self.db.by_token(self.token)["id"],self.id)
        self.assertIsNone(self.db.by_token("incorrect"))
        public = self.db.public_reports()[0]
        for field in ["token_hash","email","image_path","description"]:
            self.assertNotIn(field,public)
        with self.db.connect() as conn:
            stored = conn.execute("SELECT token_hash FROM reports").fetchone()[0]
        self.assertNotEqual(stored,self.token)
        self.assertEqual(self.create(),self.id)
        self.assertEqual(len(self.db.public_reports()),1)

    def test_protected_updates_and_required_evidence(self):
        with self.assertRaises(PermissionError):
            self.db.update_status(self.id,"Under Review","Attempt")
        with self.assertRaises(PermissionError):
            self.db.add_evidence(self.id,self.before,"Attempt")
        self.progress()
        with self.assertRaises(ValueError):
            self.db.update_status(self.id,"Repair Claimed Complete","No evidence",authorized=True)
        with self.assertRaises(ValueError):
            self.db.update_status(self.id,"Verified and Closed","Skip review",authorized=True)

    def test_human_verification_reopen_and_audit(self):
        self.pending()
        with self.assertRaises(PermissionError):
            self.db.review(self.id,"Mark Verified","Unauthorized",attested=True)
        with self.assertRaises(ValueError):
            self.db.review(self.id,"Mark Verified","Missing attestation",authorized=True)
        self.db.review(self.id,"Mark Verified","Evidence reviewed by human",authorized=True,attested=True)
        self.assertIsNotNone(self.db.get(self.id)["verified_at"])
        with self.assertRaises(ValueError):
            self.db.add_evidence(self.id,self.before,"Replace closed evidence",authorized=True)
        self.db.review(self.id,"Reopen Case","Further inspection required",authorized=True)
        report = self.db.get(self.id)
        self.assertEqual(report["status"],"Reopened")
        self.assertIsNone(report["verified_at"])
        events = self.db.history(self.id)
        self.assertEqual(events[-1]["action"],"Reopen Case")
        self.assertTrue(all(e["created_at"] and e["note"] for e in events))
        self.assertEqual(len(events),9)

    def test_concurrent_status_guard(self):
        self.db.update_status(self.id,"Under Review","Review",authorized=True)
        with self.assertRaises(ValueError):
            self.db.update_status(self.id,"Assigned","Stale update",authorized=True,expected_status="Reported")
        self.assertEqual(self.db.get(self.id)["status"],"Under Review")

    def test_request_evidence_and_feedback(self):
        self.pending()
        self.db.review(self.id,"Request More Evidence","Need a wider view",authorized=True)
        self.assertEqual(self.db.get(self.id)["status"],"Repair in Progress")
        with self.assertRaises(ValueError):
            self.db.feedback("wrong", "This feedback cannot be added")
        self.db.feedback(self.token,"Please inspect the shoulder too.")
        self.assertEqual(self.db.history(self.id)[-1]["action"],"Citizen feedback")

    def test_seed_counts_and_duplicate_suggestions(self):
        self.db.seed(self.root/"images")
        self.db.seed(self.root/"images")
        reports = self.db.public_reports()
        samples = [r for r in reports if r["synthetic"]]
        self.assertEqual(len(samples),6)
        self.assertEqual({r["status"] for r in samples},{"Reported","Under Review","Repair in Progress","Verification Pending","Verified and Closed","Reopened"})
        self.assertEqual(len(duplicate_pairs(samples)),1)

    def test_cost_constraints(self):
        result = estimate(100,100,10,8000,"Measured on site")
        self.assertAlmostEqual(result["volume_m3"],.1)
        self.assertEqual(result["amount"],920)
        for values in [(0,1,1,8000,"Measured on site"),(1,1,1,8000,"Visual estimate only"),(float("nan"),1,1,8000,"Measured on site")]:
            with self.assertRaises(ValueError):
                estimate(*values)

    def test_image_validation_and_metadata_removal(self):
        for value in [b"not an image",b"a"*(MAX_BYTES+1)]:
            with self.assertRaises(ValueError): clean_image(value)
        output = io.BytesIO()
        Image.new("RGB",(10,10)).save(output,"GIF")
        with self.assertRaises(ValueError): clean_image(output.getvalue())
        result = Image.open(io.BytesIO(clean_image(road_illustration())))
        self.assertEqual(result.format,"JPEG")
        self.assertFalse(result.getexif())


if __name__ == "__main__":
    unittest.main()
