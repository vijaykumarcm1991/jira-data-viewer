"""The sync service: pulls Jira data for one report and writes it to its `report_<id>`
table. Used by the APScheduler job, the "Run now" admin action, and the original
jsm_db.py CLI.

Commits one page at a time so the run history table can show live progress and
the user can see rows landing in MySQL during a long backfill (instead of
waiting for the entire transaction to commit at the end).
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Iterable, Iterator

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import engine
from ..field_catalog import (
    get_field_types_for_instance,
    normalize_selected_fields,
    sql_type_for,
)
from ..models import JiraInstance, JiraRunHistory, Report
from ..security import decrypt_token
from .client import fetch_and_extract


# In-memory registry of currently-running syncs. Maps run_id -> a threading.Event
# the running sync checks between pages. The admin UI can flip the event via
# POST /api/admin/runs/{id}/cancel to stop a long backfill cleanly.
_running_syncs: dict[int, threading.Event] = {}
_running_lock = threading.Lock()


def request_cancel(run_id: int) -> bool:
    """Signal the running sync for run_id to stop. Returns True if a sync was
    registered for that id, False if it had already finished."""
    with _running_lock:
        ev = _running_syncs.get(run_id)
        if ev is None:
            return False
        ev.set()
        return True


def _register_run(run_id: int) -> threading.Event:
    ev = threading.Event()
    with _running_lock:
        _running_syncs[run_id] = ev
    return ev


def _unregister_run(run_id: int) -> None:
    with _running_lock:
        _running_syncs.pop(run_id, None)


def _build_columns(selected_fields: Iterable[str], field_types: dict[str, dict]) -> list[tuple[str, str]]:
    """Always includes the system spine columns; appends one column per selected field.

    Field types come from the per-instance field cache; unknown fields default to
    VARCHAR(255). `key` and `issuekey` are NOT added here — they're aliases of
    the system `issue_key` column and are materialized in the view instead.
    """
    cols: list[tuple[str, str]] = [
        ("id", "INT AUTO_INCREMENT PRIMARY KEY"),
        ("issue_key", "VARCHAR(50) NOT NULL"),
        ("jira_created", "DATETIME NOT NULL"),
        ("jira_updated", "DATETIME NOT NULL"),
        ("fetched_at", "DATETIME NOT NULL"),
    ]
    spine_aliases = {
        "issue_key", "created", "updated", "key", "issuekey",
        "jira_created", "jira_updated", "fetched_at",
    }
    for fid in selected_fields:
        if fid in spine_aliases:
            continue
        ftype = field_types.get(fid, {}).get("type", "string")
        cols.append((fid, sql_type_for(fid, ftype)))
    return cols


def _paginated_rows(
    domain: str,
    email: str,
    token: str,
    jql: str,
    selected: list[str],
    field_types: dict[str, dict],
    page_size: int = 100,
) -> Iterator[list[dict]]:
    """Yield one list of rows per Jira page. Each list is one page's worth."""
    buf: list[dict] = []
    for row in fetch_and_extract(
        domain, email, token, jql, selected, field_types
    ):
        row["fetched_at"] = datetime.now()
        buf.append(row)
        if len(buf) >= page_size:
            yield buf
            buf = []
    if buf:
        yield buf


def run_report_sync(
    report_id: int,
    db: Session,
    *,
    on_page: callable = None,
) -> tuple[int, int]:
    """Fetch Jira data for one report and bulk-insert into its table.

    Each page is inserted in its own transaction so:
      - rows are visible in MySQL during the sync (not only at the end)
      - the run history's `rows_inserted` / `pages_fetched` update as we go
        (lets the admin UI show a live progress bar for long backfills)

    Returns (rows_inserted, pages_fetched). Writes a JiraRunHistory row reflecting
    success or failure.
    """
    report: Report | None = db.query(Report).get(report_id)
    if report is None:
        raise ValueError(f"Report {report_id} not found")

    instance: JiraInstance = report.jira_instance
    token = decrypt_token(instance.encrypted_token)
    selected: list[str] = normalize_selected_fields(
        report.selected_fields or [],
        get_field_types_for_instance(db, instance.id),
    )
    if "issue_key" not in selected:
        selected.insert(0, "issue_key")
    field_types = get_field_types_for_instance(db, instance.id)

    history = JiraRunHistory(report_id=report.id, status="running")
    db.add(history)
    db.commit()
    db.refresh(history)

    cancel_event = _register_run(history.id)
    table_name = f"report_{report.id}"
    rows_inserted = 0
    pages_fetched = 0

    try:
        for page_rows in _paginated_rows(
            instance.domain, instance.email, token, report.jql_query, selected, field_types
        ):
            # Check for cancel between pages. The current page's INSERT still
            # completes; we just don't start another one.
            if cancel_event.is_set():
                history.status = "cancelled"
                history.finished_at = datetime.now()
                history.rows_inserted = rows_inserted
                history.pages_fetched = pages_fetched
                report.last_run_at = history.finished_at
                report.last_run_status = "cancelled"
                db.commit()
                return rows_inserted, pages_fetched

            # Insert this page in its own transaction so the rows are visible
            # mid-sync (and the run history below can commit independently).
            with engine.begin() as conn:
                _flush(conn, table_name, page_rows, selected)

            rows_inserted += len(page_rows)
            pages_fetched += 1

            # Update run history so the admin UI's progress bar moves.
            history.rows_inserted = rows_inserted
            history.pages_fetched = pages_fetched
            db.commit()

            if on_page:
                on_page(pages_fetched, len(page_rows))

        history.status = "success"
        history.finished_at = datetime.now()
        report.last_run_at = history.finished_at
        report.last_run_status = "success"
        report.last_error = None
        db.commit()
        return rows_inserted, pages_fetched

    except Exception as e:
        history.status = "failed"
        history.error_message = str(e)[:2000]
        history.finished_at = datetime.now()
        report.last_run_at = history.finished_at
        report.last_run_status = "failed"
        report.last_error = history.error_message
        db.commit()
        raise
    finally:
        _unregister_run(history.id)


def _flush(conn, table_name: str, rows: list[dict], selected: list[str]) -> None:
    """Bulk-insert a batch of rows. Uses parameterized SQL to stay safe."""
    if not rows:
        return
    # Every row already carries the system spine keys (issue_key, jira_created,
    # jira_updated, fetched_at) from extract_issue_fields + the run loop, so we
    # only need to assemble the final column list with the user-selected fields
    # appended in the right order. `key` and `issuekey` are aliases of the
    # spine issue_key column and don't get their own physical column.
    spine_cols = ["issue_key", "jira_created", "jira_updated", "fetched_at"]
    spine_aliases = {"key", "issuekey"}
    final_cols: list[str] = list(spine_cols)
    seen: set[str] = set(spine_cols)
    for fid in selected:
        if fid in seen or fid in spine_aliases:
            continue
        if fid in ("issue_key", "jira_created", "jira_updated", "fetched_at"):
            continue
        seen.add(fid)
        final_cols.append(fid)

    placeholders = ", ".join(f":{c}" for c in final_cols)
    col_list = ", ".join(f"`{c}`" for c in final_cols)
    sql = f"INSERT INTO `{table_name}` ({col_list}) VALUES ({placeholders})"
    params = [{c: r.get(c) for c in final_cols} for r in rows]
    conn.execute(text(sql), params)

