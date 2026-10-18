import streamlit as st
from .components import go, html

STEPS = [
    ("CAPTURE", "Start with what you see.", "Upload a road image or take a photograph. No citizen account required."),
    ("DETECT", "Assist the first review.", "A future local vision model can flag damage. The current prototype is explicit about its limits."),
    ("REPORT", "Give the issue a place.", "Confirm the map location and record a clear, traceable report."),
    ("TRACK", "Follow the whole journey.", "Use a private token to follow notes, repair claims and every status change."),
    ("VERIFY", "Close the evidence gap.", "Compare original and repair evidence. A human reviewer makes the closure decision."),
]


def workflow():
    html('<div class="workflow">' + ''.join(f'<div class="workflow-item"><span class="number">0{i+1} / {s[0]}</span><h3>{s[1]}</h3><p>{s[2]}</p></div>' for i,s in enumerate(STEPS)) + '</div>')
    stage = st.select_slider("Explore the reporting journey", options=[s[0] for s in STEPS], key="workflow_explore")
    item = next(s for s in STEPS if s[0] == stage)
    st.info(f"{item[1]} {item[2]}")


def landing():
    from .hero import render_hero
    render_hero()
    a, b, _ = st.columns([1.5, 1.8, 2.7])
    with a:
        if st.button("Report Road Damage ↗", type="primary", width="stretch"): go("report")
    with b:
        if st.button("See how RoadProof works →", width="stretch"): go("how")
    html('''<div class="hero-foot"><span>NO SIGN-UP REQUIRED</span><span>PRIVATE REPORT TRACKING</span></div>
    <div class="trust-line"><span>A CIVIC-TECH PROTOTYPE BY <b>TEAM 10x</b></span><span>SEVA FIRST INNOVATION CHALLENGE 2026</span><span>SURAKSHIT BHARAT</span></div>
    <div class="section-head"><h2>Reporting damage is<br>only half the job.</h2><p>Broken roads deserve better solutions. The harder part is connecting a citizen's observation to a repair everyone can follow.</p></div>
    <div class="problem-grid">
    <div class="problem-panel"><span class="index">01 / THE VISIBILITY GAP</span><div class="problem-art">⌖ <span class="faint">— —</span></div><h3>Seen. Then forgotten.</h3><p>Road damage is easy to notice and difficult to describe. A photograph and a confirmed location give a report a clear starting point.</p></div>
    <div class="problem-panel"><span class="index">02 / THE DUPLICATION GAP</span><div class="problem-art">○ <span class="orange">◎</span> ○</div><h3>Many voices. One issue.</h3><p>Nearby complaints may describe the same damage. Location-based suggestions can help a reviewer connect them.</p></div>
    <div class="problem-panel"><span class="index">03 / THE EVIDENCE GAP</span><div class="problem-art">▧ <span class="orange">→</span> ▨</div><h3>Closed isn't the whole story.</h3><p>A repair claim needs evidence. A visible review trail makes the final decision easier to understand.</p></div></div>
    <div class="section-head"><h2>From a photograph<br>to a paper trail.</h2><p>Five connected steps. One accountable journey. Detect. Report. Track. Verify.</p></div>''')
    workflow()
    html('''<div class="preview"><div class="preview-ui"><div class="eyebrow">CITIZEN WORKSPACE / INTERFACE PREVIEW</div><h3>A simple first step.</h3><div class="mini-upload"><b>＋ Add a road photograph</b><br>Upload or use your camera<br><small>JPG / PNG · up to 10 MB</small></div><div class="mini-row"><span>Location</span><b>You confirm the pin</b></div><div class="mini-row"><span>Access</span><b>Your private tracking link</b></div></div>
    <div class="preview-track"><div class="eyebrow">EXAMPLE CASE JOURNEY</div><h3>The story doesn't end at submit.</h3><div class="timeline"><div class="event"><strong>Report recorded</strong><p>Photograph and selected location saved.</p></div><div class="event"><strong>Repair claimed</strong><p>After-repair evidence attached for review.</p></div><div class="event"><strong>Human verification</strong><p>Evidence reviewed before demo closure.</p></div></div></div></div>''')
    if st.button("Explore Live Demo →", type="primary"): go("dashboard")
    html('<div class="section-head" style="margin-top:65px"><h2>Built for evidence.<br>Designed for trust.</h2><p>Working prototype features today, with a clear path to future assisted review.</p></div>')
    features = [
        ("Computer-vision assisted review", "An optional local YOLO adapter is ready for custom weights. No detector is connected by default; no confidence scores are invented."),
        ("Location-confirmed reporting", "Citizens place and confirm the map pin. Nearby reports within 40 metres are suggestions for review, never automatically merged."),
        ("Explainable preliminary costs", "On-site measurements can feed a transparent material-volume illustration. No uncalibrated photograph is used to infer depth."),
        ("Evidence before closure", "A repair claim, original image, repair evidence and human decision all belong to the same recorded timeline."),
    ]
    for i, (title, text) in enumerate(features):
        html(f'<div class="feature-line"><span class="number">0{i+1}</span><h3>{title}</h3><p>{text}</p></div>')
    html('<div class="closing"><div class="overline" style="color:#aaa">A SMALL ACTION. A CLEARER PATH.</div><h2>Better roads begin<br>with better reporting.</h2><p>Try the local prototype. Every demonstration report stays in this installation.</p></div>')
    if st.button("Try the Prototype ↗", type="primary", key="final_cta"): go("report")
