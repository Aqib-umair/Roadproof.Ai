import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import unittest
from unittest.mock import MagicMock, patch

from roadproof.cloud import PUBLIC_FIELDS, PrivateStorage, SupabaseDatabase, normalize
from roadproof.settings import BackendSettings, backend_settings


class CloudAdapterTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.settings = BackendSettings("supabase","https://example.supabase.co","not-a-real-secret","roadproof-evidence")
        self.db = SupabaseDatabase(self.settings,client=self.client)

    def test_report_submission_hashes_token_and_restricts_media(self):
        token = secrets.token_urlsafe(32)
        self.client.rpc.return_value.execute.return_value.data = "RP-0123456789"
        payload = dict(token=token,lat=15.8,lon=78.0,location="Test road",
            description="Harmless test case description.",image_path="supabase://roadproof-evidence/evidence/"+"a"*32+".jpg",
            ai_status="Not connected",email="private@example.test",consent=False)
        self.assertEqual(self.db.create_report(**payload),"RP-0123456789")
        name,arguments = self.client.rpc.call_args.args
        self.assertEqual(name,"rp_create_report")
        record = arguments["p_report"]
        self.assertNotIn(token,json.dumps(record))
        self.assertEqual(record["token_hash"],hashlib.sha256(token.encode()).hexdigest())
        self.assertEqual(record["email"],"")
        with self.assertRaises(ValueError):
            self.db.create_report(**(payload|{"image_path":"/local/photo.jpg"}))

    def test_unauthorized_mutations_never_reach_supabase(self):
        with self.assertRaises(PermissionError): self.db.update_status("RP-0123456789","Under Review","Test")
        with self.assertRaises(PermissionError): self.db.add_evidence("RP-0123456789","path","Test")
        with self.assertRaises(PermissionError): self.db.review("RP-0123456789","Mark Verified","Test",attested=True)
        self.client.rpc.assert_not_called()

    def test_review_preserves_attestation_and_stale_status_guard(self):
        self.db.review("RP-0123456789","Mark Verified","Reviewed",authorized=True,attested=True,expected_status="Verification Pending")
        name,arguments = self.client.rpc.call_args.args
        self.assertEqual(name,"rp_update_case")
        self.assertTrue(arguments["p_attested"])
        self.assertEqual(arguments["p_expected"],"Verification Pending")

    def test_public_query_redaction_and_pagination(self):
        query = self.client.table.return_value.select.return_value.order.return_value
        query.range.return_value.execute.side_effect = [MagicMock(data=[{"id":f"RP-{i:010X}"} for i in range(500)]),MagicMock(data=[{"id":"RP-9999999999"}])]
        rows = self.db.public_reports()
        self.assertEqual(len(rows),501)
        self.client.table.return_value.select.assert_called_with(PUBLIC_FIELDS)
        for field in ["token_hash","email","image_path","description"]:
            self.assertNotIn(field,PUBLIC_FIELDS.split(","))
        self.assertEqual(query.range.call_args_list[1].args,(500,999))

    def test_errors_do_not_expose_provider_details(self):
        self.client.rpc.return_value.execute.side_effect = RuntimeError("sensitive-provider-detail-and-key")
        with self.assertRaises(OSError) as raised:
            self.db.update_status("RP-0123456789","Under Review","Review",authorized=True)
        self.assertNotIn("sensitive-provider",str(raised.exception))

    def test_private_bucket_and_path_scope(self):
        storage = PrivateStorage(self.settings,client=self.client)
        reference = storage.upload(b"already-cleaned-fixture")
        self.assertTrue(reference.startswith("supabase://roadproof-evidence/evidence/"))
        self.client.storage.from_.assert_called_with("roadproof-evidence")
        self.assertEqual(self.client.storage.from_.return_value.upload.call_args.kwargs["file_options"]["upsert"],"false")
        for reference in ["https://example.com/photo.jpg","supabase://other-bucket/a.jpg","supabase://roadproof-evidence/../other.jpg"]:
            with self.assertRaises(ValueError): storage.download(reference)

    def test_private_image_read_retries_one_transient_failure(self):
        storage=PrivateStorage(self.settings,client=self.client)
        download=self.client.storage.from_.return_value.download
        download.side_effect=[OSError("Temporary connection interruption"),b"image bytes"]
        result=storage.download("supabase://roadproof-evidence/evidence/example.jpg")
        self.assertEqual(result,b"image bytes")
        self.assertEqual(download.call_count,2)

    def test_json_normalization_and_configuration_fail_closed(self):
        self.assertEqual(json.loads(normalize({"analysis_json":[{"class":"pothole"}]})["analysis_json"]),[{"class":"pothole"}])
        with patch.dict(os.environ,{"ROADPROOF_BACKEND":"supabase","SUPABASE_URL":"https://example.supabase.co","SUPABASE_SECRET_KEY":""}):
            with self.assertRaises(ValueError): backend_settings()


@unittest.skipUnless(importlib.util.find_spec("cv2"),"Optional OpenCV dependency is not installed")
class CalibrationTests(unittest.TestCase):
    def test_reference_detection_and_missing_reference(self):
        from roadproof.calibration import find_marker,marker_png
        from roadproof.images import road_illustration
        self.assertEqual(find_marker(marker_png()).shape,(4,2))
        with self.assertRaises(ValueError): find_marker(road_illustration())

    def test_known_geometry_never_invents_depth(self):
        from roadproof.calibration import surface_extents
        result = surface_extents([[10,10],[210,10],[210,110],[10,110]],[[0,0],[100,0],[100,100],[0,100]],10)
        self.assertEqual(result["length_cm"],20)
        self.assertEqual(result["width_cm"],10)
        self.assertEqual(result["surface_area_cm2"],200)
        self.assertIsNone(result["depth_cm"])

    def test_perspective_geometry_and_rejected_scale(self):
        import cv2
        import numpy as np
        from roadproof.calibration import surface_extents
        marker = np.float32([[0,0],[100,0],[100,100],[0,100]])
        polygon = np.float32([[10,10],[210,10],[210,110],[10,110]])
        matrix = np.float32([[1,.1,20],[.1,1,30],[.0005,.0003,1]])
        projected_marker = cv2.perspectiveTransform(marker[None],matrix)[0]
        projected_polygon = cv2.perspectiveTransform(polygon[None],matrix)[0]
        result = surface_extents(projected_polygon,projected_marker,10)
        self.assertAlmostEqual(result["length_cm"],20,places=1)
        self.assertAlmostEqual(result["width_cm"],10,places=1)
        with self.assertRaises(ValueError): surface_extents(polygon,marker,0)
        with self.assertRaises(ValueError): surface_extents(polygon,[[0,0],[1,0],[1,1],[0,1]],10)


if __name__ == "__main__":
    unittest.main()
