from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

engine: Engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=10,
    max_overflow=20,
    future=True,
)


@event.listens_for(engine, "connect")
def _set_session_timezone(dbapi_connection, connection_record):  # noqa: ANN001
    """Force every new MySQL connection to use IST (+05:30).

    Dates are stored as naive DATETIME columns; with the session time_zone set,
    MySQL's NOW() and date comparisons are evaluated in IST, matching what the
    backend writes and reads.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("SET time_zone = '+05:30'")
    finally:
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_db() -> Generator[Session, None, None]:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
