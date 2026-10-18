"""Measured image attributes and dimensions derived from actual detector output."""
from io import BytesIO
import math

from PIL import Image, ImageStat


def photo_profile(raw):
    with Image.open(BytesIO(raw)) as image:
        width,height = image.size
        gray = image.convert("L")
        stats = ImageStat.Stat(gray)
        brightness = stats.mean[0]
        contrast = stats.stddev[0]
        notes = []
        if brightness < 55:
            notes.append("This photograph is dark. A well-lit image may reveal more road detail.")
        if contrast < 18:
            notes.append("This photograph has little contrast. Include clear edges and the surrounding road.")
        if min(width,height) < 320:
            notes.append("The image is small. A higher-resolution photograph may help detection.")
        return {"width_px":width,"height_px":height,"format":image.format,
                "brightness_0_255":round(brightness,1),"contrast_stddev":round(contrast,1),
                "file_size_kb":round(len(raw)/1024,1),"quality_notes":notes}


def detection_parameters(detection, image_info):
    box = detection.get("bbox_px") or []
    if len(box)!=4 or not all(math.isfinite(float(v)) for v in box):
        return None
    width,height = image_info["width_px"],image_info["height_px"]
    x1,x2 = sorted(min(width,max(0,float(v))) for v in [box[0],box[2]])
    y1,y2 = sorted(min(height,max(0,float(v))) for v in [box[1],box[3]])
    area = detection.get("area_px")
    polygon = detection.get("polygon_px") or []
    if area is None and len(polygon)>=3:
        area = abs(sum(polygon[i][0]*polygon[(i+1)%len(polygon)][1]
             -polygon[(i+1)%len(polygon)][0]*polygon[i][1] for i in range(len(polygon))))/2
    area = min(width*height,max(0,float(area))) if area is not None else None
    return {"bbox_width_px":round(x2-x1,1),"bbox_height_px":round(y2-y1,1),
            "outline_area_px2":round(area,1) if area is not None else None,
            "image_coverage_percent":round(100*area/(width*height),2) if area is not None else None,
            "physical_length_cm":None,"physical_width_cm":None,"depth_cm":None}
