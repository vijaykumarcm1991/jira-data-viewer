"""Thin Jira REST client. Uses POST /rest/api/3/search/jql with nextPageToken paging,
exactly as the original jsm_db.py did. Yields issues one at a time so the caller
controls batching and persistence.

Includes a small retry layer for transient network failures (DNS, connection
reset, 5xx, 429). A failure is retried with exponential backoff up to a total
budget so a long backfill doesn't stall forever on a flaky network.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Callable, Iterator, TypeVar

import requests
from requests.auth import HTTPBasicAuth
from requests.exceptions import (
    ConnectionError as ReqConnectionError,
    Timeout,
)

from .parsers import extract_issue_fields

log = logging.getLogger(__name__)

T = TypeVar("T")


class JiraAPIError(RuntimeError):
    pass


# Retry budget: 5 attempts, 0.5s → 1s → 2s → 4s → 8s (with ±25% jitter).
# Total wall time worst case ~15s, which is well below the uvicorn default 30s
# timeout for sync requests but doesn't block a long-running sync indefinitely.
_MAX_ATTEMPTS = 5
_BASE_DELAY = 0.5
_MAX_DELAY = 8.0
_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


def _is_retryable(exc: Exception | None, status: int | None) -> bool:
    if exc is not None:
        if isinstance(exc, (ReqConnectionError, Timeout)):
            return True
        # DNS / network errors surface as generic requests.exceptions, treat as retryable
        return "NameResolutionError" in type(exc).__name__ or "Connection" in type(exc).__name__
    if status is None:
        return False
    return status in _RETRYABLE_STATUS


def _with_retry(label: str, fn: Callable[[], T]) -> T:
    """Run `fn` with retries on transient failures.

    The `label` is included in log messages so a long backfill's logs make it
    clear which call is being retried.
    """
    last_exc: Exception | None = None
    last_status: int | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            # requests.HTTPError carries a response attribute; everything else
            # is treated as a network-level failure.
            last_status = getattr(getattr(e, "response", None), "status_code", None)
            if not _is_retryable(e, last_status) or attempt == _MAX_ATTEMPTS:
                raise
            delay = min(_MAX_DELAY, _BASE_DELAY * (2 ** (attempt - 1)))
            delay *= 0.75 + random.random() * 0.5  # ±25% jitter
            log.warning(
                "%s failed (attempt %d/%d): %s — retrying in %.2fs",
                label, attempt, _MAX_ATTEMPTS,
                getattr(e, "strerror", None) or str(e)[:200],
                delay,
            )
            time.sleep(delay)
    # Unreachable, but mypy likes a final raise.
    raise last_exc or JiraAPIError(f"{label} failed after {_MAX_ATTEMPTS} attempts")


def _post_json_with_retry(label: str, url: str, auth: HTTPBasicAuth, payload: dict) -> dict:
    def _do() -> dict:
        r = requests.post(
            url, json=payload, auth=auth,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=60,
        )
        if r.status_code != 200:
            # Raise with response attached so the retry layer can read the status.
            err = requests.HTTPError(
                f"Jira API returned {r.status_code}: {r.text[:500]}", response=r
            )
            raise err
        return r.json()

    return _with_retry(label, _do)


def _get_json_with_retry(label: str, url: str, auth: HTTPBasicAuth) -> dict:
    def _do() -> dict:
        r = requests.get(
            url, auth=auth,
            headers={"Accept": "application/json"},
            timeout=30,
        )
        if r.status_code != 200:
            err = requests.HTTPError(
                f"Jira returned {r.status_code}: {r.text[:300]}", response=r
            )
            raise err
        return r.json()

    return _with_retry(label, _do)


def fetch_all_issues(
    domain: str,
    email: str,
    token: str,
    jql: str,
    jira_fields: list[str],
    max_per_page: int = 100,
) -> Iterator[dict]:
    """Yield every issue returned by Jira for the given JQL, across all pages.

    Each page is fetched with retry-on-transient-failure; the per-page
    request is the unit of retry, not the whole sync.
    """
    url = f"https://{domain}/rest/api/3/search/jql"
    auth = HTTPBasicAuth(email, token)

    next_token: str | None = None
    while True:
        payload: dict = {
            "jql": jql,
            "maxResults": max_per_page,
            "fields": jira_fields,
        }
        if next_token:
            payload["nextPageToken"] = next_token

        data = _post_json_with_retry(
            f"Jira search/jql page (token={next_token!r})", url, auth, payload
        )
        issues = data.get("issues", [])
        if not issues:
            return
        for issue in issues:
            yield issue
        next_token = data.get("nextPageToken")
        if not next_token:
            return


def fetch_and_extract(
    domain: str,
    email: str,
    token: str,
    jql: str,
    selected_field_ids: list[str],
    field_types: dict[str, dict] | None = None,
) -> Iterator[dict]:
    """Like `fetch_all_issues` but yields already-extracted flat dicts ready to insert.

    The Jira field list to request is built from the per-instance field cache
    (`field_types`); for unknown ids the field id itself is used (which is correct
    for almost all Jira fields — `status`, `customfield_10086`, etc.).
    """
    field_types = field_types or {}
    jira_fields: list[str] = []
    for fid in selected_field_ids:
        if fid in {"issue_key", "key", "jira_created", "jira_updated", "created", "updated", "fetched_at"}:
            continue
        if fid not in jira_fields:
            jira_fields.append(fid)
    for required in ("key", "created", "updated"):
        if required not in jira_fields:
            jira_fields.append(required)

    for issue in fetch_all_issues(domain, email, token, jql, jira_fields):
        yield extract_issue_fields(issue, selected_field_ids, field_types)
