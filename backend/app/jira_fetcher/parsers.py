"""Field parsers for Jira REST API responses.

These handle the three shapes Jira returns:
  - ISO-8601 datetime strings ("created", "updated", "resolutiondate", custom dates)
  - ADF (Atlassian Document Format) for rich text fields like "summary_details"
  - Option/select/user objects with "value" / "name" / "displayName"
  - Lists of the above (multi-select, multi-user, etc.)
"""
from __future__ import annotations

from ..timezone import parse_jira_datetime

__all__ = [
    "parse_jira_datetime",
    "extract_adf_text",
    "extract_option_value",
    "extract_issue_fields",
]


def extract_adf_text(node) -> str:
    """Recursively parse an ADF JSON tree into plain text."""
    if not node:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        if "content" in node and isinstance(node["content"], list):
            return "".join(extract_adf_text(child) for child in node["content"])
    elif isinstance(node, list):
        return "".join(extract_adf_text(child) for child in node)
    return ""


def extract_option_value(field_value) -> str | None:
    """Convert any Jira field value to a flat string (or None).

    Handles:
      - None → None
      - ADF document → flattened text
      - Option/user dict → "value" / "name" / "displayName" (first truthy)
      - List of any of the above → ", "-joined
      - Everything else → str(value)
    """
    if field_value is None:
        return None

    if isinstance(field_value, dict):
        if field_value.get("type") == "doc":
            text = extract_adf_text(field_value).strip()
            return text if text else None
        return (
            field_value.get("value")
            or field_value.get("name")
            or field_value.get("displayName")
        )

    if isinstance(field_value, list):
        items = [extract_option_value(i) for i in field_value if i is not None]
        items = [str(i) for i in items if i]
        return ", ".join(items) if items else None

    return str(field_value)


def extract_issue_fields(
    issue: dict,
    selected_field_ids: list[str],
    field_types: dict[str, dict] | None = None,
) -> dict:
    """Map a Jira issue JSON object to a flat dict keyed by catalog field ids.

    Always returns `issue_key`, `jira_created`, `jira_updated` (system spine). The
    remaining keys are exactly the requested field ids, with values typed per the
    per-instance field cache (`field_types` — falls back to "string" for unknown).
    """
    field_types = field_types or {}
    f = issue.get("fields", {}) or {}
    result: dict = {}

    issue_key = issue.get("key")
    jira_created = parse_jira_datetime(f.get("created"))
    jira_updated = parse_jira_datetime(f.get("updated"))
    result["issue_key"] = issue_key
    result["jira_created"] = jira_created
    result["jira_updated"] = jira_updated

    for fid in selected_field_ids:
        if fid in {"issue_key", "jira_created", "jira_updated"}:
            continue
        # The Jira "key" field (and the legacy "issuekey" alias from the
        # original jsm_db.py) live on `issue.key`, not in `issue.fields.*`.
        # Materialize them as the issue key so they show up in the row.
        if fid in ("key", "issuekey"):
            result[fid] = issue_key
            continue
        raw = f.get(fid)
        ftype = field_types.get(fid, {}).get("type", "string")
        if ftype in ("string", "text"):
            result[fid] = extract_option_value(raw)
        elif ftype == "datetime":
            result[fid] = parse_jira_datetime(raw)
        elif ftype == "number":
            if isinstance(raw, (int, float)):
                result[fid] = float(raw)
            else:
                result[fid] = None
        else:
            result[fid] = extract_option_value(raw)
    return result
