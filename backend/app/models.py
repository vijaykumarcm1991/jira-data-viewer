"""SQLAlchemy models for the four fixed tables (admin, jira_instances, reports, run history).

Per-report tables (`report_<id>`) are created dynamically by `report_service.py` and are
NOT defined here as ORM models — they're built with SQLAlchemy Core at runtime.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


def _now_ist() -> datetime:
    """Server-side "now" in local time (the container's TZ=Asia/Kolkata makes this IST)."""
    return datetime.now()


class Base(DeclarativeBase):
    pass


class AdminUser(Base):
    __tablename__ = "admin_user"

    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=_now_ist)


class JiraInstance(Base):
    __tablename__ = "jira_instances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    domain = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    encrypted_token = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=_now_ist)
    updated_at = Column(
        DateTime, nullable=False, default=_now_ist, onupdate=_now_ist
    )

    fields = relationship(
        "JiraInstanceField", back_populates="instance", cascade="all, delete-orphan"
    )
    reports = relationship("Report", back_populates="jira_instance")


class JiraInstanceField(Base):
    """One row per Jira field per instance, cached from `GET /rest/api/3/field`.

    `field_type` is normalized to one of: "string", "text", "number", "datetime".
    `field_id` is the Jira-side id (`status`, `customfield_10086`, …) and is also
    used as the per-report column name.
    """

    __tablename__ = "jira_instance_fields"
    __table_args__ = (
        UniqueConstraint("jira_instance_id", "field_id", name="uq_instance_field"),
        Index("ix_instance_fields_instance", "jira_instance_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    jira_instance_id = Column(
        Integer, ForeignKey("jira_instances.id", ondelete="CASCADE"), nullable=False
    )
    field_id = Column(String(100), nullable=False)  # e.g. "status", "customfield_10086"
    name = Column(String(255), nullable=False)
    field_type = Column(String(32), nullable=False)  # "string" | "text" | "number" | "datetime"
    is_custom = Column(Boolean, nullable=False, default=False)
    schema_type = Column(String(64), nullable=True)  # raw Jira schema type (option, user, …)
    schema_custom = Column(String(255), nullable=True)  # raw Jira schema.custom (e.g. ":textarea")
    last_fetched_at = Column(DateTime, nullable=False, default=_now_ist)

    instance = relationship("JiraInstance", back_populates="fields")


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    jira_instance_id = Column(
        Integer, ForeignKey("jira_instances.id", ondelete="RESTRICT"), nullable=False
    )
    jql_query = Column(Text, nullable=False)
    schedule_cron = Column(String(64), nullable=False)
    selected_fields = Column(JSON, nullable=False)  # ordered list[str] of Jira field ids
    is_active = Column(Boolean, nullable=False, default=True)
    last_run_at = Column(DateTime, nullable=True)
    last_run_status = Column(String(32), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_now_ist)
    updated_at = Column(
        DateTime, nullable=False, default=_now_ist, onupdate=_now_ist
    )

    jira_instance = relationship("JiraInstance", back_populates="reports")
    run_history = relationship(
        "JiraRunHistory", back_populates="report", cascade="all, delete-orphan"
    )


class JiraRunHistory(Base):
    __tablename__ = "jira_run_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(
        Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    started_at = Column(DateTime, nullable=False, default=_now_ist)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(32), nullable=False)  # running / success / failed
    rows_inserted = Column(Integer, nullable=False, default=0)
    pages_fetched = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)

    report = relationship("Report", back_populates="run_history")
