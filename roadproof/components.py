from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import folium
import streamlit as st
from streamlit_folium import st_folium


def h(value):
    return escape(str(value), quote=True)


def html(markup):
    st.html(markup)


def date_label(value):
    if not value:
        return "Not recorded"
    date = datetime.fromisoformat(value)
    try:
        date = date.astimezone(ZoneInfo("Asia/Kolkata"))
    except ZoneInfoNotFoundError:
        from datetime import timedelta, timezone
        date = date.astimezone(timezone(timedelta(hours=5, minutes=30)))
    return date.strftime("%d %b %Y · %I:%M %p IST")


def go(page):
    st.session_state.page = page
    st.query_params["page"] = page
    if "token" in st.query_params:
        del st.query_params["token"]
    st.rerun()


def intro(overline, title, text):
    html(f'<div class="page-intro"><div class="overline">{h(overline)}</div><h1>{h(title)}</h1><p>{h(text)}</p></div>')


def badge(status):
    cls = "green" if status == "Verified and Closed" else "amber" if status == "Verification Pending" else "orange" if status == "Reopened" else ""
    return f'<span class="status {cls}">{h(status)}</span>'


def summary(label, value):
    html(f'<div class="summary-cell"><small>{h(label)}</small><strong>{h(value)}</strong></div>')


def timeline(events):
    html('<div class="timeline">' + ''.join(
        f'<div class="event"><strong>{h(e["action"])} · {h(e["status"])}</strong><p>{h(e["note"])}</p><small>{h(date_label(e["created_at"]))} / {h(e["actor"])}</small></div>'
        for e in events) + '</div>')


def image_view(path, caption=None):
    from .images import read_image
    try:
        raw = read_image(path)
    except (OSError, ValueError):
        st.warning("This private image could not be loaded. Check the storage connection and try again.")
        return
    if raw:
        st.image(raw, caption=caption, width="stretch")
    else:
        html('<div class="empty-evidence">No evidence image available.</div>')


def evidence_pair(report):
    left, right = st.columns(2, gap="large")
    with left:
        html('<div class="evidence-heading">01 / Original report <span>BEFORE</span></div>')
        image_view(report["image_path"], "Synthetic illustration" if report["synthetic"] else "Citizen-submitted image")
    with right:
        html('<div class="evidence-heading after">02 / Repair evidence <span>AFTER</span></div>')
        image_view(report["evidence_path"], "Synthetic repair illustration" if report["synthetic"] else "Administrator-submitted evidence; requires human review")


def report_map(reports, key, center=None, zoom=13, height=370, selected=None):
    center = center or ([reports[0]["lat"], reports[0]["lon"]] if reports else [15.8281, 78.0373])
    map_obj = folium.Map(location=center, zoom_start=zoom, tiles="OpenStreetMap", control_scale=True)
    colors = {"Verified and Closed": "green", "Verification Pending": "orange", "Reopened": "red",
              "Reported": "gray", "Repair in Progress": "blue"}
    for r in reports:
        folium.CircleMarker([r["lat"], r["lon"]], radius=8, weight=2, fill=True, fill_opacity=.85,
            color=colors.get(r["status"], "#71717A"),
            tooltip=h(f'{r["id"]} · {r["status"]}'),
            popup=folium.Popup(h(f'{r["id"]} · {r["location"]} · {r["status"]}'), max_width=280)).add_to(map_obj)
    if selected:
        folium.Marker(selected, tooltip="Your selected location", icon=folium.Icon(color="orange", icon="map-marker")).add_to(map_obj)
    if len(reports) > 1:
        map_obj.fit_bounds([[r["lat"], r["lon"]] for r in reports], padding=(30, 30))
    return st_folium(map_obj, key=key, height=height, use_container_width=True,
                    returned_objects=["last_clicked"] if selected else [])


def footer():
    html('<footer class="footer"><div><b>RoadProof AI</b> · Detect. Report. Track. Verify.<br>Built by Team 10x · Kurnool, Andhra Pradesh</div><div>SEVA First Innovation Challenge 2026<br>Demonstration prototype · No government integration</div></footer>')
