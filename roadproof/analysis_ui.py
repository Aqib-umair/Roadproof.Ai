"""The analysis result stays visible for both positive and empty model results."""
import json

import streamlit as st

from .analysis import detection_parameters
from .components import date_label, summary


def render_result(result):
    detections = result["detections"]
    threshold = result.get("confidence_threshold",.35)
    if detections:
        st.success(f"Analysis complete — {len(detections)} pothole candidate(s) detected.")
    else:
        st.info(f"Analysis complete — no pothole detected at the {threshold:.0%} confidence threshold.")
        st.write("The model did not identify a pothole in this image. This does not mean the road is safe. Try a clearer, well-lit photograph that includes the damage and surrounding road.")
    info = result["image_info"]
    count,resolution = st.columns(2)
    count.metric("Pothole candidates",len(detections))
    resolution.metric("Photo resolution",f'{info["width_px"]} × {info["height_px"]} px')
    for note in info["quality_notes"]:
        st.warning(note)
    for index,detection in enumerate(detections,1):
        st.markdown(f'**Candidate {index} · {detection["class"]}**')
        st.write(f'Model confidence: **{detection["confidence"]:.1%}**')
        parameters = detection_parameters(detection,info)
        if parameters:
            left,right = st.columns(2)
            left.metric("Detected box width",f'{parameters["bbox_width_px"]:g} px')
            right.metric("Detected box height",f'{parameters["bbox_height_px"]:g} px')
            if parameters["outline_area_px2"] is not None:
                st.caption(f'Predicted outline area: {parameters["outline_area_px2"]:,.0f} px² · {parameters["image_coverage_percent"]:g}% of the photograph')
        st.caption("Pixel dimensions describe the detected image region; they are not centimetres or a severity assessment.")
    summary("Length / width in centimetres","Requires a visible known-size reference · use step 04" if detections else "Unavailable — no detected outline and no confirmed scale")
    summary("Depth","Requires a separate suitable measurement")
    with st.expander("Photo and analysis details"):
        summary("Model identification",result["model"])
        summary("Detection threshold",f"{threshold:.0%}")
        summary("Image format / size",f'{info["format"]} · {info["file_size_kb"]:g} KB')
        summary("Mean image brightness",f'{info["brightness_0_255"]:g} / 255 · measured pixel intensity')
        summary("Analysis finished",date_label(result["ran_at"]))
        summary("Run duration",f'{result["elapsed_seconds"]:g} seconds')
        st.caption("Image attributes are calculated from the uploaded pixels. Model confidence is not a measurement of accuracy, road severity or depth.")
        export = {key:value for key,value in result.items() if key!="annotated"}
        st.download_button("Download analysis details",json.dumps(export,indent=2),"roadproof-analysis.json",mime="application/json")
