"""FastAPI app entry point.

Wires up the DB, ensures the admin user exists, starts the scheduler, and mounts the
public + admin routers.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import SessionLocal, engine
from .models import AdminUser, Base
from .routers import admin as admin_router
from .routers import auth as auth_router
from .routers import public as public_router
from .scheduler import shutdown_scheduler, start_scheduler
from .security import hash_password


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The connect-listener in database.py sets the IST time_zone on every new connection.
    Base.metadata.create_all(bind=engine)
    _ensure_admin_user()
    _run_migrations()
    _cleanup_orphaned_runs()

    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()


def _cleanup_orphaned_runs() -> None:
    """Mark any "running" runs from a previous backend session as failed.

    A backend restart kills in-flight syncs (the threads die), but their
    JiraRunHistory rows are left in `running` state because the sync code
    never had a chance to update them. Promote them to `failed` so the
    admin UI doesn't show stale "running" entries forever.
    """
    from .models import JiraRunHistory

    with SessionLocal() as db:
        orphaned = (
            db.query(JiraRunHistory)
            .filter(JiraRunHistory.status == "running")
            .all()
        )
        for run in orphaned:
            run.status = "failed"
            run.error_message = "Interrupted by backend restart"
            run.finished_at = datetime.now()
        if orphaned:
            db.commit()


def _run_migrations() -> None:
    """Lightweight, additive migrations that run on startup.

    Each one is a no-op if the change is already in place, so it's safe to re-run
    on every boot. New migrations should be appended; never edit or remove an
    existing one (it may still need to run for a database that was started on
    an older version of the app).
    """
    from sqlalchemy import text

    with engine.begin() as conn:
        # M1: jira_instance_fields.schema_custom was added after the first deploy.
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(jira_instance_fields)")).fetchall()} \
            if conn.dialect.name == "sqlite" \
            else {row[0] for row in conn.execute(
                text(
                    "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'jira_instance_fields'"
                )
            ).fetchall()}
        if "schema_custom" not in cols:
            conn.execute(text(
                "ALTER TABLE jira_instance_fields ADD COLUMN schema_custom VARCHAR(255) NULL"
            ))


def _ensure_admin_user() -> None:
    """Sync the single admin user from .env into the admin_user table.

    .env is authoritative — if ADMIN_PASSWORD changed, the DB hash is updated.
    """
    from datetime import datetime

    with SessionLocal() as db:
        user = db.query(AdminUser).filter(AdminUser.id == 1).first()
        if user is None:
            user = AdminUser(
                id=1,
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
                created_at=datetime.now(),
            )
            db.add(user)
        else:
            user.username = settings.admin_username
            user.password_hash = hash_password(settings.admin_password)
        db.commit()


app = FastAPI(title="Jira Data Viewer", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router, prefix="/api/auth", tags=["auth"])
app.include_router(admin_router.router, prefix="/api/admin", tags=["admin"])
app.include_router(public_router.router, prefix="/api", tags=["public"])


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "tz": "Asia/Kolkata"}
