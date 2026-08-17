"""Date helpers — no timezone conversion.

Jira is assumed to already return IST strings (with or without an offset). We just
parse the string to a naive datetime and store/format it as-is. No UTC math,
no offset rewriting, no `to_ist` step.
"""
from __future__ import annotations

from datetime import datetime

IST = "Asia/Kolkata"  # kept only as a label; not used for conversion anywhere.


def parse_jira_datetime(value: str | None) -> datetime | None:
    """Parse Jira's timestamp string and return a naive datetime.

    Accepts:
      - ISO 8601 with offset: "2025-12-19T11:00:00.000+0530"
      - ISO 8601 with Z:      "2025-12-19T11:00:00.000Z"
      - Space-separated:      "2025-12-19 11:00:00"
      - Date-only:            "2025-12-19"

    In every case the returned datetime is naive and equals the IST wall-clock Jira
    sent. No conversion is performed.
    """
    if not value:
        return None
    s = value.strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # Last-ditch: try the Jira "Z" form by stripping it first.
        try:
            dt = datetime.fromisoformat(s.replace("Z", ""))
        except ValueError:
            return None
    # If the string carried a tz offset, drop it so MySQL stores the IST wall-clock
    # exactly as Jira gave it.
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt


def format_ist(dt: datetime | None, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format a naive datetime as a plain string. No timezone math."""
    if dt is None:
        return ""
    return dt.strftime(fmt)
