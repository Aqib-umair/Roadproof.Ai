import hashlib
import json
import os
import re
import secrets
from urllib.parse import urlencode

import streamlit as st

from .components import badge, date_label, evidence_pair, go, h, html, image_view, intro, report_map, summary, timeline
from .costs import estimate
from .detection import PLACEHOLDER, analyze, weights_path
from .images import clean_image, save_image
from .tracking import remember_receipt, resolve_tracking


def draft():
    if "draft" not in st.session_state:
        st.session_state.draft = {"step": 1, "lat": 15.8281, "lon": 78.0373, "confirmed": False,
                                  "token": secrets.token_urlsafe(32), "image_version": 0}
    return st.session_state.draft


def advance(d, step):
    d["step"] = step
    st.rerun()


def report_wizard(db, image_directory):
    d = draft()
    intro("CITIZEN REPORTING / NO ACCOUNT REQUIRED", "A better road starts here.",
          "Add a photograph, confirm the location and record what needs attention. You can move back without losing your draft in this session.")
    labels = ["Photograph", "Location", "Analysis", "Measurements", "Submit"]
    html('<div class="stepper">' + ''.join(f'<div class="step {"active" if i == d["step"] else "done" if i < d["step"] else ""}"><b>0{i}</b>{label}</div>' for i,label in enumerate(labels,1)) + '</div>')
    if d["step"] == 1:
        left, right = st.columns([1.2, 1], gap="large")
        with left:
            st.subheader("01 / Show us the road.")
            st.write("Take the photograph from a safe place. Keep the damage in focus and include the surrounding road.")
            source = st.radio("Image source", ["Upload image", "Use camera"], horizontal=True)
            if source == "Upload image":
                upload = st.file_uploader("Drop a road image or browse files", type=["jpg", "jpeg", "png"],
                                          key=f'road_upload_{d["image_version"]}', help="Maximum 10 MB and 24 megapixels. Image metadata is removed before storage.")
            else:
                upload = st.camera_input("Capture road damage", key=f'road_camera_{d["image_version"]}')
            if upload:
                raw = upload.getvalue()
                digest = hashlib.sha256(raw).hexdigest()
                if digest != d.get("source_digest"):
                    try:
                        d["image"] = clean_image(raw)
                        d["source_digest"] = digest
                        d.pop("analysis", None)
                        d.pop("analysis_error", None)
                        d.pop("reference_result", None)
                        d.pop("saved_image", None)
                        st.success("Photograph added. Check the preview before continuing.")
                    except ValueError as exc:
                        st.error(str(exc))
            st.caption("JPG / PNG · up to 10 MB · image metadata removed on save. Please avoid faces and vehicle registration plates.")
            with st.expander("Include a reference for approximate surface measurements"):
                st.write("Place one RoadProof marker flat on the road beside the damage, on the same surface plane. Keep the entire marker and pothole visible; photograph from as directly overhead as safely possible. Do not enter traffic to place a marker.")
                st.caption("The measured black-square side length supplies the scale. Print size is not assumed. Marker estimates do not provide depth or surveyed dimensions.")
                try:
                    from .calibration import marker_png
                    st.download_button("Download reference marker",marker_png(),"roadproof-reference-marker.png",mime="image/png")
                except ImportError:
                    st.caption("The operator can enable the reference marker using requirements-ai.txt.")
            if d.get("image") and st.button("Remove image", key="remove_image"):
                for key in ["image", "source_digest", "analysis", "analysis_error", "saved_image", "reference_result"]:
                    d.pop(key, None)
                d["image_version"] += 1
                st.rerun()
        with right:
            if d.get("image"):
                st.image(d["image"], caption="Your report photograph · upload a different file to replace", width="stretch")
            else:
                html('<div class="empty-evidence">Your photograph will appear here.<br>One clear image is a useful first step.</div>')
        if st.button("Continue to location →", type="primary", disabled=not d.get("image")):
            advance(d, 2)

    elif d["step"] == 2:
        st.subheader("02 / Put the issue on the map.")
        st.write("Click the road location, or enter coordinates below. The starting view is Kurnool; it is not your GPS position or the photograph's location.")
        result = report_map([], "citizen_location", center=[d["lat"],d["lon"]], selected=[d["lat"],d["lon"]], height=390)
        clicked = (result or {}).get("last_clicked")
        if clicked and clicked != d.get("last_map_click"):
            d["last_map_click"] = clicked
            d["lat"], d["lon"] = round(clicked["lat"],6), round(clicked["lng"],6)
            d["confirmed"] = False
            st.session_state.manual_lat = d["lat"]
            st.session_state.manual_lon = d["lon"]
            st.rerun()
        st.caption("Map tiles need internet access. Manual coordinates work if the map is unavailable.")
        a, b = st.columns(2)
        lat = a.number_input("Latitude", min_value=-90.0, max_value=90.0, value=d["lat"], format="%.6f", key="manual_lat")
        lon = b.number_input("Longitude", min_value=-180.0, max_value=180.0, value=d["lon"], format="%.6f", key="manual_lon")
        if (lat,lon) != (d["lat"],d["lon"]):
            d["lat"], d["lon"], d["confirmed"] = lat, lon, False
        d["location"] = st.text_input("Road or nearby landmark (optional)", value=d.get("location", ""), max_chars=160,
                                     placeholder="e.g. road near the bus stand")
        if st.button("Confirm this location", type="primary"):
            d["confirmed"] = True
            st.success(f"Location confirmed: {lat:.6f}, {lon:.6f}")
        if d["confirmed"]:
            st.caption(f"Confirmed pin: {lat:.6f}° latitude / {lon:.6f}° longitude")
        a, b = st.columns(2)
        if a.button("← Back to photograph"): advance(d, 1)
        if b.button("Continue to analysis →", disabled=not d["confirmed"]): advance(d, 3)

    elif d["step"] == 3:
        st.subheader("03 / Evidence first. Honest analysis.")
        weights = weights_path()
        if weights is not None:
            with st.expander("Detection sensitivity"):
                threshold_percent = st.slider("Confidence threshold (%)",10,80,value=d.get("threshold_percent",35),step=5,
                    help="A lower threshold may show more candidates but also more false positives. It cannot recover detail missing from a dark or blurred image.")
                d["threshold_percent"] = threshold_percent
            threshold = threshold_percent/100
            requested = st.button("Run local model analysis",type="primary",key="run_analysis")
            signature = (hashlib.sha256(d["image"]).hexdigest(),str(weights),weights.stat().st_mtime_ns,threshold)
            needs_result = not d.get("analysis",{}).get("image_info")
            if requested or (needs_result and d.get("analysis_attempt") != signature):
                d["analysis_attempt"] = signature
                try:
                    with st.spinner("Analysing this photograph — detecting potholes and reading image parameters…"):
                        d["analysis"] = analyze(d["image"],confidence=threshold)
                    d.pop("analysis_error",None)
                except ImportError:
                    d.pop("analysis",None)
                    d["analysis_error"] = "The configured AI runtime is missing. Install requirements-ai.txt for ONNX, or ultralytics for trusted .pt weights."
                except ValueError as exc:
                    d.pop("analysis",None)
                    d["analysis_error"] = str(exc)
                except Exception as exc:
                    d.pop("analysis",None)
                    d["analysis_error"] = f"The local detector could not finish this image ({type(exc).__name__}). Check the configured model and AI dependencies, then retry."
        a,b = st.columns([1.2,1], gap="large")
        with a:
            result = d.get("analysis",{})
            caption = "Detected regions · model predictions" if result.get("detections") else "Uploaded photograph · no detected pothole outline" if result else "Uploaded photograph"
            st.image(result.get("annotated", d["image"]),caption=caption,width="stretch")
        with b:
            if weights is None:
                html(f'<div class="note">{h(PLACEHOLDER)}</div>')
                st.write("Your photograph will be recorded for human review. You can continue without AI analysis.")
                summary("Detection confidence", "Unavailable — no connected model")
                summary("Model identification", "Not connected")
            else:
                if d.get("analysis_error"):
                    st.error("Analysis did not complete. You can retry or continue for manual review.")
                    with st.expander("Analysis diagnostic"):
                        st.write(d["analysis_error"])
                if d.get("analysis",{}).get("image_info"):
                    from .analysis_ui import render_result
                    render_result(d["analysis"])
                    if d["analysis"].get("confidence_threshold") != threshold:
                        st.warning("The result uses the previous threshold. Click Run local model analysis to apply your new sensitivity setting.")
            st.caption("Local prototype predictions require human review. A confidence score is not a severity, distance, depth or repair-cost measurement.")
        if st.button("← Back to location"): advance(d, 2)
        if st.button("Continue to measurements →", type="primary"): advance(d, 4)

    elif d["step"] == 4:
        st.subheader("04 / Measurements, if you have them.")
        html('<div class="note">Exact length, width and depth cannot be determined from an arbitrary uncalibrated photograph. Skip this step unless you have safe, suitable measurements.</div>')
        methods = ["Not measured", "Visual estimate only", "Measured on site", "Calibrated survey", "Reference marker estimate"]
        method = st.selectbox("Measurement method", methods, index=methods.index(d.get("method", "Not measured")))
        d["method"] = method
        d["cost"] = None
        d["measurements"] = None
        if method == "Reference marker estimate":
            from .calibration import DISCLAIMER, measure_detection
            st.caption(DISCLAIMER)
            candidates = [detection for detection in d.get("analysis",{}).get("detections",[])
                          if detection.get("polygon_px") and detection["class"].lower()=="pothole"]
            if not candidates:
                st.info("A pothole segmentation outline is needed first. Run a connected segmentation model in step 03, or enter on-site measurements instead.")
            else:
                selected = st.selectbox("Pothole to measure",range(len(candidates)),
                    format_func=lambda i:f'Pothole {i+1} · {candidates[i]["confidence"]:.0%} model confidence')
                side = st.number_input("Measured black-square side length (cm)",2.0,100.0,value=d.get("marker_side",10.0),step=.5)
                d["marker_side"] = side
                params = (selected,side)
                if d.get("reference_params") != params:
                    d.pop("reference_result",None)
                confirmed = st.checkbox("The marker lies flat beside the pothole on the same road plane, and I measured its black-square side.")
                if st.button("Estimate surface dimensions",disabled=not confirmed,type="primary"):
                    try:
                        d["reference_result"] = measure_detection(d["image"],candidates[selected],side)
                        d["reference_params"] = params
                    except (ValueError,ImportError):
                        st.error("A usable reference could not be measured. Check that exactly one ID 0 RoadProof marker is visible, is large enough, lies near the damage, and that AI dependencies are installed.")
                if d.get("reference_result"):
                    d["measurements"] = d["reference_result"]
                    a,b = st.columns(2)
                    a.metric("Approximate surface length",f'{d["measurements"]["length_cm"]:.1f} cm')
                    b.metric("Approximate surface width",f'{d["measurements"]["width_cm"]:.1f} cm')
                    st.caption("Depth: unavailable. No repair-cost allowance is calculated from these unvalidated image estimates.")
        elif method != "Not measured":
            columns = st.columns(3)
            length = columns[0].number_input("Length (cm)", 0.0, 10000.0, value=d.get("length",0.0), step=1.0)
            width = columns[1].number_input("Width (cm)", 0.0, 10000.0, value=d.get("width",0.0), step=1.0)
            depth = columns[2].number_input("Depth (cm)", 0.0, 1000.0, value=d.get("depth",0.0), step=0.5)
            d.update(length=length, width=width, depth=depth)
            d["measurements"] = {"length_cm":length,"width_cm":width,"depth_cm":depth,"method":method}
            if method in {"Measured on site", "Calibrated survey"}:
                rate = st.number_input("Illustrative material rate (₹ per m³)", 1.0, 1000000.0, value=d.get("rate",8000.0), step=500.0)
                d["rate"] = rate
                if all(v > 0 for v in [length,width,depth]):
                    cost = estimate(length, width, depth, rate, method)
                    d["cost"] = cost
                    a,b = st.columns(2)
                    a.metric("Illustrative material quantity", f'{cost["volume_m3"]:.4f} m³')
                    b.metric("Preliminary material allowance", f'₹{cost["amount"]:,.2f}')
                    st.caption(f'Length × width × depth ÷ 1,000,000 = {cost["volume_m3"]:.4f} m³. Volume × ₹{rate:,.0f}/m³ × 1.15 (15% waste allowance).')
                else:
                    st.info("Enter all three positive measurements to calculate a material allowance, or continue without a cost.")
            else:
                st.info("Visual estimates are recorded as unverified notes and are not used for a cost calculation.")
        st.caption("Illustration only. The default rate is an editable teaching assumption, not an approved schedule of rates. This is a rectangular material-volume allowance; labour, plant, traffic control, taxes, base preparation and engineering assessment are excluded. It is not a quote.")
        if st.button("← Back to analysis"): advance(d,3)
        if st.button("Review your report →", type="primary"): advance(d,5)

    elif d["step"] == 5:
        st.subheader("05 / Check the details. Make it count.")
        a,b = st.columns([1,1.1], gap="large")
        with a:
            st.image(d["image"], width="stretch")
            summary("Location", f'{d.get("location") or "Selected map location"} · {d["lat"]:.6f}, {d["lon"]:.6f}')
            summary("Detection status", d.get("analysis",{}).get("status", PLACEHOLDER))
            summary("Measurement status", d.get("method", "Not measured"))
            if d.get("cost"):
                summary("Illustrative material allowance", f'₹{d["cost"]["amount"]:,.2f} · not an approved repair estimate')
        with b:
            d["description"] = st.text_area("Describe the road damage", value=d.get("description",""), height=150,
                max_chars=2000, placeholder="What do you see? Which part of the road is affected? Please avoid personal information.")
            email = st.text_input("Citizen email (optional)", value=d.get("email",""), max_chars=254)
            consent = st.checkbox("I consent to storing my email for possible future report updates.", value=d.get("consent",False))
            d.update(email=email, consent=consent)
            st.caption("Email notifications are not connected. Use your private tracking link for updates. Email is saved only with consent and is never shown on the public dashboard.")
            acknowledged = st.checkbox("I understand this is a demonstration report and is not sent to a government authority.")
            if st.button("Submit Report ↗", type="primary", disabled=not acknowledged, width="stretch"):
                try:
                    if not d.get("confirmed"):
                        raise ValueError("Return to step 02 and confirm the location.")
                    if not 10 <= len(d["description"].strip()) <= 2000:
                        raise ValueError("Please describe the damage in at least 10 characters.")
                    if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
                        raise ValueError("Check your email address, or leave it empty.")
                    with st.spinner("Recording your report…"):
                        if not d.get("saved_image"):
                            d["saved_image"] = save_image(d["image"], image_directory)
                        analysis = d.get("analysis",{})
                        report_id = db.create_report(token=d["token"],lat=d["lat"],lon=d["lon"],location=d.get("location",""),
                            description=d["description"], image_path=d["saved_image"],
                            ai_status=analysis.get("status",PLACEHOLDER),model=analysis.get("model","Not connected"),
                            detections=analysis.get("detections",[]), measurements=d.get("measurements"),cost=d.get("cost"),
                            email=email,consent=consent)
                    st.session_state.receipt = {"id":report_id,"token":d["token"]}
                    remember_receipt(st.session_state, st.session_state.receipt)
                    del st.session_state["draft"]
                    go("success")
                except ValueError as exc:
                    st.error(str(exc))
                except OSError:
                    st.error("The report could not be saved. Your draft is kept. Check the selected storage connection and retry; the same draft will not create a duplicate report.")
        if st.button("← Back to measurements"): advance(d,4)
    with st.expander("Draft and privacy"):
        destination = "the configured private Supabase project" if db.backend == "supabase" else "this computer"
        st.caption(f"Drafts stay in your current browser session. Submitted reports and cleaned images are stored in {destination}. Keep your tracking link private. Do not upload sensitive personal information.")
        if st.button("Discard draft", key="discard_draft"):
            del st.session_state["draft"]
            # Streamlit cleans unrendered widget state on the next rerun.
            go("home")


def success(db):
    receipt = st.session_state.get("receipt")
    if not receipt:
        intro("REPORT RECEIPT", "Your next step starts here.", "Open your private tracking link to see a previously submitted report.")
        if st.button("Track your report", type="primary"): go("track")
        return
    report = db.by_token(receipt["token"])
    if not report:
        st.error("This report could not be found in the selected database.")
        return
    remember_receipt(st.session_state, receipt)
    html('<div class="success-icon" aria-label="Report recorded">✓</div>')
    intro("REPORT RECORDED", "Your report has been recorded.", "A clear starting point for a more accountable repair journey.")
    html(badge(report["status"]))
    a,b = st.columns(2)
    with a:
        summary("Report ID — for reference", report["id"])
        summary("Selected location", f'{report["lat"]:.6f}, {report["lon"]:.6f}')
    with b:
        summary("Submission date", date_label(report["created_at"]))
        summary("Storage", "Private Supabase project" if db.backend == "supabase" else "Local RoadProof AI demonstration")
    html('<div class="note">This is a RoadProof AI demonstration report, not an officially filed government complaint.</div>')
    st.subheader("Save your private tracking access.")
    st.caption("The RP-… report ID is a reference number. Use the private token or full link below to open this report on another browser.")
    st.write("**Private tracking token**")
    st.code(receipt["token"], language=None)
    base = os.environ.get("ROADPROOF_BASE_URL", "http://localhost:8501").rstrip("/")
    link = f'{base}/?{urlencode({"page":"track","token":receipt["token"]})}'
    st.write("**Private tracking link**")
    st.code(link, language=None)
    st.caption("Use the copy icon at the right of the link. Anyone with this link can view this report and leave feedback. Save it now; the database stores only a hash of the access token.")
    st.download_button("Download tracking receipt", f'RoadProof AI demonstration\nReport ID (reference only): {report["id"]}\nPrivate tracking token: {receipt["token"]}\nPrivate tracking link: {link}\nKeep this receipt private. Not an official government complaint.\n', file_name=f'{report["id"]}-tracking.txt', mime="text/plain")
    a,b = st.columns(2)
    if a.button("View report →", type="primary"):
        st.session_state.tracking_token = receipt["token"]
        go("track")
    if b.button("Report another issue"):
        go("report")


def tracking(db):
    intro("PRIVATE CASE TRACKING", "Every step, on the record.", "Paste your private tracking token or the complete link from your receipt. Reports submitted in this browser session can also be opened by their report ID.")
    with st.form("tracking_lookup"):
        entered = st.text_input("Private tracking token or full tracking link", type="password",
            help="The RP-… value is a report ID. It works here only if this browser session still holds that report's private receipt.")
        submitted = st.form_submit_button("Find my report", type="primary")
    if submitted:
        st.session_state.tracking_reference = entered.strip()
        st.session_state.pop("tracking_token", None)
        st.session_state.pop("sample_tracking", None)
    reference = st.session_state.get("tracking_reference") if submitted else st.session_state.get("tracking_token") or st.session_state.get("tracking_reference", "")
    report, token, outcome = resolve_tracking(db, reference,st.session_state.get("my_reports"),st.session_state.get("receipt")) if reference else (None,"","empty")
    if report:
        st.session_state.tracking_token = token
    if outcome == "id_requires_token":
        st.warning("That is a report ID, not a private token. Paste the private token or full tracking link from your receipt. For privacy, an ID alone cannot open a report from another browser.")
    elif outcome == "invalid":
        st.warning("Paste the complete private token or tracking link from your receipt. Remove any surrounding text.")
    elif outcome == "not_found":
        st.error("No report matches this private tracking access in the selected database. Check that you copied the complete token or link.")
    receipts = dict(st.session_state.get("my_reports",{}))
    if latest := st.session_state.get("receipt"):
        receipts[latest["id"]] = latest["token"]
    if receipts:
        with st.expander("Your reports from this session",expanded=not bool(report)):
            own_id = st.selectbox("Saved report receipt",list(reversed(receipts)))
            if st.button("Open my saved report", type="primary"):
                st.session_state.tracking_token = receipts[own_id]
                st.session_state.pop("tracking_reference",None)
                st.session_state.pop("sample_tracking",None)
                st.rerun()
            if st.button("View my latest tracking receipt"):
                go("success")
    if not report:
        with st.expander("Just exploring? Open a synthetic sample"):
            samples = [r for r in db.public_reports() if r["synthetic"]]
            if samples:
                sample = st.selectbox("Demonstration case", samples, format_func=lambda r:f'{r["id"]} · {r["status"]}')
                if st.button("Open synthetic case"):
                    st.session_state.sample_tracking = sample["id"]
            if st.session_state.get("sample_tracking"):
                candidate = db.get(st.session_state.sample_tracking)
                if candidate and candidate["synthetic"]:
                    report = candidate
    if not report:
        return
    if report["synthetic"]:
        st.info("Synthetic demonstration record and illustrations. No real complaint or repair is represented.")
    html(badge(report["status"]))
    a,b = st.columns([1.15,1], gap="large")
    with a:
        summary("Report ID",report["id"])
        summary("Location",f'{report["location"]} · {report["lat"]:.6f}, {report["lon"]:.6f}')
        summary("Recorded",date_label(report["created_at"]))
        st.write(report["description"])
        summary("Detection",report["ai_status"])
        if report["measurements_json"]:
            measure = json.loads(report["measurements_json"])
            depth = f'{measure["depth_cm"]} cm' if measure.get("depth_cm") is not None else "unavailable"
            summary("Report measurements", f'{measure["length_cm"]} × {measure["width_cm"]} cm surface · depth {depth} · {measure["method"]}')
            if measure.get("disclaimer"):
                st.caption(measure["disclaimer"])
        if report["cost_json"]:
            cost = json.loads(report["cost_json"])
            st.caption(f'Illustrative material allowance ₹{cost["amount"]:,.2f} = {cost["volume_m3"]:.4f} m³ × ₹{cost["rate_per_m3"]:,.0f} × 1.15. Excludes labour and other works. Not an approved repair estimate.')
    with b:
        st.subheader("Case timeline")
        events = db.history(report["id"])
        timeline(events)
    st.subheader("The evidence trail")
    evidence_pair(report)
    st.caption("Closure means a human reviewer approved this local demonstration record. It is not official certification of a road repair.")
    if not report["synthetic"]:
        with st.form("citizen_feedback"):
            feedback = st.text_area("Share feedback or flag a concern", max_chars=2000)
            if st.form_submit_button("Add feedback"):
                try:
                    db.feedback(token, feedback)
                    st.success("Your feedback was added to the case history.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        st.caption("Clearing this private session removes its saved receipts. Download your tracking receipt first; saved links remain valid.")
        if st.button("Clear private tracking session"):
            for key in ["tracking_token","tracking_reference","my_reports","receipt","sample_tracking"]:
                st.session_state.pop(key, None)
            st.rerun()
