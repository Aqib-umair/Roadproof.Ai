"""Launch with: streamlit run app.py"""
import os
import hashlib
from pathlib import Path

import streamlit as st

from roadproof.components import footer, go, html, intro
from roadproof.database import Database
from roadproof.settings import backend_settings
from roadproof.branding import ASSETS, brand_markup

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("ROADPROOF_DATA_DIR", str(ROOT / "data")))
st.set_page_config(page_title="RoadProof AI · Detect. Report. Track. Verify.",page_icon=str(ASSETS / "roadproof-favicon.png"),layout="wide",initial_sidebar_state="collapsed")
html(f'<style>{(ROOT / "roadproof" / "styles.css").read_text(encoding="utf-8")}</style>')


@st.cache_resource
def database(path, backend="sqlite", url="", secret_fingerprint="", _settings=None):
    if backend == "supabase":
        from roadproof.cloud import SupabaseDatabase
        return SupabaseDatabase(_settings)
    db = Database(Path(path)/"roadproof.sqlite3")
    db.seed(Path(path)/"images")
    return db


def about():
    intro("TEAM 10x / SURAKSHIT BHARAT", "From observation\nto accountability.", "RoadProof AI connects a citizen's road-damage report with a transparent maintenance and evidence-review journey.")
    html('<div class="team-grid"><div><div class="overline">BUILT BY TEAM 10x</div><strong>S.MD.Aqib Umair<br>Shaik Arashad</strong><p>Dr. K. V. Subba Reddy Institute of Technology<br>Kurnool, Andhra Pradesh</p></div><div><div class="overline">SEVA FIRST INNOVATION CHALLENGE 2026</div><strong>Surakshit Bharat</strong><p>Mobility, Infrastructure and Public Safety<br>Detect. Report. Track. Verify.</p></div></div>')
    topics = [
        ("The problem", "Road damage can be hard to report precisely. Repeated complaints and unclear repair updates make it difficult to know what has happened and what still needs attention."),
        ("The proposed solution", "A photograph, a citizen-confirmed map pin and a private tracking receipt establish a report. Maintenance teams could then record progress, attach repair evidence and ask a human reviewer to verify the outcome."),
        ("The innovation", "Repair verification is part of the core journey. An evidence trail connects the initial observation, a repair claim, the reviewer's notes and any reopening decision. Nearby-case suggestions support a reviewer without automatically merging complaints."),
        ("The working prototype", "Python and Streamlit power the interface; SQLite stores local records and audit history. Pillow validates and cleans images. Pandas supports case tables, while Folium and streamlit-folium provide location selection and report maps."),
        ("Future scalability", "Future work could evaluate a locally trained YOLO/OpenCV pipeline, add Telugu and Hindi, calibrate measurements, integrate authorized maintenance systems and introduce role-based identities, tamper-resistant audit storage and independent field inspections."),
        ("Current limitations", "No AI detector, municipal integration or email delivery is connected by default. Illustrative costs use manually supplied measurements and editable assumptions. The local password gate is for demonstrations; it is not production identity management. Synthetic samples do not establish validated public outcomes or government partnerships."),
    ]
    for title,text in topics:
        a,b = st.columns([1,2])
        a.subheader(title)
        b.write(text)
        st.divider()


def main():
    try:
        settings = backend_settings()
        db = database(str(DATA.resolve()), settings.backend, settings.url,
                      hashlib.sha256(settings.secret.encode()).hexdigest(), _settings=settings)
    except (ValueError, OSError):
        st.error("The selected database is not configured. Check the server-only settings and setup guide. Supabase mode does not fall back to local storage.")
        st.stop()
    incoming = st.query_params.get("token","")
    if incoming:
        st.session_state.tracking_token = incoming
        st.session_state.page = "track"
        st.query_params["page"] = "track"
        del st.query_params["token"]
    page = st.session_state.get("page",st.query_params.get("page","home"))
    with st.container(key="topnav"):
        cols = st.columns([2.2, .8,1.2,1.2,1.35,1.35])
        with cols[0]: html(brand_markup())
        for column,label,target in zip(cols[1:],["Home","How It Works","Track Report","Demo Dashboard","Report a Pothole"],["home","how","track","dashboard","report"]):
            with column:
                if st.button(label,key=f'nav_{target}',type="primary" if target=="report" else "secondary",width="stretch"): go(target)
    storage_label = "SUPABASE STORAGE" if db.backend == "supabase" else "LOCAL PROTOTYPE"
    html(f'<div class="demo-strip"><span>DEMONSTRATION MODE / {storage_label}</span><span>TEAM 10x · KURNOOL, INDIA</span></div>')
    if page == "home":
        from roadproof.landing import landing
        landing()
    elif page == "how":
        from roadproof.landing import workflow
        intro("HOW IT WORKS", "One report.\nA visible journey.", "A simple citizen experience, backed by a transparent case history. Every stage has a clear purpose.")
        workflow()
        a,b = st.columns(2)
        if a.button("Start a report →",type="primary"): go("report")
        if b.button("Explore repair verification →"): go("verify")
    elif page == "report":
        from roadproof.citizen import report_wizard
        report_wizard(db,DATA/"images")
    elif page == "success":
        from roadproof.citizen import success
        success(db)
    elif page == "track":
        from roadproof.citizen import tracking
        tracking(db)
    elif page == "dashboard":
        from roadproof.admin import dashboard
        dashboard(db,DATA/"images")
    elif page == "verify":
        from roadproof.admin import verification
        verification(db)
    elif page == "about":
        about()
    else:
        st.warning("This page is unavailable. Use the navigation to continue.")
    st.write("")
    a,b,c = st.columns(3)
    if a.button("About the project",width="stretch"): go("about")
    if b.button("Repair verification",width="stretch"): go("verify")
    if c.button("Track a report",width="stretch"): go("track")
    footer()


if __name__ == "__main__":
    try:
        main()
    except OSError:
        st.error("Storage is temporarily unavailable. Your draft is kept in this session. Check the database connection and try again.")
