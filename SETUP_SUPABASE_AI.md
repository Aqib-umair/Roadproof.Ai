# Connect Supabase and enable experimental pothole analysis

The interface and visual design are preserved. SQLite remains usable until an operator explicitly selects Supabase. **Prepared integration is not a verified live connection.** A real Supabase project and server-only credentials are needed for the cloud round trip.

## 1. Create your project

Sign into [Supabase Dashboard](https://supabase.com/dashboard) and create a project named RoadProof AI in your organization. Choose an available region close to your expected users. Save its database password in your password manager. Do not send passwords or secret keys through chat. Wait for provisioning to finish.

Only the Project URL can be shared here. The app itself needs a **server secret API key**, entered locally in the next step. It does not need your account password or database password. A publishable/anon key is insufficient for this server-only adapter. See [Supabase's API key guidance](https://supabase.com/docs/guides/getting-started/api-keys).

## 2. Prepare tables and private image storage

Open your project's SQL Editor. Paste and run the complete contents of `supabase/schema.sql`.

It creates `rp_reports`, `rp_history`, a private `roadproof-evidence` bucket and three transaction-backed functions. Table access and function execution are revoked from public, anon and authenticated roles. Only the server service role is granted application access. Report changes and audit events happen in a single PostgreSQL transaction. Row locking protects against conflicting status updates; hashed-token locking makes submission retries idempotent.

Do not make this bucket public or add public-read policies. The app downloads evidence on its Python server only after its existing tracking/admin access checks. The secret key must never be sent to browser code. See [private buckets](https://supabase.com/docs/guides/storage/buckets/fundamentals) and [database functions](https://supabase.com/docs/guides/database/functions).

## 3. Enter the connection privately

Install the optional backend dependencies:

```powershell
python -m pip install -r requirements-supabase.txt
```

Edit `.streamlit/secrets.toml` locally. An example file is supplied at `.streamlit/secrets.toml.example`. Keep any existing `admin_password` and `ROADPROOF_YOLO_WEIGHTS` settings. Set:

```toml
ROADPROOF_BACKEND = "supabase"
SUPABASE_URL = "https://YOUR-PROJECT-REF.supabase.co"
SUPABASE_SECRET_KEY = ""
```

Paste your real server secret key between the final quotation marks **in that local file only**. Find it in your project Settings → API Keys. This file is ignored by Git. Environment variables with the same names take precedence. Restart Streamlit after configuration.

```powershell
python scripts/check_supabase.py
streamlit run app.py
```

The check is read-only. The app's small demonstration indicator changes to SUPABASE STORAGE when that backend is selected; selection alone does not prove connectivity. Verify a complete round trip by submitting one harmless test photograph, checking the row in `rp_reports` and the image in the private bucket, then opening its private tracking receipt and the dashboard. Test an evidence upload, status progression and human review before inviting users. Do not enable public bucket access to fix a failing download.

Existing SQLite reports remain on this computer and are **not automatically migrated or uploaded**. Their old tracking receipts work only while the app uses that original database. Back it up before changing backends. Synthetic samples are not implicitly uploaded to the new project.

If a cloud request fails, the app preserves the draft and does not fall back silently to SQLite. Retrying the same submission token returns the same report ID. Storage upload and report transactions are separate; interrupted uploads may leave unused private objects. An operator should review orphaned uploads before deleting them. A network failure after a commit must not trigger automatic removal of an image the committed report may reference.

## 4. Experimental detector

Research identified the [keremberke YOLOv8n pothole segmentation model](https://huggingface.co/keremberke/yolov8n-pothole-segmentation) and a [community ONNX export](https://huggingface.co/seanjudelyons/yolov8n-pothole-segmentation-onnx). The export supplies one pothole class and segmentation masks. A pinned revision, checksum and observed tensor shapes are recorded in `models/research-model.json`.

The ONNX publisher has no model card or stated license. Its precise provenance, licensing and training data need clarification before public deployment or redistribution. It is a **research candidate**, not a validated RoadProof model. Publisher-reported metrics are not reproduced or shown as RoadProof accuracy. No third-party Python model repository code or pickle checkpoint is loaded by the ONNX adapter.

```powershell
python -m pip install -r requirements-ai.txt
python scripts/download_research_model.py
```

To enable the downloaded candidate locally, add its full path to `.streamlit/secrets.toml` using forward slashes:

```toml
ROADPROOF_YOLO_WEIGHTS = "E:/path/to/roadproofsi/models/pothole-research.onnx"
```

Restart Streamlit. In the existing reporting workflow, entering step 03 automatically performs actual local CPU inference once per uploaded image. The image shows predicted outlines, boxes and actual confidence values. A manual run button remains available. Failure preserves the photograph and permits human review. No cloud AI API or per-image payment is required. The model does not certify severity, repair need or a safe road.

Before judging model accuracy, assemble representative local road images with independent annotations, including potholes, shadows, puddles, patches and intact roads. Measure false positives, missed damage and segmentation quality. Evaluate separately from training data. Runtime smoke tests on synthetic images establish execution only.

## 5. Reference-marker measurements

The upload screen has a small expandable reference guide and marker download. It uses **ArUco DICT_4X4_50, marker ID 0**, generated with [OpenCV](https://docs.opencv.org/4.x/d5/dae/tutorial_aruco_detection.html).

1. Print the marker with a clear white border. Measure the **outer black square's side length**, not the whole sheet. Printing scale is never assumed.
2. From a safe position, place one marker flat beside the damage on the same approximate road plane. All four corners and the pothole must be visible. Keep it nearby and take a near-overhead photo. Do not enter traffic to do this.
3. Complete location and actual segmentation. In step 04 select **Reference marker estimate**, choose a detected pothole, enter the measured marker side and confirm its placement.
4. The prototype detects the marker corners and projects the detected outline onto the marker's plane. It reports approximate surface length/width and stores its method, scale and limitations with the report.

**It does not measure depth.** Slopes, lens distortion, oblique views, marker placement, distance and segmentation errors can substantially change estimates. The UI rejects some unsuitable inputs but cannot independently verify road flatness or physical marker size. No engineering tolerance is claimed. These unvalidated image estimates do not generate a repair-cost calculation. Suitable on-site/calibrated measurements, including separately measured depth, can still use the original calculator.

## Remaining production work

The current local installation uses `ROADPROOF_ADMIN_MODE = "demo"`, opening case photographs and demonstration management without a password. Optional `"password"` mode restores the local gate. Before public use with sensitive records, use authenticated individual administrator/reviewer identities, shared login and abuse limits, user-data retention/deletion, monitoring, backups and secure hosting. Supabase handles remote storage; it does not by itself deploy Streamlit or validate the AI. Government integration and email notifications remain unconnected.
