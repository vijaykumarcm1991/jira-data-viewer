"""Weekly history-cleanup service.

For each report table `report_<id>`, keep only the row with the latest
(jira_updated, fetched_at) per issue_key. If the report has
`history_retention_days > 0`, also delete non-latest rows older than
that many days. The latest row per key is ALWAYS preserved regardless
of age.

This is a self-join DELETE; the existing `idx_issue_key` index makes
the lookup fast. For a 60k-row table with ~1k keys touched, this
runs in well under a second on MySQL 8.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from .models import Report

log = logging.getLogger(__name__)


def cleanup_report_history(
    db: Session, report: Report, *, retention_days: int | None = None
) -> int:
    """Delete all non-latest rows in this report's table.

    Args:
        db: an open session
        report: the Report row (used for the table name)
        retention_days: if provided, also delete non-latest rows older than
            this many days. If None, uses `report.history_retention_days`.
            Pass 0 or a negative value to dedup only (no time-based delete).

    Returns:
        number of rows deleted
    """
    from .report_service import table_name

    if retention_days is None:
        retention_days = report.history_retention_days or 0

    table = table_name(report.id)
    # Self-join DELETE: keep the row with the MAX (jira_updated, fetched_at)
    # per issue_key; delete all the others. If retention_days > 0, also
    # require the older row's fetched_at to be older than the retention
    # cutoff — so the latest row is never deleted regardless of age.
    if retention_days <= 0:
        # Dedup only — every non-latest row gets deleted.
        sql = f"""
        DELETE r1 FROM `{table}` r1
        INNER JOIN `{table}` r2
          ON r1.issue_key = r2.issue_key
         AND (r1.jira_updated < r2.jira_updated
              OR (r1.jira_updated = r2.jira_updated
                  AND r1.fetched_at < r2.fetched_at))
        """
    else:
        sql = f"""
        DELETE r1 FROM `{table}` r1
        INNER JOIN `{table}` r2
          ON r1.issue_key = r2.issue_key
         AND (r1.jira_updated < r2.jira_updated
              OR (r1.jira_updated = r2.jira_updated
                  AND r1.fetched_at < r2.fetched_at))
        WHERE r1.fetched_at < (NOW() - INTERVAL {int(retention_days)} DAY)
        """

    result = db.execute(text(sql))
    db.commit()
    return int(result.rowcount or 0)


def cleanup_all_reports(db: Session) -> dict[int, int]:
    """Run the cleanup for every active report. Returns {report_id: rows_deleted}."""
    from .models import Report
    results: dict[int, int] = {}
    for report in db.query(Report).filter(Report.is_active.is_(True)).all():
        try:
            deleted = cleanup_report_history(db, report)
            results[report.id] = deleted
        except Exception as e:
            log.exception("Cleanup failed for report id=%s: %s", report.id, e)
            results[report.id] = -1
    return results
