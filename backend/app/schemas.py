"""Pydantic schemas for the API."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---- Auth ----
class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    username: str


# ---- Jira instance ----
class JiraInstanceIn(BaseModel):
    name: str = Field(..., max_length=128)
    domain: str = Field(..., max_length=255)
    email: str = Field(..., max_length=255)
    api_token: str = Field(..., min_length=1)
    is_active: bool = True


class JiraInstanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    domain: str
    email: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ---- Report ----
class ReportIn(BaseModel):
    name: str = Field(..., max_length=128)
    jira_instance_id: int
    jql_query: str = Field(..., min_length=1)
    schedule_cron: str = Field(..., min_length=1)
    selected_fields: list[str] = Field(..., min_length=1)
    is_active: bool = True
    history_retention_days: int = 0  # 0 = keep latest per key only


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    jira_instance_id: int
    jira_instance_name: str | None = None
    jql_query: str
    schedule_cron: str
    selected_fields: list[str]
    is_active: bool
    history_retention_days: int = 0
    last_run_at: datetime | None
    last_run_status: str | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class ReportUpdate(BaseModel):
    name: str | None = None
    jql_query: str | None = None
    schedule_cron: str | None = None
    selected_fields: list[str] | None = None
    is_active: bool | None = None
    history_retention_days: int | None = None


# ---- Run history ----
class RunHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    report_id: int
    started_at: datetime
    finished_at: datetime | None
    status: Literal["running", "success", "failed", "cancelled"]
    rows_inserted: int
    pages_fetched: int
    error_message: str | None


# ---- Public issues ----
class IssueRow(BaseModel):
    data: dict
    total: int
    page: int
    page_size: int


# ---- Field catalog ----
class FieldDefOut(BaseModel):
    id: str
    name: str
    type: Literal["string", "text", "number", "datetime"]
    jira_field: str
    length: int | None = None
