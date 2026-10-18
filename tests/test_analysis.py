from io import BytesIO
import unittest

from PIL import Image

from roadproof.analysis import detection_parameters, photo_profile


class AnalysisParametersTests(unittest.TestCase):
    def test_dark_photo_has_real_attributes_and_quality_note(self):
        raw = BytesIO()
        Image.new("RGB",(568,320),(30,30,30)).save(raw,"JPEG")
        result = photo_profile(raw.getvalue())
        self.assertEqual((result["width_px"],result["height_px"]),(568,320))
        self.assertEqual(result["brightness_0_255"],30)
        self.assertTrue(any("dark" in note for note in result["quality_notes"]))

    def test_detected_pixel_parameters_do_not_invent_physical_measurements(self):
        detection={"bbox_px":[10,20,110,70],"polygon_px":[[10,20],[110,20],[110,70],[10,70]]}
        result=detection_parameters(detection,{"width_px":200,"height_px":100})
        self.assertEqual(result["bbox_width_px"],100)
        self.assertEqual(result["bbox_height_px"],50)
        self.assertEqual(result["outline_area_px2"],5000)
        self.assertEqual(result["image_coverage_percent"],25)
        for key in ["physical_length_cm","physical_width_cm","depth_cm"]:
            self.assertIsNone(result[key])

    def test_explicit_segmented_area_and_invalid_boxes(self):
        result=detection_parameters({"bbox_px":[0,0,100,100],"area_px":1800},{"width_px":100,"height_px":100})
        self.assertEqual(result["image_coverage_percent"],18)
        self.assertIsNone(detection_parameters({"bbox_px":[0,0,float("nan"),100]},{"width_px":100,"height_px":100}))


if __name__=="__main__":
    unittest.main()
