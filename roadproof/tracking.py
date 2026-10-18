"""Resolve tracking inputs without granting private access from a public case ID."""
import re
from urllib.parse import parse_qs, urlsplit


def parse_reference(value):
    value = value.strip()
    if re.fullmatch(r"RP-[A-Fa-f0-9]{10}", value, re.IGNORECASE):
        return "report_id", value.upper()
    if "?" in value:
        try:
            values = parse_qs(urlsplit(value).query).get("token", [])
        except ValueError:
            return "invalid", ""
        if len(values) != 1:
            return "invalid", ""
        value = values[0].strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{32,128}", value):
        return "token", value
    return "invalid", ""


def remember_receipt(state, receipt):
    receipts = dict(state.get("my_reports", {}))
    receipts[receipt["id"]] = receipt["token"]
    state["my_reports"] = dict(list(receipts.items())[-20:])


def resolve_tracking(db, value, receipts=None, latest_receipt=None):
    kind, reference = parse_reference(value)
    if kind == "invalid":
        return None, "", "invalid"
    if kind == "report_id":
        # Only a token already held by this browser can unlock a report by its ID.
        token = (receipts or {}).get(reference)
        if not token and latest_receipt and latest_receipt.get("id") == reference:
            token = latest_receipt.get("token")
        if not token:
            return None, "", "id_requires_token"
        report = db.by_token(token)
        if not report or report["id"] != reference:
            return None, "", "not_found"
        return report, token, "found"
    report = db.by_token(reference)
    return report, reference if report else "", "found" if report else "not_found"
