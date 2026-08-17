# Jira Data Viewer

A self-hosted tool that pulls Jira issues into a MySQL database, lets you build user-defined reports on top of that data, and exposes a modern web UI for filtering, viewing, and exporting.

Everything runs in Docker Compose. Everything is in IST (Asia/Kolkata) — the MySQL container, the backend, the frontend, and how dates are stored and displayed. Jira is assumed to return IST strings as-is; the backend does no timezone conversion.

## What you get

- **Three services in one `docker compose up`**: `db` (MySQL 8), `backend` (FastAPI + APScheduler + a thread-safe cancel registry), `frontend` (React + Vite + shadcn/ui)
- **Multi-Jira-instance support** — add as many Jira Cloud sources as you want, each with its own credentials
- **Dynamic field discovery** — every Jira instance's full field list (system + custom) is fetched live from `GET /rest/api/3/field`, cached in MySQL, and used to drive the report form. No more hardcoded `customfield_10086` lists
- **User-defined reports** — each report has its own JQL, its own selected fields (drag-to-reorder), its own cron schedule, and its own physical MySQL table (`report_<id>`) plus a latest-snapshot view (`v_report_<id>_latest`)
- **History + latest snapshot** — every fetch inserts new rows; the view returns only the latest `jira_updated` per `issue_key`
- **Long-text detection** — textareas (Jira `schema.custom` ending in `:textarea` or `:textfield`) and known system fields like `summary`, `description`, `environment`, `comment` are mapped to `TEXT` instead of `VARCHAR(255)`. A startup migration widens existing tables automatically
- **Test connection** button on every instance — verifies Jira auth and re-caches the field list in one click. Re-running it on a fix (e.g. after enabling a new custom field) heals every report on that instance
- **Manual run** button per instance ("Run all") and per report ("Run now") for kicking off syncs outside the cron schedule
- **Truncate** button per report — empties the data table but keeps the schema and view, so you can backfill with a different JQL
- **Stop** button on running syncs — cancels the in-flight job cleanly between pages, preserving all already-committed rows
- **Live progress bar** with per-page row count updates and a 2s polling interval
- **Public read, admin-gated config** — anyone with the URL can browse reports; only logged-in admins can add Jira sources, edit reports, or run syncs
- **Retry layer** for transient network failures — 5 attempts, exponential backoff with jitter, retries on connection errors, timeouts, DNS errors, and HTTP 408/425/429/5xx. Per-page retry, not whole-sync
- **Resilient to restarts** — on backend boot, any `running` runs from a previous session are auto-marked `failed` with "Interrupted by backend restart"
- **Column sorting** — click any column header to sort asc/desc; sort persists in `localStorage` per report
- **Column visibility** — toggle which columns to show; persists in `localStorage`
- **Filter panel** with internal scroll (per your UX preference) for multi-select on string fields, text search on free text, numeric equality
- **Date slicer** on the `created` field with presets (Last 7/30/90 days, All time)

## Quick start

### 1. Generate the secrets

```bash
cp .env.example .env

# Fernet key for encrypting Jira tokens
python -c "from cryptography.fernet import Fernet; print('ENCRYPTION_KEY=' + Fernet.generate_key().decode())"

# JWT signing secret
python -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(48))"
```

Open `.env` and:
- Paste the two generated values
- Replace `MYSQL_ROOT_PASSWORD`, `DB_PASSWORD`, and `ADMIN_PASSWORD` with strong values
- Set `ADMIN_USERNAME` (default is `admin`)

### 2. Start the stack

```bash
docker compose up -d --build
```

This boots:
- `jira_db` on the internal network (port 3306 not published — use `docker compose exec db mysql ...` to inspect)
- `jira_backend` on `http://localhost:8000` (API docs at `/docs`)
- `jira_frontend` on `http://localhost:5173` (the UI)

### 3. Log in and configure

1. Open `http://localhost:5173/admin/login` → sign in with the admin credentials from `.env`
2. **Jira instances** → **New instance** → fill in domain, email, API token from [id.atlassian.com](https://id.atlassian.com/manage-profile/security/api-tokens)
3. Click **Test** on the instance row — verifies the token, fetches the full field list, and stores it
4. **Reports** → **New report** → pick the instance, paste a JQL, set a cron, drag fields into the **Selected** list, reorder with the grip handle, save
5. The backend creates `report_<id>` + `v_report_<id>_latest` and schedules the first run

### 4. Use the public report view

- `http://localhost:5173/` lists all reports
- Click a report → `http://localhost:5173/r/<id>` for the data table
- Date range slicer on `created`, multi-field filters, column visibility, column sort, CSV export — all in the toolbar

## Architecture

```
┌────────────────────┐      ┌────────────────────┐      ┌────────────────────┐
│  frontend (nginx)  │─────▶│  backend (FastAPI) │─────▶│  db (MySQL 8)      │
│  React + shadcn/ui │      │  APScheduler in-   │      │  TZ=Asia/Kolkata   │
│  Vite              │      │  process, cancel   │      │  session tz=+05:30 │
│                    │      │  registry, retry   │      │                    │
└────────────────────┘      └────────────────────┘      └────────────────────┘
```

### Backend modules

```
backend/app/
├── main.py                  # FastAPI app, lifespan: scheduler, admin user sync,
│                            #   migrations, orphaned-run cleanup
├── config.py                # Pydantic settings (env)
├── database.py              # SQLAlchemy engine; sets MySQL session time_zone via
│                            #   connect-listener
├── timezone.py              # parse_jira_datetime (no conversion — Jira is assumed
│                            #   to already be in IST), format_ist
├── field_catalog.py         # Field-type lookup helpers (per-instance cache)
├── models.py                # ORM: admin_user, jira_instances, jira_instance_fields,
│                            #   reports, jira_run_history
├── schemas.py               # Pydantic request/response models
├── security.py              # Fernet (Jira tokens), bcrypt (admin password)
├── auth.py                  # JWT issuance + admin dependency
├── scheduler.py             # APScheduler, IST cron
├── report_service.py        # DDL for per-report tables + latest views, plus
│                            #   schema reconciliation (add columns, widen types,
│                            #   recreate view)
├── jira_fetcher/
│   ├── parsers.py           # parse_jira_datetime, extract_adf_text,
│   │                        #   extract_option_value, extract_issue_fields
│   │                        #   (with key/issuekey aliasing)
│   ├── client.py            # POST /search/jql with nextPageToken paging,
│   │                        #   per-page retry with exponential backoff + jitter
│   ├── fields.py            # GET /field discovery + normalize_field
│   │                        #   (textarea detection via schema.custom)
│   └── service.py           # run_report_sync — per-page transactions,
│                            #   cancel checking, run history updates
└── routers/
    ├── auth.py              # POST /api/auth/login, /logout, GET /me
    ├── admin.py             # CRUD on instances and reports, /test, /run-now,
    │                        #   /run-all, /truncate, /runs/{id}/cancel
    └── public.py            # GET /api/reports, /api/reports/{id},
                             #   /api/reports/{id}/issues (paginated, filtered,
                             #   sortable), /api/reports/{id}/export (CSV)
```

### Data model

**Four fixed tables** + **one dynamic table per report** + **one dynamic view per report**:

```sql
-- Admin login (single user, bcrypt hash from env)
CREATE TABLE admin_user (
  id INT PRIMARY KEY,
  username VARCHAR(64) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  created_at DATETIME NOT NULL
);

-- Registered Jira sources
CREATE TABLE jira_instances (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(128) NOT NULL,
  domain VARCHAR(255) NOT NULL,
  email VARCHAR(255) NOT NULL,
  encrypted_token TEXT NOT NULL,           -- Fernet
  is_active BOOLEAN DEFAULT TRUE,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

-- Per-instance field cache (refreshed by /test)
CREATE TABLE jira_instance_fields (
  id INT AUTO_INCREMENT PRIMARY KEY,
  jira_instance_id INT NOT NULL,
  field_id VARCHAR(100) NOT NULL,           -- e.g. "status", "customfield_10086"
  name VARCHAR(255) NOT NULL,
  field_type VARCHAR(32) NOT NULL,          -- "string" | "text" | "number" | "datetime"
  is_custom BOOLEAN DEFAULT FALSE,
  schema_type VARCHAR(64) NULL,             -- raw Jira schema.type
  schema_custom VARCHAR(255) NULL,          -- raw Jira schema.custom (e.g. ":textarea")
  last_fetched_at DATETIME NOT NULL,
  UNIQUE (jira_instance_id, field_id)
);

-- User-defined reports
CREATE TABLE reports (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(128) NOT NULL,
  jira_instance_id INT NOT NULL,
  jql_query TEXT NOT NULL,
  schedule_cron VARCHAR(64) NOT NULL,
  selected_fields JSON NOT NULL,            -- ordered list[str] of Jira field ids
  is_active BOOLEAN DEFAULT TRUE,
  last_run_at DATETIME NULL,
  last_run_status VARCHAR(32) NULL,
  last_error TEXT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

-- Sync audit trail
CREATE TABLE jira_run_history (
  id INT AUTO_INCREMENT PRIMARY KEY,
  report_id INT NOT NULL,
  started_at DATETIME NOT NULL,
  finished_at DATETIME NULL,
  status VARCHAR(32) NOT NULL,              -- running / success / failed / cancelled
  rows_inserted INT DEFAULT 0,
  pages_fetched INT DEFAULT 0,
  error_message TEXT NULL
);

-- One per report (created dynamically)
CREATE TABLE report_<id> (
  id INT AUTO_INCREMENT PRIMARY KEY,
  issue_key VARCHAR(50) NOT NULL,
  jira_created DATETIME NOT NULL,
  jira_updated DATETIME NOT NULL,
  fetched_at DATETIME NOT NULL,
  -- + one column per user-selected field (typed per the per-instance cache)
  INDEX idx_issue_key (issue_key),
  INDEX idx_jira_created (jira_created),
  INDEX idx_jira_updated (jira_updated)
);

-- One per report (created dynamically)
CREATE VIEW v_report_<id>_latest AS
SELECT <columns in user-selected order, with key/issuekey/created/updated aliased
        onto the system spine as appropriate>
FROM report_<id> t
INNER JOIN (
  SELECT issue_key, MAX(jira_updated) AS max_updated, MAX(fetched_at) AS max_fetched
  FROM report_<id> GROUP BY issue_key
) latest
  ON t.issue_key = latest.issue_key
 AND t.jira_updated = latest.max_updated
 AND t.fetched_at = latest.max_fetched;
```

### `key` / `issuekey` aliasing

Both `key` (Jira's real field id) and `issuekey` (the legacy id from the original `jsm_db.py`, which was never a real Jira field) are special-cased:

- `extract_issue_fields` materialises them as the issue's own `key`
- The view exposes them as `t.issue_key AS key` / `t.issue_key AS issuekey` in the user's position
- The data table doesn't get a separate column for them (the spine `issue_key` already holds the value)

This is what fixes the original script's "key has no value" bug — the legacy `issuekey` field id was being requested from Jira (which silently returned nothing) and stored as NULL. The new code reads from `issue.key` and aliases it in the view.

## API summary (admin)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/auth/login` | Sign in, set `jira_session` cookie |
| `POST` | `/api/auth/logout` | Clear the session cookie |
| `GET` | `/api/auth/me` | Current admin info |
| `GET` | `/api/admin/instances` | List Jira instances |
| `POST` | `/api/admin/instances` | Create an instance |
| `DELETE` | `/api/admin/instances/{id}` | Delete (rejected if reports exist) |
| `POST` | `/api/admin/instances/{id}/test` | Verify Jira auth + re-cache fields (heals schemas too) |
| `GET` | `/api/admin/instances/{id}/fields` | List cached fields |
| `POST` | `/api/admin/instances/{id}/run-all` | Queue a sync for every active report on this instance |
| `GET` | `/api/admin/reports` | List reports |
| `GET` | `/api/admin/reports/{id}` | Get one report |
| `POST` | `/api/admin/reports` | Create a report (also creates the per-report table + view) |
| `PATCH` | `/api/admin/reports/{id}` | Update a report (JQL, fields, schedule; ALTERs table if fields changed) |
| `DELETE` | `/api/admin/reports/{id}` | Delete a report (drops the table and view) |
| `POST` | `/api/admin/reports/{id}/truncate` | Empty the data table; keep schema and view |
| `POST` | `/api/admin/reports/{id}/run-now` | Queue a sync for this report |
| `GET` | `/api/admin/reports/{id}/runs` | Sync history for one report |
| `GET` | `/api/admin/runs` | Recent sync history across all reports |
| `POST` | `/api/admin/runs/{id}/cancel` | Stop a running sync (finishes the current page, then ends) |
| `GET` | `/api/admin/field-catalog` | Reserved for the static catalog (now empty — use `/instances/{id}/fields`) |

## API summary (public)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/reports` | List reports (summary) |
| `GET` | `/api/reports/{id}` | Report metadata + selected fields with name/type |
| `GET` | `/api/reports/{id}/issues?page=1&page_size=50&created_from=YYYY-MM-DD&created_to=YYYY-MM-DD&sort_field=…&sort_dir=asc&f_status=Open,In+Progress` | Paginated, filtered, sorted data |
| `GET` | `/api/reports/{id}/export?…` | CSV stream with the same filters / sort |

## End-to-end verification

```bash
# Confirm the admin user was created from .env
docker compose exec db mysql -uroot -p"$MYSQL_ROOT_PASSWORD" jira_db \
  -e "SELECT id, username FROM admin_user;"

# Confirm a report's table and view exist
docker compose exec db mysql -uroot -p"$MYSQL_ROOT_PASSWORD" jira_db \
  -e "SHOW TABLES LIKE 'report_%'; SHOW TABLES LIKE 'v_report_%';"

# Confirm the table has the right columns
docker compose exec db mysql -uroot -p"$MYSQL_ROOT_PASSWORD" jira_db \
  -e "DESCRIBE report_<id>;"

# Confirm the view returns the latest row per issue_key
docker compose exec db mysql -uroot -p"$MYSQL_ROOT_PASSWORD" jira_db \
  -e "SELECT issue_key, status, priority, jira_created FROM v_report_<id>_latest ORDER BY jira_created DESC LIMIT 5;"

# Confirm history is kept (more rows in the table than the view's row count)
docker compose exec db mysql -uroot -p"$MYSQL_ROOT_PASSWORD" jira_db \
  -e "SELECT (SELECT COUNT(*) FROM report_<id>) AS history_rows, (SELECT COUNT(*) FROM v_report_<id>_latest) AS latest_rows;"
```

Then in the UI:
1. `/admin/login` → sign in
2. Sub-nav appears below the header when on any `/admin/*` page; **Reports** and **Instances** links
3. Create a Jira instance → click **Test** (verifies and caches fields)
4. **Reports** → **New report** → pick the instance, JQL, schedule, drag fields, save
5. Click the **Run** button on a report row → watch the live progress bar in "Recent sync activity" (polls every 2s)
6. **Stop** button appears on running syncs — current page finishes, then the run ends with status `cancelled` and the rows preserved
7. Open `/r/<id>` → see the data, set date range, filter, sort columns, toggle visibility, export CSV
8. Refresh the page → filters, date range, column visibility, sort, and page size all persist (localStorage per report)

## CLI sync (the original `jsm_db.py`)

The original script is preserved at the project root as a thin wrapper around the new module:

```bash
docker compose exec backend python /app/jsm_db.py --report-id 1
```

It opens its own session, calls `run_report_sync`, and prints progress per page. Useful for ad-hoc syncs without going through the UI.

## Troubleshooting

**Backend won't start: `ENCRYPTION_KEY is not configured`**
Generate one and put it in `.env`:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**`Jira API returned 401` in the run history**
Token is wrong or revoked. Generate a new one at [id.atlassian.com](https://id.atlassian.com/manage-profile/security/api-tokens) and recreate the instance.

**Dates look off by 5:30 hours**
This app assumes Jira returns IST strings as-is. If your Jira actually returns UTC, the wall-clock digits in the report will differ from what Jira UI shows. Either accept it, or wrap `parse_jira_datetime` with an `astimezone(IST)` conversion.

**Page-level errors on column lookup**
The view's column list changed but the frontend still references the old column id. The frontend's `allColumns` is derived from the report's `selected_fields`, so this shouldn't happen — but if you hand-edited a report's `selected_fields` JSON in MySQL, regenerate it via the UI.

**`Run now` doesn't seem to do anything**
The sync runs as a background task. The run history table on the admin dashboard auto-refreshes every 2s. If the run stays in "running" for more than a few minutes, check `docker compose logs backend`.

**Sync is slow / timing out**
The retry layer handles transient blips. If a single page request is taking >60s, your network or Jira is genuinely slow. Check `docker compose logs backend` for retry warnings.

**Stale "running" rows after a backend restart**
The startup hook `_cleanup_orphaned_runs` marks any `running` run as `failed` with message "Interrupted by backend restart". The committed data is preserved.

**"Key" column is empty in the report view**
This was a bug in the original script. The fix is in — both `key` and `issuekey` (the legacy id) are now aliased to `issue.key`. The data is always populated. See the **key / issuekey aliasing** section above.

## Tech stack

- **Backend**: Python 3.11, FastAPI 0.115, SQLAlchemy 2.0, APScheduler 3.10, pymysql, cryptography (Fernet), bcrypt, python-jose (JWT), Pydantic 2 + pydantic-settings
- **Frontend**: React 18, Vite 5, TypeScript 5, TanStack Table 8, TanStack Query 5, TailwindCSS 3, shadcn/ui (Radix primitives), axios, react-hook-form + zod, date-fns, lucide-react, @dnd-kit
- **DB**: MySQL 8 with `time_zone=+05:30` and `utf8mb4_unicode_ci`
- **Deployment**: Docker Compose, multi-stage builds
