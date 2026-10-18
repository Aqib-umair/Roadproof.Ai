"""Optional real local YOLO inference. No scores are fabricated."""
from pathlib import Path
from io import BytesIO
from datetime import datetime, timezone
from time import perf_counter

from PIL import Image

PLACEHOLDER = "AI detection module not connected — demonstration interface."


def weights_path():
    from .settings import setting
    value = setting("ROADPROOF_YOLO_WEIGHTS", "")
    return Path(value) if value and Path(value).is_file() else None


def analyze(raw, confidence=.35):
    from .analysis import photo_profile
    if not .05 <= confidence <= .95:
        raise ValueError("Choose a detection confidence threshold between 5% and 95%.")
    started = perf_counter()
    profile = photo_profile(raw)
    weights = weights_path()
    if weights is None:
        return {"status": PLACEHOLDER, "model": "Not connected", "detections": [],"image_info":profile,"connected":False}
    if weights.suffix.lower() == ".onnx":
        from .onnx_detector import analyze_onnx
        result = analyze_onnx(raw,weights,confidence)
    else:
        result = analyze_pt(raw,weights,confidence)
    count = len(result["detections"])
    result.update(image_info=profile,connected=True,confidence_threshold=confidence,
                  elapsed_seconds=round(perf_counter()-started,2),
                  ran_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  status=f"Local analysis: {count} pothole candidate(s) at {confidence:.0%} threshold. Human review required.")
    return result


def analyze_pt(raw,weights,confidence):
    # Import only after an operator supplies local weights; never download a model.
    from ultralytics import YOLO
    model = YOLO(str(weights))
    result = model.predict(Image.open(BytesIO(raw)).convert("RGB"), conf=confidence, verbose=False)[0]
    detections = []
    for index,box in enumerate(result.boxes):
        polygon = result.masks.xy[index].tolist() if result.masks is not None else []
        detections.append({"class":result.names[int(box.cls.item())],
            "confidence":float(box.conf.item()),"bbox_px":box.xyxy[0].tolist(),"polygon_px":polygon})
    output = BytesIO()
    Image.fromarray(result.plot()[..., ::-1]).save(output, "JPEG")
    return {"status": "Local model inference completed; human review required.",
            "model": weights.name, "detections": detections, "annotated": output.getvalue()}
