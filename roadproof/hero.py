"""A self-contained, accessible comparison in the existing landing hero."""
import base64
from functools import lru_cache
from pathlib import Path

import streamlit as st


@lru_cache(maxsize=2)
def image_url(name):
    path = Path(__file__).resolve().parents[1] / "assets" / "hero" / name
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode()


def render_hero():
    before = image_url("road-before.jpg")
    after = image_url("road-after.jpg")
    st.html(f'''
    <section class="hero">
      <div><div class="overline">SMARTER ROADS. SAFER CITIES.</div>
      <h1>See a pothole.<br>Start a <em>solution.</em></h1>
      <p>Turn a pothole photograph into a trackable road-maintenance report. Pin the location. Follow the repair. Review the evidence.</p></div>
      <div class="hero-visual road-comparison" id="roadproof-comparison">
        <div class="comparison-header"><span>ONE ROAD. A BETTER OUTCOME.</span><span>01 / 02</span></div>
        <div class="comparison-scene" style="--split:50%">
          <img class="comparison-photo" src="{after}" alt="Generated demonstration of a flat asphalt repair patch." draggable="false">
          <div class="comparison-before"><img class="comparison-photo" src="{before}" alt="Generated demonstration of the same road with an open pothole." draggable="false"></div>
          <span class="comparison-tag before-tag">BEFORE / REPORTED</span>
          <span class="comparison-tag after-tag">AFTER / REPAIRED</span>
          <div class="comparison-divider" aria-hidden="true"><span>‹ ›</span></div>
          <input class="comparison-range" type="range" min="0" max="100" value="50" aria-label="Compare road before and after repair" aria-valuetext="50% before, 50% after">
        </div>
        <div class="comparison-footer"><strong>From road damage to repair.</strong><span>Drag to compare <span aria-hidden="true">↔</span></span></div>
        <div class="comparison-disclosure">AI-GENERATED DEMONSTRATION · NOT ACTUAL REPAIR EVIDENCE</div>
      </div>
    </section>
    <script>
    (() => {{
      const panel = document.getElementById('roadproof-comparison');
      if (!panel) return;
      const range = panel.querySelector('.comparison-range');
      const scene = panel.querySelector('.comparison-scene');
      const update = () => {{
        const value = Number(range.value);
        scene.style.setProperty('--split', value + '%');
        range.setAttribute('aria-valuetext', value + '% before, ' + (100 - value) + '% after');
      }};
      range.addEventListener('input', update);
      update();
    }})();
    </script>
    ''', unsafe_allow_javascript=True)
