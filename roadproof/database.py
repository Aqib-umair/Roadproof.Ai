"""SQLite persistence, private tracking, and append-only application audit history."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
from pathlib import Path
import secrets
import sqlite3
import uuid

from .images import road_illustration, save_image

STATUSES = ["Reported", "Under Review", "Assigned", "Repair in Progress",
            "Repair Claimed Complete", "Verification Pending", "Verified and Closed", "Reopened"]
TRANSITIONS = {
    "Reported": ["Under Review"],
    "Under Review": ["Assigned"],
    "Assigned": ["Repair in Progress"],
    "Repair in Progress": ["Repair Claimed Complete"],
    "Repair Claimed Complete": ["Verification Pending"],
    "Verification Pending": [],
    "Verified and Closed": [],
    "Reopened": ["Under Review", "Assigned", "Repair in Progress"],
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def token_hash(token):
    return hashlib.sha256(token.strip().encode()).hexdigest()


class Database:
    backend = "sqlite"

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    lat REAL NOT NULL, lon REAL NOT NULL, location TEXT NOT NULL,
                    description TEXT NOT NULL, image_path TEXT NOT NULL,
                    status TEXT NOT NULL, ai_status TEXT NOT NULL, model TEXT NOT NULL,
                    analysis_json TEXT NOT NULL DEFAULT '[]',
                    measurements_json TEXT, cost_json TEXT,
                    email TEXT, consent INTEGER NOT NULL DEFAULT 0,
                    synthetic INTEGER NOT NULL DEFAULT 0,
                    evidence_path TEXT, repair_claim_at TEXT, verified_at TEXT
                );
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_id TEXT NOT NULL REFERENCES reports(id),
                    created_at TEXT NOT NULL, status TEXT NOT NULL,
                    action TEXT NOT NULL, note TEXT NOT NULL, actor TEXT NOT NULL,
                    evidence_path TEXT
                );
                CREATE INDEX IF NOT EXISTS history_report ON history(report_id, id);
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(str(self.path), timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def create_report(self, *, token, lat, lon, location, description, image_path,
                      ai_status, model="Not connected", detections=None,
                      measurements=None, cost=None, email="", consent=False,
                      synthetic=False, created_at=None):
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Coordinates are outside the valid range.")
        if len(description.strip()) < 10 or len(description) > 2000:
            raise ValueError("Describe the damage in 10–2,000 characters.")
        if not Path(image_path).is_file():
            raise ValueError("The report image is missing.")
        if len(token) < 32:
            raise ValueError("A secure tracking token is required.")
        timestamp = created_at or now()
        report_id = "RP-" + uuid.uuid4().hex[:10].upper()
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM reports WHERE token_hash=?", (token_hash(token),)).fetchone()
            if existing:
                return existing["id"]
            conn.execute("""INSERT INTO reports
                (id,token_hash,created_at,updated_at,lat,lon,location,description,image_path,
                 status,ai_status,model,analysis_json,measurements_json,cost_json,email,consent,synthetic)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (report_id, token_hash(token), timestamp, timestamp, lat, lon,
                 location.strip()[:160] or "Selected map location", description.strip(), image_path,
                 "Reported", ai_status, model, json.dumps(detections or []),
                 json.dumps(measurements) if measurements else None,
                 json.dumps(cost) if cost else None, email.strip() if consent else "", int(consent), int(synthetic)))
            self._audit(conn, report_id, "Reported", "Report recorded",
                        "Synthetic demonstration record." if synthetic else "Citizen report recorded locally; no government submission.",
                        "Demo seed" if synthetic else "Citizen", timestamp=timestamp)
        return report_id

    def _audit(self, conn, report_id, status, action, note, actor, evidence=None, timestamp=None):
        conn.execute("""INSERT INTO history (report_id,created_at,status,action,note,actor,evidence_path)
                     VALUES (?,?,?,?,?,?,?)""", (report_id, timestamp or now(), status, action, note, actor, evidence))

    def by_token(self, token):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM reports WHERE token_hash=?", (token_hash(token),)).fetchone()
            return dict(row) if row else None

    def get(self, report_id):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
            return dict(row) if row else None

    def public_reports(self):
        # Deliberately omit photographs, description, tokens, and contact information.
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("""SELECT id,created_at,updated_at,lat,lon,
                location,status,ai_status,synthetic FROM reports ORDER BY created_at DESC""")]

    def history(self, report_id):
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM history WHERE report_id=? ORDER BY id", (report_id,))]

    def update_status(self, report_id, status, note, *, authorized=False, expected_status=None):
        if not authorized:
            raise PermissionError("Administrator access required.")
        if not note.strip():
            raise ValueError("Add a reason for this status change.")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            report = conn.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
            if report is None:
                raise ValueError("Report not found.")
            if expected_status and report["status"] != expected_status:
                raise ValueError("This case changed in another session. Refresh and review its latest status.")
            if status not in TRANSITIONS[report["status"]]:
                raise ValueError("Use the next workflow stage. Closure and reopening require a reviewer decision.")
            if status in {"Repair Claimed Complete", "Verification Pending"} and not report["evidence_path"]:
                raise ValueError("Upload repair evidence before recording a repair claim.")
            timestamp = now()
            conn.execute("UPDATE reports SET status=?,updated_at=?,repair_claim_at=CASE WHEN ?='Repair Claimed Complete' THEN ? ELSE repair_claim_at END WHERE id=?",
                         (status, timestamp, status, timestamp, report_id))
            self._audit(conn, report_id, status, "Status changed", note.strip()[:2000], "Demo administrator")

    def add_evidence(self, report_id, path, note, *, authorized=False):
        if not authorized:
            raise PermissionError("Administrator access required.")
        if not Path(path).is_file() or not note.strip():
            raise ValueError("Provide a repair image and an evidence note.")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT status FROM reports WHERE id=?", (report_id,)).fetchone()
            if row is None:
                raise ValueError("Report not found.")
            if row["status"] == "Verified and Closed":
                raise ValueError("Reopen this case before replacing evidence.")
            conn.execute("UPDATE reports SET evidence_path=?,updated_at=? WHERE id=?", (path, now(), report_id))
            self._audit(conn, report_id, row["status"], "Repair evidence uploaded", note.strip()[:2000], "Demo administrator", path)

    def review(self, report_id, decision, note, *, authorized=False, attested=False, expected_status=None):
        if not authorized:
            raise PermissionError("Reviewer access required.")
        if not note.strip():
            raise ValueError("Add reviewer notes explaining your decision.")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            report = conn.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
            if report is None:
                raise ValueError("Report not found.")
            if expected_status and report["status"] != expected_status:
                raise ValueError("This case changed. Refresh before reviewing it.")
            if decision == "Mark Verified":
                if report["status"] != "Verification Pending" or not report["evidence_path"] or not attested:
                    raise ValueError("Verification requires a pending case, repair evidence, and your human-review confirmation.")
                status = "Verified and Closed"
            elif decision == "Request More Evidence":
                if report["status"] not in {"Repair Claimed Complete", "Verification Pending"}:
                    raise ValueError("More evidence can be requested after a repair has been claimed.")
                status = "Repair in Progress"
            elif decision == "Reopen Case":
                if report["status"] not in {"Verified and Closed", "Verification Pending", "Repair Claimed Complete"}:
                    raise ValueError("Reopening requires a claimed, pending, or closed case.")
                status = "Reopened"
            else:
                raise ValueError("Unknown reviewer decision.")
            timestamp = now()
            conn.execute("UPDATE reports SET status=?,updated_at=?,verified_at=? WHERE id=?",
                         (status, timestamp, timestamp if status == "Verified and Closed" else None, report_id))
            self._audit(conn, report_id, status, decision, note.strip()[:2000], "Human demo reviewer", report["evidence_path"])

    def feedback(self, token, note):
        if not 5 <= len(note.strip()) <= 2000:
            raise ValueError("Write feedback in 5–2,000 characters.")
        with self.connect() as conn:
            report = conn.execute("SELECT id,status FROM reports WHERE token_hash=?", (token_hash(token),)).fetchone()
            if not report:
                raise ValueError("Tracking access is invalid.")
            self._audit(conn, report["id"], report["status"], "Citizen feedback", note.strip(), "Citizen")

    def seed(self, image_directory):
        with self.connect() as conn:
            if conn.execute("SELECT 1 FROM metadata WHERE key='seed_v1'").fetchone():
                return
            # Reserve the seed once; a transaction ensures simultaneous sessions cannot duplicate it.
            conn.execute("INSERT OR IGNORE INTO metadata VALUES ('seed_v1','started')")
            if conn.execute("SELECT changes()").fetchone()[0] == 0:
                return
        before = save_image(road_illustration(), image_directory)
        after = save_image(road_illustration(True), image_directory)
        locations = [(15.8281, 78.0373, "Kurnool · demonstration site A"),
                     (15.8283, 78.0375, "Kurnool · demonstration site B"),
                     (15.8154, 78.0408, "Kurnool · demonstration site C"),
                     (15.8390, 78.0510, "Kurnool · demonstration site D"),
                     (15.8050, 78.0300, "Kurnool · demonstration site E"),
                     (15.8240, 78.0610, "Kurnool · demonstration site F")]
        targets = ["Reported", "Under Review", "Repair in Progress", "Verification Pending", "Verified and Closed", "Reopened"]
        for i, ((lat, lon, location), target) in enumerate(zip(locations, targets)):
            report_id = self.create_report(token=secrets.token_urlsafe(32), lat=lat, lon=lon,
                location=location, description="Synthetic road damage illustration for exploring the local demonstration workflow.",
                image_path=before, ai_status="AI module not connected", synthetic=True,
                created_at=(datetime.now(timezone.utc) - timedelta(days=6-i)).isoformat(timespec="seconds"))
            route = STATUSES[:STATUSES.index(target)+1] if target != "Reopened" else STATUSES[:7]
            for status in route[1:]:
                if status == "Repair Claimed Complete":
                    self.add_evidence(report_id, after, "Synthetic repair illustration; not field evidence.", authorized=True)
                if status == "Verified and Closed":
                    self.review(report_id, "Mark Verified", "Seeded human-review example. No real-world repair is certified.", authorized=True, attested=True)
                else:
                    self.update_status(report_id, status, "Seeded demonstration workflow milestone.", authorized=True)
            if target == "Reopened":
                self.review(report_id, "Reopen Case", "Synthetic example: reviewer requested a further inspection.", authorized=True)


def duplicate_pairs(reports, radius_m=40):
    pairs = []
    for i, a in enumerate(reports):
        for b in reports[i+1:]:
            # Keep seeded examples separate from citizen submissions.
            if a["synthetic"] != b["synthetic"]:
                continue
            lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
            dlat, dlon = lat2-lat1, math.radians(b["lon"]-a["lon"])
            h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
            distance = 6371000 * 2 * math.asin(min(1, math.sqrt(h)))
            if distance <= radius_m:
                pairs.append((a["id"], b["id"], round(distance)))
    return pairs
