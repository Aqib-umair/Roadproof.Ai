"""Approximate surface extents from a known square, never single-photo depth."""
from io import BytesIO
import math

import numpy as np
from PIL import Image

DISCLAIMER = ("Approximate road-plane extents, not surveyed dimensions. The marker must be flat on the same road plane, "
              "close to the damage, with all corners visible. Lens distortion, slopes, perspective, the detected outline "
              "and placement affect accuracy. Depth is not available from this calculation.")


def marker_png():
    import cv2
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker = cv2.aruco.generateImageMarker(dictionary,0,600)
    # A white quiet zone is required around the black square for reliable detection.
    canvas = np.full((840,840),255,dtype=np.uint8)
    canvas[120:720,120:720] = marker
    output = BytesIO()
    Image.fromarray(canvas).save(output,"PNG")
    return output.getvalue()


def find_marker(raw):
    import cv2
    image = np.array(Image.open(BytesIO(raw)).convert("RGB"))
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))
    corners, ids, _ = detector.detectMarkers(image)
    matches = [] if ids is None else [i for i,v in enumerate(ids.flatten()) if v == 0]
    if len(matches) != 1:
        raise ValueError("Include exactly one RoadProof marker (DICT_4X4_50, ID 0), fully visible beside the damage.")
    points = np.asarray(corners[matches[0]],dtype=np.float32).reshape(4,2)
    edges = np.linalg.norm(np.roll(points,-1,axis=0)-points,axis=1)
    if edges.min() < 25 or edges.max()/edges.min() > 4:
        raise ValueError("The reference marker is too small or too oblique. Take a clearer, more overhead photograph.")
    return points


def surface_extents(polygon, marker_corners, side_cm):
    import cv2
    if not math.isfinite(float(side_cm)) or not 2 <= side_cm <= 100:
        raise ValueError("Enter the measured black-square side length, between 2 and 100 cm.")
    corners = np.asarray(marker_corners,dtype=np.float32).reshape(4,2)
    points = np.asarray(polygon,dtype=np.float32).reshape(-1,2)
    if len(points) < 3 or not np.isfinite(points).all() or not np.isfinite(corners).all():
        raise ValueError("A valid pothole segmentation outline and four reference corners are required.")
    if not cv2.isContourConvex(corners) or abs(cv2.contourArea(corners)) < 625:
        raise ValueError("The reference marker corners do not form a usable square projection.")
    target = np.array([[0,0],[side_cm,0],[side_cm,side_cm],[0,side_cm]],dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(corners,target)
    homogeneous = np.c_[points,np.ones(len(points))] @ matrix.T
    denominator = homogeneous[:,2]
    if np.any(abs(denominator) < 1e-5) or np.any(denominator*denominator[0] <= 0):
        raise ValueError("The outline crosses the estimated road-plane horizon; use a more overhead photograph.")
    projected = (homogeneous[:,:2]/denominator[:,None]).astype(np.float32)
    # Extrapolation far beyond a small marker is unstable. Require a nearby reference.
    if np.max(np.linalg.norm(projected-target.mean(axis=0),axis=1)) > side_cm*12:
        raise ValueError("The reference is too far from the outline for this prototype's measurement limit.")
    rectangle = cv2.minAreaRect(projected)
    width, length = sorted(rectangle[1])
    if not (0 < width <= length < 2000):
        raise ValueError("The estimated surface dimensions are unusable. Check the photograph and marker size.")
    return {"length_cm":round(length,1),"width_cm":round(width,1),"depth_cm":None,
            "surface_area_cm2":round(abs(cv2.contourArea(projected)),1),
            "method":"Reference marker estimate", "marker_side_cm":side_cm,
            "marker_corners_px":corners.tolist(),"disclaimer":DISCLAIMER}


def measure_detection(raw, detection, side_cm):
    polygon = detection.get("polygon_px")
    if not polygon:
        raise ValueError("This detection has no segmentation outline; a bounding box is not a damage measurement.")
    return surface_extents(polygon,find_marker(raw),side_cm)
