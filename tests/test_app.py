"""Streamlit page and citizen-flow checks using a disposable database."""
import os
from pathlib import Path
import tempfile
import unittest
import secrets
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from roadproof.images import clean_image, road_illustration
from roadproof.database import Database


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ,{"ROADPROOF_DATA_DIR":self.temp.name,"ROADPROOF_BACKEND":"sqlite","SUPABASE_URL":"","SUPABASE_SECRET_KEY":"","ROADPROOF_YOLO_WEIGHTS":"","ROADPROOF_ADMIN_MODE":"password","ROADPROOF_ADMIN_PASSWORD":"temporary-test-only-password"})
        self.environment.start()
        self.app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/"app.py"),default_timeout=30)

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def test_all_pages_launch(self):
        for page in ["home","how","report","success","track","dashboard","verify","about"]:
            self.app.session_state["page"] = page
            self.app.run()
            self.assertFalse(self.app.exception, f"Page failed: {page}")

    def test_citizen_submission_and_tracking(self):
        self.app.session_state["page"] = "report"
        self.app.run()
        self.app.session_state["draft"].update(image=clean_image(road_illustration()),step=2)
        self.app.run()
        next(b for b in self.app.button if b.label == "Confirm this location").click().run()
        next(b for b in self.app.button if b.label == "Continue to analysis →").click().run()
        self.assertFalse(self.app.exception)
        next(b for b in self.app.button if b.label == "Continue to measurements →").click().run()
        next(b for b in self.app.button if b.label == "Review your report →").click().run()
        next(t for t in self.app.text_area if t.label == "Describe the road damage").set_value("Road damage near the road shoulder.")
        next(c for c in self.app.checkbox if c.label.startswith("I understand")).check().run()
        next(b for b in self.app.button if b.label == "Submit Report ↗").click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.session_state["page"],"success")
        self.assertIn("token",self.app.session_state["receipt"])
        # A new browser session using the saved receipt also verifies persistence.
        receipt = self.app.session_state["receipt"]
        self.app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/"app.py"),default_timeout=30)
        self.app.session_state["page"] = "success"
        self.app.session_state["receipt"] = receipt
        self.app.run()
        next(b for b in self.app.button if b.label == "View report →").click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.session_state["page"],"track")

    def test_admin_login_status_update_and_human_review(self):
        self.app.session_state["page"] = "dashboard"
        self.app.run()
        self.assertFalse(any(t.label == "Reason / progress update" for t in self.app.text_area))
        next(t for t in self.app.text_input if t.label == "Demo administrator password").set_value("temporary-test-only-password")
        next(b for b in self.app.button if b.label == "Unlock demo controls").click().run()
        self.assertFalse(self.app.exception)
        db = Database(Path(self.temp.name)/"roadproof.sqlite3")
        case = next(r for r in db.public_reports() if r["status"] == "Reported")
        next(s for s in self.app.selectbox if s.label == "Open case").select(case["id"]).run()
        next(t for t in self.app.text_area if t.label == "Reason / progress update").set_value("Administrator inspected this demo report.")
        next(b for b in self.app.button if b.label == "Save demo status").click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(db.get(case["id"])["status"],"Under Review")
        # Use a fresh authenticated page run to check the separate review screen.
        pending = next(r for r in db.public_reports() if r["status"] == "Verification Pending")
        import hashlib
        import time
        self.app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/"app.py"),default_timeout=30)
        self.app.session_state["page"] = "verify"
        self.app.session_state["verification_case"] = pending["id"]
        self.app.session_state["admin_fingerprint"] = hashlib.sha256(b"temporary-test-only-password").hexdigest()
        self.app.session_state["admin_until"] = time.time()+3600
        self.app.run()
        self.assertFalse(self.app.exception)
        next(t for t in self.app.text_area if t.label == "Reviewer notes / reason for decision").set_value("Both synthetic illustrations and the location have been reviewed.")
        next(r for r in self.app.radio if r.label == "Reviewer decision").set_value("Mark Verified")
        next(c for c in self.app.checkbox if c.label.startswith("I have personally")).check()
        next(b for b in self.app.button if b.label == "Record human decision").click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(db.get(pending["id"])["status"],"Verified and Closed")

    def create_citizen_case(self):
        db = Database(Path(self.temp.name)/"roadproof.sqlite3")
        image = db.get(db.public_reports()[0]["id"])["image_path"]
        token = secrets.token_urlsafe(32)
        report_id = db.create_report(token=token,lat=15.8,lon=78.0,location="New citizen report",
            description="New road damage submitted in the UI regression test.",image_path=image,ai_status="Not connected")
        return report_id,token

    def test_report_id_works_only_with_same_browser_receipt(self):
        self.app.session_state["page"] = "track"
        self.app.run()
        report_id,token = self.create_citizen_case()
        self.app.session_state["receipt"] = dict(id=report_id,token=token)
        self.app.text_input[0].set_value(report_id)
        next(b for b in self.app.button if b.label=="Find my report").click().run()
        self.assertFalse(self.app.exception)
        self.assertTrue(any(s.value=="Case timeline" for s in self.app.subheader))
        other = AppTest.from_file(str(Path(__file__).resolve().parents[1]/"app.py"),default_timeout=30)
        other.session_state["page"]="track"
        other.run()
        other.text_input[0].set_value(report_id)
        next(b for b in other.button if b.label=="Find my report").click().run()
        self.assertFalse(other.exception)
        self.assertTrue(any("That is a report ID" in warning.value for warning in other.warning))
        self.assertFalse(any(s.value=="Case timeline" for s in other.subheader))

    def test_full_tracking_link_and_clear_receipt_labels(self):
        self.app.session_state["page"]="track"
        self.app.run()
        report_id,token=self.create_citizen_case()
        self.app.text_input[0].set_value(f'http://localhost:8501/?page=track&token={token}')
        next(b for b in self.app.button if b.label=="Find my report").click().run()
        self.assertFalse(self.app.exception)
        self.assertTrue(any(s.value=="Case timeline" for s in self.app.subheader))
        receipt_app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/"app.py"),default_timeout=30)
        receipt_app.session_state["page"]="success"
        receipt_app.session_state["receipt"]={"id":report_id,"token":token}
        receipt_app.run()
        self.assertFalse(receipt_app.exception)
        self.assertTrue(any(block.value==token for block in receipt_app.code))
        self.assertTrue(any("**Private tracking token**" in block.value for block in receipt_app.markdown))
        self.app.session_state["receipt"]={"id":report_id,"token":token}
        self.app.session_state["my_reports"]={report_id:token}
        next(b for b in self.app.button if b.label=="Clear private tracking session").click().run()
        self.assertFalse(self.app.exception)
        for key in ["tracking_token","tracking_reference","my_reports","receipt"]:
            self.assertNotIn(key,self.app.session_state)
        self.assertIsNotNone(Database(Path(self.temp.name)/"roadproof.sqlite3").by_token(token))

    def test_dashboard_refresh_filters_and_protected_photos(self):
        self.app.session_state["page"]="dashboard"
        self.app.run()
        report_id,token=self.create_citizen_case()
        next(b for b in self.app.button if b.label=="Refresh reports").click().run()
        self.assertFalse(self.app.exception)
        frame=next(frame.value for frame in self.app.dataframe if "Report ID" in frame.value.columns)
        self.assertIn(report_id,frame["Report ID"].tolist())
        self.assertFalse(self.app.get("imgs"))
        next(t for t in self.app.text_input if t.label=="Demo administrator password").set_value("temporary-test-only-password")
        next(b for b in self.app.button if b.label=="Unlock demo controls").click().run()
        self.assertFalse(self.app.exception)
        self.assertTrue(self.app.get("imgs"))
        self.assertTrue(any(b.key==f'photo_review_{report_id}' for b in self.app.button))
        self.app.radio(key="record_scope").set_value("Synthetic samples").run()
        frame=next(frame.value for frame in self.app.dataframe if "Report ID" in frame.value.columns)
        self.assertNotIn(report_id,frame["Report ID"].tolist())
        next(b for b in self.app.button if b.label=="Clear dashboard filters").click().run()
        self.assertFalse(self.app.exception)
        frame=next(frame.value for frame in self.app.dataframe if "Report ID" in frame.value.columns)
        self.assertIn(report_id,frame["Report ID"].tolist())

    def test_open_demo_has_photos_and_controls_without_password(self):
        with patch.dict(os.environ,{"ROADPROOF_ADMIN_MODE":"demo"}):
            for page in ["dashboard","verify"]:
                self.app.session_state["page"]=page
                self.app.run()
                self.assertFalse(self.app.exception)
                self.assertFalse(any(t.label=="Demo administrator password" for t in self.app.text_input))
                self.assertFalse(any(b.label=="Unlock demo controls" for b in self.app.button))
                self.assertFalse(any(b.label=="Lock administrator controls" for b in self.app.button))
                self.assertTrue(self.app.get("imgs"))
            self.assertTrue(any(t.label=="Reviewer notes / reason for decision" for t in self.app.text_area))

    def test_analysis_button_refreshes_positive_and_empty_results(self):
        from roadproof.analysis import photo_profile
        from datetime import datetime,timezone
        raw=clean_image(road_illustration())
        model=Path(self.temp.name)/"fixture-model.onnx"
        model.write_bytes(b"test fixture; runtime is mocked")
        result={"model":"fixture-model.onnx","status":"Unit test result", "connected":True,
            "image_info":photo_profile(raw),"annotated":raw,"confidence_threshold":.35,
            "elapsed_seconds":.1,"ran_at":datetime.now(timezone.utc).isoformat(),
            "detections":[{"class":"pothole","confidence":.8,"bbox_px":[10,10,110,60],"area_px":5000,"polygon_px":[[10,10],[110,10],[110,60],[10,60]]}]}
        self.app.session_state["page"]="report"
        self.app.run()
        self.app.session_state["draft"].update(step=3,image=raw)
        with patch("roadproof.citizen.weights_path",return_value=model),patch("roadproof.citizen.analyze",return_value=result) as analyzer:
            self.app.run()
            self.assertFalse(self.app.exception)
            self.assertEqual(analyzer.call_count,1)
            self.assertTrue(any(m.label=="Pothole candidates" and m.value=="1" for m in self.app.metric))
            self.assertTrue(any(m.label=="Detected box width" and m.value=="100 px" for m in self.app.metric))
            next(b for b in self.app.button if b.key=="run_analysis").click().run()
            self.assertFalse(self.app.exception)
            self.assertEqual(analyzer.call_count,2)
            analyzer.return_value={**result,"detections":[]}
            next(b for b in self.app.button if b.key=="run_analysis").click().run()
            self.assertFalse(self.app.exception)
            self.assertEqual(analyzer.call_count,3)
            self.assertTrue(any(m.label=="Pothole candidates" and m.value=="0" for m in self.app.metric))
            self.assertFalse(any(m.label=="Detected box width" for m in self.app.metric))
            self.assertTrue(any("no pothole detected" in message.value for message in self.app.info))


if __name__ == "__main__":
    unittest.main()
