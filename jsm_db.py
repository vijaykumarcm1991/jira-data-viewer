"""CLI wrapper around the new jira_fetcher module.

The full fetcher / scheduler / per-report schema lives in `backend/app/`. This script
is kept as a thin command-line entry point so an operator can trigger a sync without
going through the UI (e.g. `python jsm_db.py --report-id 1`).

Original behavior (single hard-coded JQL into a single global table) is replaced by the
report-based flow. Use the admin UI to create a Jira instance + report first.
"""
from __future__ import annotations

import argparse
import os
import sys

# Make `backend/app` importable when this script is run from the project root.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "backend"))

from app.database import SessionLocal  # noqa: E402
from app.jira_fetcher.service import run_report_sync  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Trigger a Jira report sync (CLI).")
    p.add_argument("--report-id", type=int, required=True, help="Report id to sync")
    p.add_argument(
        "--quiet", action="store_true", help="Suppress per-page progress output"
    )
    args = p.parse_args()

    def _on_page(page_idx: int, page_size: int) -> None:
        if not args.quiet:
            print(f"  page {page_idx}: {page_size} rows", flush=True)

    with SessionLocal() as db:
        try:
            rows, pages = run_report_sync(args.report_id, db, on_page=_on_page)
        except Exception as e:
            print(f"Sync failed: {e}", file=sys.stderr)
            return 1
    print(f"OK: inserted {rows} rows across {pages} pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
