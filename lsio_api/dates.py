"""The two timestamp formats: ISO 8601 (data/, status.json) and the original API's str(datetime)."""

import datetime


def parse_iso(timestamp: str | None) -> datetime.datetime | None:
    """Either format, or None when it is empty or doesn't parse."""
    try:
        return datetime.datetime.fromisoformat(timestamp) if timestamp else None
    except ValueError:
        return None


def python_timestamp(timestamp: str | None) -> str:
    """ "2026-10-24T11:25:58.123Z" -> "2026-10-24 11:25:58+00:00", as the original API formats times."""
    when = parse_iso(timestamp)
    return str(when.astimezone(datetime.UTC).replace(microsecond=0)) if when else ""
