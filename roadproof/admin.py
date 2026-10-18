from datetime import date, datetime
import json

import pandas as pd
import streamlit as st

from .auth import admin_gate, is_admin, open_demo_access
from .components import badge, date_label, evidence_pair, go, h, html, image_view, intro, report_map, summary, timeline
from .database import STATUSES, TRANSITIONS, duplicate_pairs
from .images import remove_image, save_image
from .report_views import filter_reports, submission_date


def admin_access():
    if open_demo_access():
        st.caption("Open demonstration workspace · no password required · all changes are prototype actions")
        return True
    if is_admin():
        st.caption("Demo administrator session active · expires after one hour")
        if st.button("Lock administrator controls"):
            st.session_state.pop("admin_until",None)
            st.session_state.pop("admin_fingerprint",None)
            st.rerun()
        return True
    with st.expander("Administrator access", expanded=not is_admin()):
        return admin_gate()


def case_details(db, report, image_directory):
    st.subheader("Case workspace")
    html(badge(report["status"]))
    if report["synthetic"]:
        st.info("Synthetic sample. All images and activity in this case are demonstration material.")
    a,b = st.columns([1.2,1],gap="large")
    with a:
        image_view(report["image_path"])
    with b:
        summary("Report",report["id"])
        summary("Location", f'{report["location"]} · {report["lat"]:.6f}, {report["lon"]:.6f}')
        summary("Submitted",date_label(report["created_at"]))
        summary("AI result",report["ai_status"])
        st.write(report["description"])
        detections = json.loads(report["analysis_json"])
        if detections:
            st.caption(f'Local model: {report["model"]}')
            st.dataframe(pd.DataFrame([{"Class":d["class"],"Model confidence":d["confidence"]} for d in detections]),hide_index=True,width="stretch")
        if report["measurements_json"]:
            measurements = json.loads(report["measurements_json"])
            depth = f'{measurements["depth_cm"]} cm' if measurements.get("depth_cm") is not None else "unavailable"
            summary("Report measurements", f'{measurements["length_cm"]} × {measurements["width_cm"]} cm surface · depth {depth}')
            st.caption(f'Method: {measurements["method"]}. {measurements.get("disclaimer", "Citizen-provided; requires review.")}')
    status_tab, evidence_tab, history_tab = st.tabs(["Manage status", "Repair evidence", "Audit history"])
    with status_tab:
        next_statuses = TRANSITIONS[report["status"]]
        if next_statuses:
            with st.form(f'status_{report["id"]}'):
                status = st.selectbox("Next workflow stage",next_statuses)
                note = st.text_area("Reason / progress update",max_chars=2000)
                submitted = st.form_submit_button("Save demo status", type="primary")
            if submitted:
                try:
                    db.update_status(report["id"],status,note,authorized=is_admin(),expected_status=report["status"])
                    st.session_state.admin_notice = "Status updated and recorded in the audit timeline."
                    st.rerun()
                except (ValueError,PermissionError) as exc:
                    st.error(str(exc))
        else:
            st.info("This case requires a reviewer decision in the repair verification workspace.")
        st.caption("A repair claim is not a verification decision. Human review and evidence are required for demo closure.")
        if st.button("Open repair verification →", key="open_verification"):
            st.session_state.verification_case = report["id"]
            go("verify")
    with evidence_tab:
        if report["evidence_path"]:
            image_view(report["evidence_path"],"Current repair evidence")
        if report["status"] == "Verified and Closed":
            st.caption("Reopen the case through a reviewer decision before adding new evidence.")
        else:
            with st.form(f'evidence_{report["id"]}', clear_on_submit=True):
                upload = st.file_uploader("After-repair photograph", type=["jpg","jpeg","png"])
                note = st.text_area("Evidence notes",max_chars=2000,placeholder="Describe the repair and where and when this photograph was taken.")
                submitted = st.form_submit_button("Save repair evidence", type="primary")
            if submitted:
                try:
                    if not upload or not note.strip():
                        raise ValueError("Choose an evidence image and add a note.")
                    path = save_image(upload.getvalue(),image_directory)
                    try:
                        db.add_evidence(report["id"],path,note,authorized=is_admin())
                    except (ValueError, PermissionError):
                        remove_image(path)
                        raise
                    st.session_state.admin_notice = "Repair evidence saved to this case. Previous evidence remains in the audit history."
                    st.rerun()
                except (ValueError,PermissionError,OSError) as exc:
                    st.error(str(exc))
    with history_tab:
        events = db.history(report["id"])
        timeline(events)
        evidence_events = [e for e in events if e["action"] == "Repair evidence uploaded"]
        for event in evidence_events:
            with st.expander(f'Evidence version · {date_label(event["created_at"])} · audit #{event["id"]}'):
                image_view(event["evidence_path"])
                st.write(event["note"])


def dashboard(db,image_directory):
    source = "the configured Supabase project" if db.backend == "supabase" else "local records in this installation"
    intro("OPERATIONS / DEMONSTRATION", "Road Maintenance\nControl Center", f"Demo environment — simulated administrative workflow. Counts come from {source}.")
    refresh, clear = st.columns(2)
    refresh.button("Refresh reports", key="refresh_reports", type="primary")
    if clear.button("Clear dashboard filters",key="clear_dashboard_filters"):
        for key in ["record_scope","status_filter","submission_dates","report_search","complaints_table","last_table_case"]:
            st.session_state.pop(key,None)
        st.rerun()
    st.caption("Refresh reads the latest saved reports from the database. Filters apply to the map, table and photograph review below.")
    reports = db.public_reports()
    scope = st.radio("Record scope",["All records","Synthetic samples","Citizen submissions"],horizontal=True,key="record_scope")
    scoped, _ = filter_reports(reports,scope=scope)
    pairs = duplicate_pairs(scoped)
    metrics = [("Total reported cases",len(scoped)),
               ("Open cases",sum(r["status"] != "Verified and Closed" for r in scoped)),
               ("Awaiting verification",sum(r["status"] == "Verification Pending" for r in scoped)),
               ("Verified and closed",sum(r["status"] == "Verified and Closed" for r in scoped)),
               ("Duplicate suggestions",len(pairs))]
    html('<div class="metric-grid">' + ''.join(f'<div class="metric-box"><small>{h(label)}</small><strong>{value:02}</strong></div>' for label,value in metrics) + '</div>')
    st.caption("Metrics reflect the selected record scope, before the status and date filters below. Verified means human-approved in this prototype; no municipal system is connected.")
    a,b = st.columns([1.3,1])
    statuses = a.multiselect("Filter by status",STATUSES,placeholder="All statuses",key="status_filter")
    if scoped:
        first = min(submission_date(r["created_at"]) for r in scoped)
        last = max(date.today(),max(submission_date(r["created_at"]) for r in scoped))
    else:
        first = last = date.today()
    dates = b.date_input("Submission date range",value=(first,last),format="DD/MM/YYYY",key="submission_dates")
    query = st.text_input("Search report ID or location",key="report_search",placeholder="RP-… or a road / landmark")
    _, filtered = filter_reports(reports,scope,statuses,dates,query)
    if len(dates) == 1:
        st.caption("Select the end date to apply the date range.")
    st.caption(f"Showing {len(filtered)} of {len(reports)} saved reports. New submissions appear under All records or Citizen submissions; synthetic-only filters hide them.")
    map_tab, duplicate_tab = st.tabs(["Report map", "Potential duplicates"])
    with map_tab:
        report_map(filtered,"dashboard_map")
        st.caption("Markers show status labels on hover. Grey: reported · blue: repair in progress · amber: awaiting verification · green: demo verified · red: reopened. Contact details and private tracking tokens are never displayed here.")
    with duplicate_tab:
        st.caption("Location proximity only: pairs within 40 metres, calculated from local coordinates. Suggestions are not AI findings, are not confirmed duplicates, and are never automatically merged. Samples are compared only with samples.")
        if pairs:
            st.dataframe(pd.DataFrame(pairs,columns=["Case A","Case B","Distance (m)"]),hide_index=True,width="stretch")
        else:
            st.info("No nearby report pairs in this record scope.")
    st.subheader("Recent complaints")
    selected_row = None
    if filtered:
        frame = pd.DataFrame([{"Report ID":r["id"],"Location":r["location"],"Submission date":date_label(r["created_at"]),
            "Status":r["status"],"AI result":r["ai_status"],"Record type":"Synthetic sample" if r["synthetic"] else "Citizen demonstration",
            "Action":"Select to review"} for r in filtered])
        selection = st.dataframe(frame,hide_index=True,width="stretch",on_select="rerun",selection_mode="single-row",key="complaints_table")
        if selection.selection.rows:
            index = selection.selection.rows[0]
            if index < len(filtered):
                selected_row = filtered[index]["id"]
    else:
        st.info("No reports match these filters. Change the filters or record a new issue.")
    access = admin_access()
    if notice := st.session_state.pop("admin_notice",None):
        st.success(notice)
    if filtered and access:
        ids = [r["id"] for r in filtered]
        if selected_row and selected_row != st.session_state.get("last_table_case"):
            st.session_state.dashboard_case = selected_row
            st.session_state.last_table_case = selected_row
        if st.session_state.get("dashboard_case") not in ids:
            st.session_state.dashboard_case = ids[0]
        st.subheader("Report photographs")
        st.caption("Review a photograph to open its case workspace. This open demonstration workspace shows submitted photographs." if open_demo_access() else "Private citizen photographs are visible only in an unlocked administrator session. Review a photograph to open its case workspace.")
        with st.container(key="report_gallery"):
            for start in range(0,min(len(filtered),12),3):
                columns = st.columns(3)
                for column,item in zip(columns,filtered[start:start+3]):
                    with column:
                        with st.container(border=True):
                            full = db.get(item["id"])
                            if not full:
                                st.caption("This case is unavailable. Refresh reports.")
                                continue
                            image_view(full["image_path"],"Synthetic illustration" if full["synthetic"] else "Citizen report photograph")
                            st.write(f'**{item["id"]}**')
                            html(badge(item["status"]))
                            st.caption(item["location"])
                            st.caption(date_label(item["created_at"]))
                            if st.button("Review report →",key=f'photo_review_{item["id"]}',width="stretch"):
                                st.session_state.dashboard_case = item["id"]
                                st.rerun()
        if len(filtered)>12:
            st.caption("Showing photographs for the 12 most recent matches. Search or use the case selector to review older reports.")
        selected = st.selectbox("Open case",ids,key="dashboard_case",
            format_func=lambda value:next(f'{r["id"]} · {r["status"]}' for r in filtered if r["id"]==value))
        case_details(db,db.get(selected),image_directory)
    elif filtered:
        st.info("Unlock Administrator access above to view uploaded photographs and full case details. Public visitors can see the report list, but citizen photographs remain private.")


def verification(db):
    intro("EVIDENCE / HUMAN REVIEW", "A repair claim deserves\na closer look.", "Compare the original report with repair evidence. Record a reasoned human decision, then preserve it in the case history.")
    access = admin_access()
    reports = db.public_reports()
    options = reports if access else [r for r in reports if r["synthetic"]]
    if not access:
        st.caption("Read-only preview using synthetic samples. Unlock administrator controls to review a case.")
    if not options:
        st.info("No cases available for review.")
        return
    ids = [r["id"] for r in options]
    preferred = st.session_state.get("verification_case")
    if preferred not in ids:
        preferred = next((r["id"] for r in options if r["status"] == "Verification Pending"),ids[0])
    selected = st.selectbox("Evidence workspace case", ids, index=ids.index(preferred),
        format_func=lambda value:next(f'{r["id"]} · {r["status"]}' for r in options if r["id"]==value),key="verification_selector")
    report = db.get(selected)
    if report["synthetic"]:
        st.info("Synthetic illustrations and simulated review history. These are not photographs of an actual repair.")
    html(badge(report["status"]))
    st.write("")
    evidence_pair(report)
    a,b,c = st.columns(3)
    with a: summary("Location",f'{report["lat"]:.6f}, {report["lon"]:.6f}')
    with b: summary("Repair claim",date_label(report["repair_claim_at"]))
    with c: summary("Human verification",date_label(report["verified_at"]))
    st.caption("A side-by-side visual review cannot establish material strength, hidden defects or engineering compliance. Record uncertainties and request additional evidence when needed.")
    if notice := st.session_state.pop("review_notice",None):
        st.success(notice)
    if access:
        with st.form(f'review_{selected}'):
            note = st.text_area("Reviewer notes / reason for decision",max_chars=2000,placeholder="Describe what the evidence supports, any location concerns, and any further checks needed.")
            decision = st.radio("Reviewer decision",["Request More Evidence","Mark Verified","Reopen Case"],horizontal=True)
            attested = st.checkbox("I have personally reviewed both images, the location and the case history. I approve this demonstration closure.")
            submitted = st.form_submit_button("Record human decision",type="primary")
        if submitted:
            try:
                db.review(selected,decision,note,authorized=is_admin(),attested=attested,expected_status=report["status"])
                st.session_state.review_notice = "Human decision saved with a timestamp and reviewer notes. This is a local demo decision, not official certification."
                st.rerun()
            except (ValueError,PermissionError) as exc:
                st.error(str(exc))
        if st.button("Manage case / upload evidence →"):
            st.session_state.dashboard_case = selected
            go("dashboard")
    st.subheader("Review and audit trail")
    timeline(db.history(selected))
