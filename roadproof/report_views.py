"""Shared dashboard filters; reporting dates follow the India-facing interface."""
from datetime import datetime, timedelta, timezone

INDIA_TIME = timezone(timedelta(hours=5, minutes=30))


def submission_date(timestamp):
    return datetime.fromisoformat(timestamp).astimezone(INDIA_TIME).date()


def filter_reports(reports, scope="All records", statuses=(), dates=(), query=""):
    scoped = [r for r in reports if scope == "All records" or bool(r["synthetic"]) == (scope == "Synthetic samples")]
    filtered = [r for r in scoped if not statuses or r["status"] in statuses]
    if len(dates) == 2:
        filtered = [r for r in filtered if dates[0] <= submission_date(r["created_at"]) <= dates[1]]
    query = query.strip().casefold()
    if query:
        filtered = [r for r in filtered if query in r["id"].casefold() or query in r["location"].casefold()]
    return scoped, filtered
