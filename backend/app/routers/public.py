"""Public read endpoints. No authentication required.

- GET /api/reports
- GET /api/reports/<id>           (report metadata + field metadata)
- GET /api/reports/<id>/issues    (paginated, filterable)
- GET /api/reports/<id>/export    (CSV stream, same filters)
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import engine, get_db
from ..field_catalog import (
    get_field_types_for_instance,
    normalize_selected_fields,
)
from ..models import JiraInstanceField, Report
from ..report_service import view_name
from ..timezone import format_ist

router = APIRouter()

_SAFE_ID = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


@router.get("/reports")
def list_reports(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.query(Report).order_by(Report.id).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "jira_instance_id": r.jira_instance_id,
            "selected_fields": list(r.selected_fields or []),
            "last_run_at": r.last_run_at.isoformat() if r.last_run_at else None,
            "last_run_status": r.last_run_status,
        }
        for r in rows
    ]


@router.get("/reports/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db)) -> dict:
    r = db.query(Report).get(report_id)
    if not r:
        raise HTTPException(404, "Report not found")
    field_types = get_field_types_for_instance(db, r.jira_instance_id)
    selected = normalize_selected_fields(
        r.selected_fields or [], field_types
    )
    out_fields: list[dict] = []
    for i, fid in enumerate(selected):
        meta = field_types.get(fid, {})
        out_fields.append(
            {
                "id": fid,
                "name": meta.get("name", fid),
                "type": meta.get("type", "string"),
                "is_custom": meta.get("is_custom", False),
                "position": i,
            }
        )
    return {
        "id": r.id,
        "name": r.name,
        "jira_instance_id": r.jira_instance_id,
        "jql_query": r.jql_query,
        "selected_fields": out_fields,
        "last_run_at": r.last_run_at.isoformat() if r.last_run_at else None,
        "last_run_status": r.last_run_status,
    }


@router.get("/reports/{report_id}/issues")
def get_issues(
    report_id: int,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    created_from: str | None = None,
    created_to: str | None = None,
    sort_field: str | None = None,
    sort_dir: str | None = Query(None, pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
) -> dict:
    report = db.query(Report).get(report_id)
    if not report:
        raise HTTPException(404, "Report not found")

    field_types = get_field_types_for_instance(db, report.jira_instance_id)
    selected = normalize_selected_fields(
        report.selected_fields or [], field_types
    )
    where, params = _build_filters(selected, field_types, request.query_params, created_from, created_to)
    where_sql = " AND ".join(where) if where else "1=1"
    view = view_name(report_id)
    offset = (page - 1) * page_size
    cols = _select_columns(selected)
    order_sql = _build_order_by(sort_field, sort_dir, selected)

    count_sql = f"SELECT COUNT(*) FROM `{view}` WHERE {where_sql}"
    total = db.execute(text(count_sql), params).scalar() or 0

    data_sql = (
        f"SELECT {cols} FROM `{view}` WHERE {where_sql} "
        f"{order_sql} LIMIT :_limit OFFSET :_offset"
    )
    params["_limit"] = page_size
    params["_offset"] = offset
    rows = db.execute(text(data_sql), params).fetchall()
    data = [_row_to_dict(r) for r in rows]

    return {
        "data": data,
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


@router.get("/reports/{report_id}/export")
def export_csv(
    report_id: int,
    request: Request,
    created_from: str | None = None,
    created_to: str | None = None,
    sort_field: str | None = None,
    sort_dir: str | None = Query(None, pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    report = db.query(Report).get(report_id)
    if not report:
        raise HTTPException(404, "Report not found")

    field_types = get_field_types_for_instance(db, report.jira_instance_id)
    selected = normalize_selected_fields(
        report.selected_fields or [], field_types
    )
    where, params = _build_filters(selected, field_types, request.query_params, created_from, created_to)
    where_sql = " AND ".join(where) if where else "1=1"
    view = view_name(report_id)
    data_cols = _data_columns(selected)
    col_sql = ", ".join(f"`{c}`" for c in data_cols)
    header = [field_types.get(c, {}).get("name", c) for c in data_cols]
    order_sql = _build_order_by(sort_field, sort_dir, selected)
    sql = f"SELECT {col_sql} FROM `{view}` WHERE {where_sql} {order_sql}"

    def _iter():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(header)
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
        with engine.connect() as conn:
            result = conn.execute(text(sql), params)
            for row in result:
                writer.writerow([_format_csv_value(row._mapping[c], field_types.get(c, {}).get("type")) for c in data_cols])
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate(0)

    return StreamingResponse(
        _iter(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="report_{report_id}.csv"'},
    )


# ---------- helpers ----------

def _data_columns(selected: list[str]) -> list[str]:
    """Columns the user sees in the data table / CSV. The view has these same
    names: each user-selected field id is a column, plus `issue_key` first and
    either `created` (if the user selected it) or `jira_created` (if they didn't)
    as the system date column. `key` and `issuekey` are passed through too —
    they're aliased in the view to `issue_key`.
    """
    out: list[str] = []
    seen: set[str] = set()
    for fid in selected:
        if fid in seen:
            continue
        if fid in {"issue_key", "jira_created", "jira_updated", "fetched_at"}:
            continue
        if not _SAFE_ID.match(fid):
            continue
        out.append(fid)
        seen.add(fid)
    return out


def _select_columns(selected: list[str]) -> str:
    """Build the full SELECT for the data endpoint (visible + hidden tiebreak cols)."""
    cols = ["issue_key"] + _data_columns(selected)
    if "created" in selected:
        cols.append("created")
    else:
        cols.append("jira_created")
    cols += ["_jira_created", "_jira_updated", "_fetched_at"]
    return ", ".join(f"`{c}`" for c in cols)


def _row_to_dict(row) -> dict[str, Any]:
    m = row._mapping
    out: dict[str, Any] = {}
    for k, v in m.items():
        if k.startswith("_"):
            continue
        if isinstance(v, datetime):
            out[k] = format_ist(v)
        else:
            out[k] = v
    return out


def _format_csv_value(value: Any, ftype: str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return format_ist(value)
    if ftype == "datetime" and isinstance(value, str):
        return value
    return str(value)


def _build_filters(
    selected: list[str],
    field_types: dict[str, dict],
    qparams,
    created_from: str | None,
    created_to: str | None,
) -> tuple[list[str], dict[str, Any]]:
    where: list[str] = []
    params: dict[str, Any] = {}

    if created_from:
        where.append("`_jira_created` >= :created_from")
        params["created_from"] = _parse_date(created_from, end=False)
    if created_to:
        where.append("`_jira_created` <= :created_to")
        params["created_to"] = _parse_date(created_to, end=True)

    for raw_key, raw_value in qparams.multi_items():
        if not raw_key.startswith("f_") or not raw_value:
            continue
        field_id = raw_key[2:]
        if field_id not in selected or field_id not in field_types:
            continue
        if not _SAFE_ID.match(field_id):
            continue
        ftype = field_types.get(field_id, {}).get("type", "string")
        if ftype in ("string", "text"):
            values = [v.strip() for v in raw_value.split(",") if v.strip()]
            if not values:
                continue
            if len(values) == 1:
                where.append(f"`{field_id}` = :f_{field_id}")
                params[f"f_{field_id}"] = values[0]
            else:
                ph = ", ".join(f":f_{field_id}_{i}" for i in range(len(values)))
                where.append(f"`{field_id}` IN ({ph})")
                for i, v in enumerate(values):
                    params[f"f_{field_id}_{i}"] = v
        elif ftype == "number":
            try:
                num = float(raw_value)
            except ValueError:
                continue
            where.append(f"`{field_id}` = :f_{field_id}")
            params[f"f_{field_id}"] = num

    return where, params


def _build_order_by(sort_field: str | None, sort_dir: str | None, selected: list[str]) -> str:
    """Build the ORDER BY clause, whitelisting against the report's selected fields.

    The default (no sort) is `_jira_created DESC` — newest first.
    """
    if not sort_field:
        return "ORDER BY `_jira_created` DESC"
    if not _SAFE_ID.match(sort_field):
        return "ORDER BY `_jira_created` DESC"
    # Whitelist: must be in the report's selected fields (or the system jira_created)
    if sort_field not in selected and sort_field not in {"jira_created", "issue_key"}:
        return "ORDER BY `_jira_created` DESC"
    direction = "DESC" if (sort_dir or "desc").lower() != "asc" else "ASC"
    return f"ORDER BY `{sort_field}` {direction}, `_jira_created` DESC"


def _parse_date(s: str, *, end: bool) -> str:
    """Accept YYYY-MM-DD or full datetime; return a MySQL-compatible string in IST."""
    s = s.strip()
    if "T" in s or " " in s and len(s) > 10:
        return s.replace("T", " ")
    if end:
        return f"{s} 23:59:59"
    return f"{s} 00:00:00"
