"""Field-type lookup helpers.

The static 40-field catalog from the original `jsm_db.py` is gone — each Jira
instance now caches its own field list (see `JiraInstanceField`). This module just
holds small lookup helpers that read the per-instance field info from the DB.
"""
from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session

from .models import JiraInstance, JiraInstanceField


# A handful of fields we always need, in addition to whatever the user selected.
# These are not in the selectable field list — they drive the system spine of
# every report table.
SYSTEM_FIELDS: tuple[str, ...] = ("issue_key", "jira_created", "jira_updated", "fetched_at")


def get_field_types_for_instance(db: Session, instance_id: int) -> dict[str, dict]:
    """Return {field_id: {name, type, is_custom, schema_type}} for the instance."""
    rows = (
        db.query(JiraInstanceField)
        .filter(JiraInstanceField.jira_instance_id == instance_id)
        .all()
    )
    return {
        r.field_id: {
            "name": r.name,
            "type": r.field_type,
            "is_custom": r.is_custom,
            "schema_type": r.schema_type,
        }
        for r in rows
    }


def sql_type_for(field_id: str, field_type: str | None) -> str:
    """Map an app-level field type to a MySQL column type."""
    if field_type == "text":
        return "TEXT"
    if field_type == "number":
        return "FLOAT"
    if field_type == "datetime":
        return "DATETIME"
    return "VARCHAR(255)"


def normalize_selected_fields(
    selected: Iterable[str], field_types: dict[str, dict]
) -> list[str]:
    """Strip the system spine column names from the user selection and return the
    remaining field ids in the user's order. Unknown ids (not in the cache) are
    kept so the user can still see them in the UI even if Jira returned no
    metadata for them — they'll be defaulted to VARCHAR(255) / "string".

    Note: "created" and "updated" are user-selectable Jira field ids; they're
    NOT stripped here. The view aliases `t.jira_created AS created` /
    `t.jira_updated AS updated` so the user's position is preserved.
    """
    skip = {"issue_key", "key", "jira_created", "jira_updated", "fetched_at"}
    out: list[str] = []
    seen: set[str] = set()
    for fid in selected:
        if fid in skip or fid in seen:
            continue
        seen.add(fid)
        out.append(fid)
    return out
