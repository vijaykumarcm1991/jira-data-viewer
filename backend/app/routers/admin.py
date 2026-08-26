from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import SessionLocal, engine, get_db
from ..jira_fetcher.fields import (
    JiraFieldFetchError,
    fetch_instance_fields,
    fetch_myself,
)
from ..jira_fetcher.service import run_report_sync
from ..models import JiraInstance, JiraInstanceField, JiraRunHistory, Report
from ..report_service import drop_report, ensure_schema_matches_report
from ..scheduler import schedule_report, unschedule_report
from ..schemas import (
    JiraInstanceIn,
    JiraInstanceOut,
    ReportIn,
    ReportOut,
    ReportUpdate,
    RunHistoryOut,
)
from ..security import decrypt_token, encrypt_token

router = APIRouter(dependencies=[Depends(require_admin)])


# ---- Jira instances ----
@router.get("/instances", response_model=list[JiraInstanceOut])
def list_instances(db: Session = Depends(get_db)):
    return db.query(JiraInstance).order_by(JiraInstance.id).all()


@router.post("/instances", response_model=JiraInstanceOut, status_code=201)
def create_instance(payload: JiraInstanceIn, db: Session = Depends(get_db)):
    inst = JiraInstance(
        name=payload.name,
        domain=payload.domain,
        email=payload.email,
        encrypted_token=encrypt_token(payload.api_token),
        is_active=payload.is_active,
    )
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return inst


@router.delete("/instances/{instance_id}", status_code=204)
def delete_instance(instance_id: int, db: Session = Depends(get_db)):
    inst = db.query(JiraInstance).get(instance_id)
    if not inst:
        raise HTTPException(404, "Instance not found")
    if db.query(Report).filter(Report.jira_instance_id == instance_id).count() > 0:
        raise HTTPException(409, "Cannot delete an instance that has reports")
    db.delete(inst)
    db.commit()


# ---- Instance: test connection & refresh fields ----

def _instance_token(instance: JiraInstance) -> str:
    return decrypt_token(instance.encrypted_token)


@router.post("/instances/{instance_id}/test")
def test_instance(instance_id: int, db: Session = Depends(get_db)):
    """Verify the Jira credentials work and refresh the field cache.

    Returns:
      - account_id, display_name, email: the connected Jira user
      - fields_cached: number of fields now in the per-instance cache
      - fields_refreshed_at: when fields were last fetched from Jira
    Raises 502 on Jira-side errors.
    """
    inst = db.query(JiraInstance).get(instance_id)
    if not inst:
        raise HTTPException(404, "Instance not found")
    token = _instance_token(inst)
    try:
        me = fetch_myself(inst.domain, inst.email, token)
        raw_fields = fetch_instance_fields(inst.domain, inst.email, token)
    except JiraFieldFetchError as e:
        raise HTTPException(502, f"Jira rejected the request: {e}") from e

    # Replace the field cache for this instance.
    now = datetime.now()
    db.query(JiraInstanceField).filter(
        JiraInstanceField.jira_instance_id == instance_id
    ).delete()
    for f in raw_fields:
        db.add(
            JiraInstanceField(
                jira_instance_id=instance_id,
                field_id=f["field_id"],
                name=f["name"],
                field_type=f["field_type"],
                is_custom=f["is_custom"],
                schema_type=f["schema_type"],
                schema_custom=f.get("schema_custom"),
                last_fetched_at=now,
            )
        )
    db.commit()

    # Heal any reports on this instance whose column types no longer match the
    # freshly-cached field types (e.g. a "string" field re-detected as "text"
    # should become TEXT, not stay VARCHAR(255)).
    from ..report_service import ensure_schema_matches_report

    for r in (
        db.query(Report)
        .filter(Report.jira_instance_id == instance_id)
        .all()
    ):
        ensure_schema_matches_report(r)

    inst.updated_at = now
    db.commit()
    return {
        "account_id": me.get("account_id"),
        "display_name": me.get("display_name"),
        "email": me.get("email"),
        "fields_cached": len(raw_fields),
        "fields_refreshed_at": now,
    }


@router.get("/instances/{instance_id}/fields")
def list_instance_fields(instance_id: int, db: Session = Depends(get_db)):
    """Return the cached field list for an instance, sorted by name."""
    inst = db.query(JiraInstance).get(instance_id)
    if not inst:
        raise HTTPException(404, "Instance not found")
    rows = (
        db.query(JiraInstanceField)
        .filter(JiraInstanceField.jira_instance_id == instance_id)
        .order_by(JiraInstanceField.name)
        .all()
    )
    return [
        {
            "id": r.field_id,
            "name": r.name,
            "type": r.field_type,
            "is_custom": r.is_custom,
            "schema_type": r.schema_type,
            "schema_custom": r.schema_custom,
            "last_fetched_at": r.last_fetched_at,
        }
        for r in rows
    ]


@router.post("/instances/{instance_id}/run-all", status_code=202)
def run_all_for_instance(
    instance_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    """Queue a sync for every active report bound to this instance.

    Each report runs in its own background task. The run history table on the
    admin dashboard auto-refreshes every 5s, so progress is visible there.
    """
    inst = db.query(JiraInstance).get(instance_id)
    if not inst:
        raise HTTPException(404, "Instance not found")
    reports = (
        db.query(Report)
        .filter(Report.jira_instance_id == instance_id, Report.is_active.is_(True))
        .all()
    )
    if not reports:
        raise HTTPException(400, "No active reports for this instance")

    def _run_one(report_id: int):
        with SessionLocal() as session:
            try:
                run_report_sync(report_id, session)
            except Exception:
                pass

    for r in reports:
        background.add_task(_run_one, r.id)

    return {
        "status": "scheduled",
        "instance_id": instance_id,
        "reports_queued": len(reports),
        "report_ids": [r.id for r in reports],
    }


# ---- Reports ----
@router.get("/reports", response_model=list[ReportOut])
def list_reports(db: Session = Depends(get_db)):
    return [_report_to_dict(r) for r in db.query(Report).order_by(desc(Report.created_at)).all()]


@router.get("/reports/{report_id}", response_model=ReportOut)
def get_report(report_id: int, db: Session = Depends(get_db)):
    r = db.query(Report).get(report_id)
    if not r:
        raise HTTPException(404, "Report not found")
    return _report_to_dict(r)


@router.post("/reports", response_model=ReportOut, status_code=201)
def create_report(payload: ReportIn, db: Session = Depends(get_db)):
    inst = db.query(JiraInstance).get(payload.jira_instance_id)
    if not inst:
        raise HTTPException(400, "Jira instance not found")
    if not inst.is_active:
        raise HTTPException(400, "Jira instance is not active")
    if db.query(JiraInstanceField).filter(
        JiraInstanceField.jira_instance_id == payload.jira_instance_id
    ).count() == 0:
        raise HTTPException(
            400,
            "No fields cached for this instance. Click 'Test connection' on the instance to fetch its fields first.",
        )
    report = Report(
        name=payload.name,
        jira_instance_id=payload.jira_instance_id,
        jql_query=payload.jql_query,
        schedule_cron=payload.schedule_cron,
        selected_fields=payload.selected_fields,
        is_active=payload.is_active,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    ensure_schema_matches_report(report)
    if report.is_active:
        schedule_report(report.id, report.schedule_cron)
    return _report_to_dict(report)


@router.patch("/reports/{report_id}", response_model=ReportOut)
def update_report(report_id: int, payload: ReportUpdate, db: Session = Depends(get_db)):
    r = db.query(Report).get(report_id)
    if not r:
        raise HTTPException(404, "Report not found")
    if payload.name is not None:
        r.name = payload.name
    if payload.jql_query is not None:
        r.jql_query = payload.jql_query
    if payload.selected_fields is not None:
        r.selected_fields = payload.selected_fields
    if payload.schedule_cron is not None:
        r.schedule_cron = payload.schedule_cron
    if payload.is_active is not None:
        r.is_active = payload.is_active
    if payload.history_retention_days is not None:
        if payload.history_retention_days < 0:
            raise HTTPException(400, "history_retention_days must be >= 0")
        r.history_retention_days = payload.history_retention_days
    db.commit()
    db.refresh(r)
    ensure_schema_matches_report(r)
    if r.is_active:
        schedule_report(r.id, r.schedule_cron)
    else:
        unschedule_report(r.id)
    return _report_to_dict(r)


@router.delete("/reports/{report_id}", status_code=204)
def delete_report(report_id: int, db: Session = Depends(get_db)):
    r = db.query(Report).get(report_id)
    if not r:
        raise HTTPException(404, "Report not found")
    unschedule_report(r.id)
    db.delete(r)
    db.commit()
    drop_report(r.id)


@router.post("/reports/{report_id}/truncate", status_code=200)
def truncate_report(report_id: int, db: Session = Depends(get_db)):
    """Empty the report's data table (TRUNCATE) without dropping the schema or view.

    The next sync will repopulate it from scratch using the report's current JQL.
    Use this when you want to backfill with a different time range, or just
    start over with a clean slate.
    """
    r = db.query(Report).get(report_id)
    if not r:
        raise HTTPException(404, "Report not found")
    from sqlalchemy import text as sa_text
    with engine.begin() as conn:
        conn.execute(sa_text(f"TRUNCATE TABLE `report_{report_id}`"))
    r.last_run_at = None
    r.last_run_status = None
    r.last_error = None
    db.commit()
    return {"status": "truncated", "report_id": report_id}


@router.post("/reports/{report_id}/cleanup", status_code=200)
def cleanup_report(report_id: int, db: Session = Depends(get_db)):
    """Run the history-cleanup now: delete all non-latest rows for this report.

    Honors the report's `history_retention_days` setting (0 = keep only the
    latest per key, >0 = also delete non-latest rows older than that many days).
    Returns the number of rows deleted.
    """
    from ..cleanup_service import cleanup_report_history

    r = db.query(Report).get(report_id)
    if not r:
        raise HTTPException(404, "Report not found")
    deleted = cleanup_report_history(db, r)
    return {
        "status": "ok",
        "report_id": report_id,
        "rows_deleted": deleted,
        "retention_days": r.history_retention_days,
    }


@router.post("/reports/{report_id}/run-now", status_code=202)
def run_now(report_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    r = db.query(Report).get(report_id)
    if not r:
        raise HTTPException(404, "Report not found")

    def _run():
        with SessionLocal() as session:
            try:
                run_report_sync(report_id, session)
            except Exception:
                pass

    background.add_task(_run)
    return {"status": "scheduled"}


# ---- Run history ----
@router.get("/reports/{report_id}/runs", response_model=list[RunHistoryOut])
def report_runs(report_id: int, db: Session = Depends(get_db), limit: int = 50):
    return (
        db.query(JiraRunHistory)
        .filter(JiraRunHistory.report_id == report_id)
        .order_by(desc(JiraRunHistory.started_at))
        .limit(limit)
        .all()
    )


@router.get("/runs", response_model=list[RunHistoryOut])
def all_runs(db: Session = Depends(get_db), limit: int = 100):
    return (
        db.query(JiraRunHistory)
        .order_by(desc(JiraRunHistory.started_at))
        .limit(limit)
        .all()
    )


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    """Signal a running sync to stop. The sync finishes its current page
    (so the data committed so far is preserved) and then marks itself as
    `cancelled` in the run history.

    Returns 404 if the run doesn't exist, 409 if it isn't running, 200 otherwise.
    """
    run = db.query(JiraRunHistory).get(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run.status != "running":
        raise HTTPException(409, f"Run is not running (status: {run.status})")
    from ..jira_fetcher.service import request_cancel
    if not request_cancel(run_id):
        # The in-memory registry doesn't have it — likely a stale "running"
        # row left over from a backend restart. Mark it failed so the UI
        # can move on.
        run.status = "failed"
        run.error_message = "Interrupted (sync process no longer running)"
        run.finished_at = datetime.now()
        if run.report_id:
            r = db.query(Report).get(run.report_id)
            if r:
                r.last_run_at = run.finished_at
                r.last_run_status = "failed"
        db.commit()
        return {"status": "interrupted", "run_id": run_id}
    return {"status": "cancel_requested", "run_id": run_id}


# ---- helpers ----
def _report_to_dict(r: Report) -> dict[str, Any]:
    return {
        "id": r.id,
        "name": r.name,
        "jira_instance_id": r.jira_instance_id,
        "jira_instance_name": r.jira_instance.name if r.jira_instance else None,
        "jql_query": r.jql_query,
        "schedule_cron": r.schedule_cron,
        "selected_fields": list(r.selected_fields or []),
        "is_active": r.is_active,
        "history_retention_days": r.history_retention_days,
        "last_run_at": r.last_run_at,
        "last_run_status": r.last_run_status,
        "last_error": r.last_error,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }
