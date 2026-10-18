"""Supabase adapter. Only Streamlit's Python server holds this privileged client."""
import json
from pathlib import Path
import uuid

from .database import now, token_hash
from .settings import backend_settings

PUBLIC_FIELDS = "id,created_at,updated_at,lat,lon,location,status,ai_status,synthetic"


def make_client(settings):
    try:
        from supabase import create_client
        from supabase.client import ClientOptions
    except ImportError:
        raise ValueError("Install requirements-supabase.txt before enabling Supabase.") from None
    return create_client(settings.url, settings.secret, options=ClientOptions(
        postgrest_client_timeout=20, storage_client_timeout=30,
        auto_refresh_token=False, persist_session=False))


def cloud_error(exc):
    # Do not expose raw SDK errors, request headers, credentials, or report payloads.
    code = str(getattr(exc, "code", ""))
    message = str(getattr(exc, "message", ""))
    allowed = ["Report not found.", "This case changed. Refresh before updating it.",
               "Use the next workflow stage.", "Repair evidence is required.",
               "Add a reason for this change.", "Verification requires pending evidence and human approval.",
               "Reopen this case before replacing evidence.", "This decision is not available for the current status.",
               "Tracking access is invalid.", "Invalid report data."]
    if code == "P0001" and message in allowed:
        raise ValueError(message) from None
    raise OSError("Supabase could not complete this operation. Check the connection and project setup. Your draft has been kept; retry using the same draft.") from None


def normalize(row):
    if row is None:
        return None
    row = dict(row)
    for key in ["analysis_json", "measurements_json", "cost_json"]:
        if key in row and row[key] is not None and not isinstance(row[key], str):
            row[key] = json.dumps(row[key])
    return row


class SupabaseDatabase:
    backend = "supabase"

    def __init__(self, settings=None, client=None):
        self.settings = settings or backend_settings()
        self.client = client if client is not None else make_client(self.settings)

    def seed(self, image_directory):
        # Never upload local reports or synthetic samples to a remote project implicitly.
        return

    def _rpc(self, name, payload):
        try:
            return self.client.rpc(name, payload).execute().data
        except Exception as exc:
            cloud_error(exc)

    def create_report(self, *, token, lat, lon, location, description, image_path,
                      ai_status, model="Not connected", detections=None,
                      measurements=None, cost=None, email="", consent=False,
                      synthetic=False, created_at=None):
        if not (-90 <= lat <= 90 and -180 <= lon <= 180) or not 10 <= len(description.strip()) <= 2000 or len(token) < 32:
            raise ValueError("Check the coordinates, description, and private tracking access.")
        if not image_path.startswith(f"supabase://{self.settings.bucket}/"):
            raise ValueError("The image must be saved to private Supabase storage first.")
        record = dict(id="RP-" + uuid.uuid4().hex[:10].upper(), token_hash=token_hash(token),
            created_at=created_at or now(), lat=lat,lon=lon,location=location.strip()[:160] or "Selected map location",
            description=description.strip(),image_path=image_path,ai_status=ai_status,model=model,
            analysis_json=detections or [],measurements_json=measurements,cost_json=cost,
            email=email.strip() if consent else "",consent=bool(consent),synthetic=bool(synthetic))
        return self._rpc("rp_create_report", {"p_report":record})

    def by_token(self, token):
        try:
            rows = self.client.table("rp_reports").select("*").eq("token_hash",token_hash(token)).limit(1).execute().data
            return normalize(rows[0]) if rows else None
        except Exception as exc:
            cloud_error(exc)

    def get(self, report_id):
        try:
            rows = self.client.table("rp_reports").select("*").eq("id",report_id).limit(1).execute().data
            return normalize(rows[0]) if rows else None
        except Exception as exc:
            cloud_error(exc)

    def _all(self, table, fields, order, report_id=None):
        rows = []
        try:
            while True:
                query = self.client.table(table).select(fields).order(order,desc=(table=="rp_reports"))
                if report_id:
                    query = query.eq("report_id",report_id)
                batch = query.range(len(rows),len(rows)+499).execute().data
                rows.extend(normalize(row) for row in batch)
                if len(batch) < 500:
                    return rows
        except Exception as exc:
            cloud_error(exc)

    def public_reports(self):
        return self._all("rp_reports",PUBLIC_FIELDS,"created_at")

    def history(self, report_id):
        return self._all("rp_history","*","id",report_id)

    def update_status(self, report_id, status, note, *, authorized=False, expected_status=None):
        if not authorized:
            raise PermissionError("Administrator access required.")
        return self._rpc("rp_update_case",dict(p_id=report_id,p_action="status",p_note=note,
            p_value=status,p_expected=expected_status,p_attested=False))

    def add_evidence(self, report_id, path, note, *, authorized=False):
        if not authorized:
            raise PermissionError("Administrator access required.")
        return self._rpc("rp_update_case",dict(p_id=report_id,p_action="evidence",p_note=note,
            p_value=path,p_expected=None,p_attested=False))

    def review(self, report_id, decision, note, *, authorized=False, attested=False, expected_status=None):
        if not authorized:
            raise PermissionError("Reviewer access required.")
        return self._rpc("rp_update_case",dict(p_id=report_id,p_action="review",p_note=note,
            p_value=decision,p_expected=expected_status,p_attested=attested))

    def feedback(self, token, note):
        return self._rpc("rp_add_feedback",dict(p_token_hash=token_hash(token),p_note=note))


class PrivateStorage:
    def __init__(self, settings=None, client=None):
        self.settings = settings or backend_settings()
        self.client = client if client is not None else make_client(self.settings)

    def _key(self, reference):
        prefix = f"supabase://{self.settings.bucket}/"
        if not reference.startswith(prefix):
            raise ValueError("This image is outside the configured private bucket.")
        key = reference[len(prefix):]
        if not key or ".." in key or "\\" in key or key.startswith("/"):
            raise ValueError("Invalid private image reference.")
        return key

    def upload(self, cleaned):
        key = f"evidence/{uuid.uuid4().hex}.jpg"
        try:
            self.client.storage.from_(self.settings.bucket).upload(key,cleaned,
                file_options={"content-type":"image/jpeg","upsert":"false"})
        except Exception as exc:
            cloud_error(exc)
        return f"supabase://{self.settings.bucket}/{key}"

    def download(self, reference):
        key = self._key(reference)
        # Reads are safe to retry once when the storage connection fails transiently.
        for attempt in range(2):
            try:
                return self.client.storage.from_(self.settings.bucket).download(key)
            except Exception as exc:
                if attempt:
                    cloud_error(exc)

    def remove(self, reference):
        key = self._key(reference)
        try:
            self.client.storage.from_(self.settings.bucket).remove([key])
        except Exception as exc:
            cloud_error(exc)
