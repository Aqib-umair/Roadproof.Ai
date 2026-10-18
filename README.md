# RoadProof AI

**Detect. Report. Track. Verify.** A local civic-tech prototype by Team 10x for the **SEVA First Innovation Challenge 2026**, Surakshit Bharat — Mobility, Infrastructure and Public Safety.

**S.MD.Aqib Umair · Shaik Arashad**  
Dr. K. V. Subba Reddy Institute of Technology, Kurnool, Andhra Pradesh.

**Supabase and reference-assisted AI update:** See [SETUP_SUPABASE_AI.md](SETUP_SUPABASE_AI.md) for the optional private cloud backend, pinned experimental ONNX model, reference-marker measurements and connection verification. The original SQLite mode and visual design remain available. Existing local records are not uploaded automatically. The sections below describe the baseline local mode; cloud/AI configuration overrides its disconnected defaults.

## Install and launch

Python 3.11 or newer recommended. From this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Open the local address printed by Streamlit (normally http://localhost:8501). No paid API keys or account signup are required. On systems where activation is restricted, run `.\.venv\Scripts\python.exe -m streamlit run app.py` directly after installing dependencies with that same Python executable.

## Demo administration

This installation uses **open demonstration mode**: select Demo Dashboard or Repair verification to view submitted photographs and use the prototype workflow directly. No password, unlock form or logout button is shown. The selected local setting is:

```toml
ROADPROOF_ADMIN_MODE = "demo"
```

Open demo mode intentionally lets visitors to this app see case photographs and make demonstration updates. Supabase credentials, email addresses and private tracking tokens are still kept out of those pages. Human review confirmation remains necessary for closure.

The optional password mode remains available for a protected installation. Set `ROADPROOF_ADMIN_MODE = "password"` in `.streamlit/secrets.toml`, and use your own strong password:

Create `.streamlit/secrets.toml` locally, using your own strong password:

```toml
ROADPROOF_ADMIN_MODE = "password"
admin_password = "choose-your-own-long-unique-password"
```

In password mode, alternatively set `ROADPROOF_ADMIN_PASSWORD` in your terminal environment before launch. The secrets file is ignored by Git. Open **Demo Dashboard → Administrator access** and enter your password. Sessions expire after one hour; the Lock button signs out. Five incorrect attempts trigger a one-minute cooldown in that browser session. A fresh installation defaults to password mode unless open demo mode is explicitly configured.

This is a **local demonstration gate**, not production identity management. Before public deployment add authenticated individual roles, shared rate limits, HTTPS, private media storage, backups, retention policies and tamper-resistant audit logging. Local file/database administrators can modify the installation; the audit trail is not cryptographically immutable. Do not expose this prototype directly to the internet with sensitive data.

## A five-minute judge walkthrough

1. Explore the landing page and five-step workflow. All illustrations are explicitly labelled synthetic.
2. Select **Report a Pothole**. Upload a JPG/PNG (up to 10 MB / 24 MP), or use your camera. Preview or replace the image.
3. Click the map or enter coordinates and **Confirm this location**. The initial map center is Kurnool, never inferred GPS.
4. Review the actual connected-model result, or the honest placeholder if no model is configured. The analysis button updates the annotated image, candidate count, photo resolution, confidence, detected bounding-box dimensions in pixels and predicted outline area. A zero-detection result is shown explicitly. Skip optional measurements, or use a reference marker / suitable on-site measurements as appropriate.
5. Add a description, acknowledge demo status and submit. Save the private tracking receipt. The code block's copy icon copies the link; a receipt download is also available.
6. Open **View report** to see the private timeline and leave feedback. An invalid token reveals no case. Report IDs alone do not grant tracking access.
7. Open **Demo Dashboard**, select the submitted photograph/case, then progress through Under Review → Assigned → Repair in Progress. No password is required in the configured demo mode.
8. Upload repair evidence with notes. Change to Repair Claimed Complete → Verification Pending.
9. Open **Repair verification**. Compare before/after images, write reviewer notes, select Mark Verified and confirm personal human review. Record the decision. Reopen or request more evidence when appropriate.

All decisions are local demo decisions. No screen or status is an official government complaint or road-repair certification.

## Working features

Tracking accepts a private token or the complete receipt link. In the browser that submitted a report, its ID can also open it using the private receipt already held in that session; an ID never unlocks a private case in a new browser. The success screen shows the reference ID and private access separately. Download the receipt before clearing the private session.

Use **Refresh reports** on the dashboard to read new database records, and **Clear dashboard filters** if a status, date, search or sample-only scope hides a case. Date filters use the same Indian calendar date shown in the interface. The photograph gallery opens directly in demo mode; in optional password mode it opens only after authentication. Any configured password stays in the ignored local settings file or environment, never in committed source.

- Warm-white, charcoal and orange editorial interface with responsive layouts, keyboard controls and reduced-motion support.
- Seven connected screens plus an interactive How It Works page.
- Session-preserved five-step citizen draft, validated image uploads/camera, manually confirmed location, optional measurements and transparent cost assumptions.
- SQLite reports, cryptographically random private tracking tokens (only SHA-256 hashes stored), idempotent submission, private feedback and ordered audit events.
- Six synthetic cases seeded once: reported, under review, repair in progress, verification pending, verified/closed and reopened.
- Actual database-derived counts, date/status filters, selectable case table and interactive status-aware map.
- Proximity-only duplicate suggestions within 40 metres; no automatic merging or fabricated AI results.
- Protected case management, evidence version history, reviewer decisions, timestamped notes and stale-status update protection.
- Final closure requires repair evidence, a pending case, a reviewer note and explicit human approval.

## AI and calculation limitations

Without model weights, the screen says **“AI detection module not connected — demonstration interface.”** This installation has an experimental local ONNX pothole segmentation model configured; see [SETUP_SUPABASE_AI.md](SETUP_SUPABASE_AI.md). The Run local model analysis button performs a new inference and updates the visible result in the same run. Empty results say how many candidates were found and at which threshold, and show measured image attributes plus image-quality guidance. There are no invented confidence values. Pixel bounding-box dimensions and outline area are derived from detector output, not inferred engineering measurements. Photo resolution, file size, brightness and contrast are calculated directly from the image. The result can be downloaded as JSON.

The app does not automatically fetch weights. ONNX uses requirements-ai.txt; operator-supplied trusted .pt weights require ultralytics separately. Labels, confidences, outlines and model identification are saved with the report. The annotated preview is session-only; the original image remains the persistent evidence. A known-size ArUco reference can support approximate road-plane extents in step 04, not depth or surveyed accuracy. Validate the model and measurements separately before making accuracy or safety claims.

Depth and exact dimensions cannot be inferred from an uncalibrated photograph. The optional illustration uses **length × width × depth / 1,000,000** to obtain cubic metres, multiplied by an editable rate and **1.15** waste factor. The default ₹8,000/m³ is a teaching assumption, not an approved rate. Labour, equipment, base preparation, traffic control, taxes and engineering assessment are excluded. Visual estimates never produce a cost allowance.

## Storage, privacy and connectivity

- Runtime records live in `data/roadproof.sqlite3`; cleaned JPEGs live in `data/images/`. Both are ignored by Git. Keep this directory private and back it up together. To reset this local demonstration, stop the app and move the entire data directory aside, then restart.
- Uploads are decoded, format/size checked, re-encoded and stripped of EXIF metadata. Original filenames are not used as storage paths.
- Email is optional and stored only with consent. Email delivery is not implemented. Overview queries exclude tokens/hashes, email, descriptions and evidence paths. The open demo workspace intentionally shows full case photographs/details; use password mode when those should be restricted to authenticated administrators and token holders.
- Tracking links are bearer access: anyone holding one can see that report and leave feedback. Save the receipt; raw tokens are not recoverable from the database. Query tokens are removed from the address bar after opening, but links may remain in browser/network history. Do not share them publicly.
- Drafts last only for the current Streamlit browser session; a disconnected/restarted session may lose an unsubmitted draft.
- Maps use public OpenStreetMap tiles and Folium frontend assets. Google Fonts supplies the requested typefaces. These need network access; fallback system fonts and manual coordinates remain available offline. Camera permissions/secure context depend on your browser; use file upload if unavailable.
- The default tracking URL is `http://localhost:8501`. Set `ROADPROOF_BASE_URL` to your actual local host/port if different. Use `ROADPROOF_DATA_DIR` for an alternate private data folder.
- There is no government integration, notification service, production authentication, automated repair verification or validated public-impact claim. Telugu and Hindi remain future work.

## Source layout

`app.py` handles navigation and page composition. `roadproof/` contains database, image validation, cost, authentication, detection adapter, landing, citizen, admin, reusable components and CSS modules. `.streamlit/config.toml` configures the visual theme and upload limit.

## Checks

```powershell
python -m unittest discover -s tests -v
```

Tests use disposable directories and exercise private tracking/redaction, idempotent submission, protected mutations, workflow restrictions, evidence, human verification/reopening, audit history, seed records, proximity suggestions, costs, image validation, page startup and the citizen submission journey. Browser QA should also check file/camera upload, actual map clicks, copy controls and narrow-screen layouts because Streamlit's test harness does not emulate browser components.
