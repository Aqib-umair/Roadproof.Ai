"""CPU inference for non-NMS YOLOv8, one-class pothole segmentation exports."""
import ast
from functools import lru_cache
import hashlib
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw


@lru_cache(maxsize=2)
def load_session(path, modified_ns):
    import onnxruntime as ort
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    return ort.InferenceSession(path,sess_options=options,providers=["CPUExecutionProvider"])


def analyze_onnx(raw, weights, confidence=.35):
    import cv2
    session = load_session(str(weights.resolve()),weights.stat().st_mtime_ns)
    metadata = session.get_modelmeta().custom_metadata_map
    try:
        labels = ast.literal_eval(metadata.get("names","{}"))
    except (ValueError,SyntaxError):
        labels = {}
    if labels not in ({0:"pothole"}, {"0":"pothole"}, ["pothole"]):
        raise ValueError("This adapter requires a one-class pothole segmentation model with explicit label metadata.")
    source = Image.open(BytesIO(raw)).convert("RGB")
    image = np.asarray(source)
    height,width = image.shape[:2]
    input_spec = session.get_inputs()[0]
    if input_spec.type != "tensor(float)" or len(input_spec.shape)!=4:
        raise ValueError("Unsupported ONNX input format.")
    size_h = input_spec.shape[2] if isinstance(input_spec.shape[2],int) else 640
    size_w = input_spec.shape[3] if isinstance(input_spec.shape[3],int) else 640
    scale = min(size_w/width,size_h/height)
    resized_w,resized_h = round(width*scale),round(height*scale)
    offset_x,offset_y = (size_w-resized_w)//2,(size_h-resized_h)//2
    padded = np.full((size_h,size_w,3),114,dtype=np.uint8)
    padded[offset_y:offset_y+resized_h,offset_x:offset_x+resized_w] = cv2.resize(image,(resized_w,resized_h))
    tensor = padded.transpose(2,0,1)[None].astype(np.float32)/255
    outputs = session.run(None,{input_spec.name:tensor})
    if len(outputs)!=2 or outputs[1].ndim!=4:
        raise ValueError("Expected a YOLOv8 segmentation export with mask prototypes.")
    predictions = outputs[0][0]
    prototypes = outputs[1][0]
    mask_count = prototypes.shape[0]
    expected = 5+mask_count
    if predictions.shape[0] == expected:
        predictions = predictions.T
    if predictions.shape[1] != expected:
        raise ValueError("This ONNX output layout is not supported.")
    predictions = predictions[predictions[:,4]>=confidence]
    boxes = predictions[:,:4].copy()
    boxes[:,:2] -= boxes[:,2:]/2
    indices = cv2.dnn.NMSBoxes(boxes.tolist(),predictions[:,4].tolist(),confidence,.45)
    indices = np.asarray(indices).reshape(-1)[:20] if len(indices) else []
    annotated = source.copy()
    overlay = np.asarray(source).copy()
    detections = []
    for index in indices:
        prediction = predictions[index]
        x,y,w,bh = boxes[index]
        x1,x2 = np.clip((np.array([x,x+w])-offset_x)/scale,0,width)
        y1,y2 = np.clip((np.array([y,y+bh])-offset_y)/scale,0,height)
        logits = prediction[5:] @ prototypes.reshape(mask_count,-1)
        mask = (1/(1+np.exp(-np.clip(logits,-40,40)))).reshape(prototypes.shape[1:])
        mask = cv2.resize(mask,(size_w,size_h))[offset_y:offset_y+resized_h,offset_x:offset_x+resized_w]
        mask = cv2.resize(mask,(width,height))>.5
        cropped = np.zeros((height,width),dtype=np.uint8)
        bx1,by1,bx2,by2 = int(x1),int(y1),int(np.ceil(x2)),int(np.ceil(y2))
        cropped[by1:by2,bx1:bx2] = mask[by1:by2,bx1:bx2]
        contours,_ = cv2.findContours(cropped,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        polygon = []
        if contours:
            contour = max(contours,key=cv2.contourArea)
            contour = cv2.approxPolyDP(contour,max(1,cv2.arcLength(contour,True)*.001),True)
            polygon = contour.reshape(-1,2).tolist()
            overlay[cropped.astype(bool)] = (overlay[cropped.astype(bool)]*.65 + np.array([255,90,31])*.35).astype(np.uint8)
        detections.append({"class":"pothole","confidence":float(prediction[4]),
            "bbox_px":[round(float(v),1) for v in [x1,y1,x2,y2]],"polygon_px":polygon,
            "area_px":int(np.count_nonzero(cropped))})
    annotated = Image.fromarray(overlay)
    draw = ImageDraw.Draw(annotated)
    for detection in detections:
        box = detection["bbox_px"]
        draw.rectangle(box,outline="#FF5A1F",width=3)
        label = f'pothole {detection["confidence"]:.0%} / model prediction'
        draw.rectangle((box[0],max(0,box[1]-22),min(width,box[0]+280),box[1]+2),fill="#111111")
        draw.text((box[0]+4,max(0,box[1]-19)),label,fill="white")
    output = BytesIO()
    annotated.save(output,"JPEG",quality=90)
    return {"status":"Experimental local segmentation completed; human review required.",
            "model":weights.name,"model_sha256":hashlib.sha256(weights.read_bytes()).hexdigest(),
            "detections":detections,"annotated":output.getvalue(),"image_size_px":[width,height],
            "confidence_threshold":confidence}
