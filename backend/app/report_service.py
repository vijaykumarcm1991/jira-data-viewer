"""Schema management for per-report tables and views.

Each report owns a physical table `report_<id>` and a view `v_report_<id>_latest`.
The table holds the full history (rows with the same `issue_key` but different
`jira_updated` are kept). The view returns only the latest row per `issue_key`.

On report edit we add new columns (don't drop removed ones — history is preserved) and
recreate the view to match the new selected-field order.

Field SQL types come from the per-instance field cache (`JiraInstanceField`).
"""
from __future__ import annotations

import re
from typing import Iterable

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from .database import SessionLocal, engine
from .field_catalog import (
    get_field_types_for_instance,
    normalize_selected_fields,
    sql_type_for,
)
from .models import Report

_SAFE_ID = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def _validate_field_ids(field_ids: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for fid in field_ids:
        if not _SAFE_ID.match(fid):
            raise ValueError(f"Invalid field id: {fid!r}")
        if fid in seen:
            continue
        seen.add(fid)
        out.append(fid)
    return out


def table_name(report_id: int) -> str:
    if not isinstance(report_id, int) or report_id <= 0:
        raise ValueError("report_id must be a positive integer")
    return f"report_{report_id}"


def view_name(report_id: int) -> str:
    return f"v_report_{report_id}_latest"


def create_report_table_and_view(report_id: int, selected_fields: list[str]) -> None:
    """Create the per-report table and its latest view. Idempotent for the table."""
    with SessionLocal() as db:
        report = db.query(Report).get(report_id)
        field_types = get_field_types_for_instance(db, report.jira_instance_id) if report else {}

    selected = _validate_field_ids(selected_fields)
    cols = _build_columns(selected, field_types)
    col_defs = ",\n  ".join(f"`{name}` {typ}" for name, typ in cols)
    indexes = (
        "INDEX `idx_issue_key` (`issue_key`),\n"
        "  INDEX `idx_jira_created` (`jira_created`),\n"
        "  INDEX `idx_jira_updated` (`jira_updated`)"
    )
    sql = f"""
CREATE TABLE IF NOT EXISTS `{table_name(report_id)}` (
  {col_defs},
  {indexes}
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""
    with engine.begin() as conn:
        conn.execute(text(sql))
    _recreate_view(report_id, selected)


def _build_columns(selected_fields: Iterable[str], field_types: dict[str, dict]) -> list[tuple[str, str]]:
    """Build (name, type) tuples for the physical table."""
    cols: list[tuple[str, str]] = [
        ("id", "INT AUTO_INCREMENT PRIMARY KEY"),
        ("issue_key", "VARCHAR(50) NOT NULL"),
        ("jira_created", "DATETIME NOT NULL"),
        ("jira_updated", "DATETIME NOT NULL"),
        ("fetched_at", "DATETIME NOT NULL"),
    ]
    spine_aliases = {"issue_key", "created", "updated", "key", "jira_created", "jira_updated", "fetched_at"}
    for fid in selected_fields:
        if fid in spine_aliases:
            continue
        ftype = field_types.get(fid, {}).get("type", "string")
        cols.append((fid, sql_type_for(fid, ftype)))
    return cols


def add_columns(report_id: int, new_field_ids: list[str]) -> None:
    """ALTER TABLE ADD COLUMN for any field that doesn't yet have a column."""
    new_fields = _validate_field_ids(new_field_ids)
    if not new_fields:
        return
    with SessionLocal() as db:
        report = db.query(Report).get(report_id)
        field_types = get_field_types_for_instance(db, report.jira_instance_id) if report else {}
    insp = inspect(engine)
    existing = {c["name"] for c in insp.get_columns(table_name(report_id))}
    statements: list[str] = []
    for fid in new_fields:
        if fid in existing:
            continue
        ftype = field_types.get(fid, {}).get("type", "string")
        col_type = sql_type_for(fid, ftype)
        statements.append(
            f"ALTER TABLE `{table_name(report_id)}` ADD COLUMN `{fid}` {col_type} NULL"
        )
    if statements:
        with engine.begin() as conn:
            for s in statements:
                conn.execute(text(s))


def widen_columns_if_needed(
    report_id: int, selected: list[str], field_types: dict[str, dict]
) -> None:
    """ALTER TABLE MODIFY COLUMN for any column whose current SQL type no longer
    matches the field's detected type. This is what heals reports created before
    a long-text field was re-detected as "text" instead of "string".
    """
    insp = inspect(engine)
    if not insp.has_table(table_name(report_id)):
        return
    existing_types = {c["name"]: str(c["type"]).upper() for c in insp.get_columns(table_name(report_id))}
    statements: list[str] = []
    for fid in selected:
        if fid in {"issue_key", "jira_created", "jira_updated", "fetched_at"}:
            continue
        ftype = field_types.get(fid, {}).get("type", "string")
        want = sql_type_for(fid, ftype).upper()
        have = existing_types.get(fid)
        if have is None or have == want:
            continue
        # Only widen: going from a tighter type (VARCHAR(255)) to a looser
        # type (TEXT) is safe; the other direction could lose data.
        if want == "TEXT" and "VARCHAR" not in have and "CHAR" not in have and have != "TEXT":
            continue
        if want == "TEXT" and have == "TEXT":
            continue
        statements.append(
            f"ALTER TABLE `{table_name(report_id)}` MODIFY COLUMN `{fid}` {want} NULL"
        )
    if statements:
        with engine.begin() as conn:
            for s in statements:
                conn.execute(text(s))


def update_view(report_id: int, selected_fields: list[str]) -> None:
    """Recreate the latest view to match the given field order."""
    selected = _validate_field_ids(selected_fields)
    _recreate_view(report_id, selected)


def _recreate_view(report_id: int, selected_fields: list[str]) -> None:
    """Build and execute CREATE OR REPLACE VIEW for the latest snapshot.

    Column ordering honors the user's selected_fields order. When the user
    includes "created" or "updated", those are aliased to the system columns
    *in the user's position* (not appended at the end). Three hidden columns
    (prefixed with `_`) are always included for internal use:
      - _jira_created : for the date slicer's WHERE clause
      - _jira_updated : for the latest-row subquery
      - _fetched_at   : for the latest-row tiebreak
    """
    selected = _validate_field_ids(selected_fields)

    view_cols: list[str] = ["t.`issue_key` AS `issue_key`"]
    seen: set[str] = {"issue_key"}

    has_user_created = "created" in selected
    has_user_updated = "updated" in selected

    for fid in selected:
        if fid in seen:
            continue
        if fid in ("key", "issuekey"):
            # `key` and `issuekey` are user-selectable aliases for issue.key.
            view_cols.append(f"t.`issue_key` AS `{fid}`")
            seen.add(fid)
            continue
        if fid == "created":
            view_cols.append("t.`jira_created` AS `created`")
            seen.add("created")
            continue
        if fid == "updated":
            view_cols.append("t.`jira_updated` AS `updated`")
            seen.add("updated")
            continue
        view_cols.append(f"t.`{fid}` AS `{fid}`")
        seen.add(fid)

    # If the user did NOT pick "created", expose jira_created under its system
    # name so the frontend's "Created (IST)" column still has data.
    if not has_user_created:
        view_cols.append("t.`jira_created` AS `jira_created`")

    # Hidden system columns (stripped from API responses by `_row_to_dict`).
    view_cols.append("t.`jira_created` AS `_jira_created`")
    view_cols.append("t.`jira_updated` AS `_jira_updated`")
    view_cols.append("t.`fetched_at` AS `_fetched_at`")

    col_list = ",\n  ".join(view_cols)
    sql = f"""
CREATE OR REPLACE VIEW `{view_name(report_id)}` AS
SELECT
  {col_list}
FROM `{table_name(report_id)}` t
INNER JOIN (
  SELECT `issue_key`, MAX(`jira_updated`) AS max_updated, MAX(`fetched_at`) AS max_fetched
  FROM `{table_name(report_id)}`
  GROUP BY `issue_key`
) latest
  ON t.`issue_key`   = latest.`issue_key`
 AND t.`jira_updated` = latest.`max_updated`
 AND t.`fetched_at`   = latest.`max_fetched`
"""
    with engine.begin() as conn:
        conn.execute(text(sql))


def drop_report(report_id: int) -> None:
    """Drop the view and table for a report. Used on hard delete."""
    with engine.begin() as conn:
        conn.execute(text(f"DROP VIEW IF EXISTS `{view_name(report_id)}`"))
        conn.execute(text(f"DROP TABLE IF EXISTS `{table_name(report_id)}`"))


def ensure_schema_matches_report(report: Report) -> None:
    """Reconcile the physical schema with a Report row.

    - Creates the table if missing
    - Adds columns for any newly-selected fields
    - Widens existing columns whose SQL type has changed (e.g. when a field's
      type is re-detected as "text" after the cache is refreshed)
    - Recreates the view with the current field order

    Safe to call repeatedly.
    """
    with SessionLocal() as db:
        field_types = get_field_types_for_instance(db, report.jira_instance_id)
    selected = normalize_selected_fields(
        report.selected_fields or [],
        field_types,
    )
    insp = inspect(engine)
    if not insp.has_table(table_name(report.id)):
        create_report_table_and_view(report.id, list(report.selected_fields or []))
        return
    add_columns(report.id, list(report.selected_fields or []))
    widen_columns_if_needed(report.id, selected, field_types)
    update_view(report.id, list(report.selected_fields or []))
