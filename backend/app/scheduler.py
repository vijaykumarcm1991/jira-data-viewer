"""APScheduler bootstrap.

On startup, loads every active report and schedules a cron job for it. The
admin "Run now" endpoint reuses `run_report_sync` directly without going through
the scheduler.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .database import SessionLocal
from .jira_fetcher.service import run_report_sync
from .models import Report

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _job(report_id: int):
    """APScheduler job body. Opens its own session."""
    log.info("Running scheduled sync for report id=%s", report_id)
    with SessionLocal() as db:
        try:
            run_report_sync(report_id, db)
        except Exception as e:
            log.exception("Scheduled sync failed for report id=%s: %s", report_id, e)


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
    _scheduler.start()
    reload_jobs()


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def reload_jobs() -> None:
    """Reschedule every active report from scratch."""
    if _scheduler is None:
        return
    for job in list(_scheduler.get_jobs()):
        job.remove()
    with SessionLocal() as db:
        for report in db.query(Report).filter(Report.is_active.is_(True)).all():
            schedule_report(report.id, report.schedule_cron, replace=False)


def schedule_report(report_id: int, cron: str, *, replace: bool = True) -> None:
    """Add or replace a cron job for one report."""
    if _scheduler is None:
        return
    job_id = f"report_{report_id}"
    if replace:
        existing = _scheduler.get_job(job_id)
        if existing:
            existing.remove()
    try:
        trigger = CronTrigger.from_crontab(cron, timezone="Asia/Kolkata")
    except Exception as e:
        log.warning("Invalid cron %r for report %s: %s", cron, report_id, e)
        return
    _scheduler.add_job(
        _job,
        trigger=trigger,
        args=[report_id],
        id=job_id,
        replace_existing=True,
        misfire_grace_time=600,
    )


def unschedule_report(report_id: int) -> None:
    if _scheduler is None:
        return
    job = _scheduler.get_job(f"report_{report_id}")
    if job:
        job.remove()


def _weekly_cleanup() -> None:
    """Run history cleanup for every active report. Runs Sundays 03:00 IST."""
    from .cleanup_service import cleanup_all_reports
    from .database import SessionLocal

    log.info("Running weekly history cleanup")
    with SessionLocal() as db:
        results = cleanup_all_reports(db)
    if results:
        log.info("Weekly cleanup results: %s", results)
    else:
        log.info("Weekly cleanup: no active reports")
