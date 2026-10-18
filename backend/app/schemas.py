"""Pydantic API contracts."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from .lab import sqlguard


# ---------- auth ----------

class RegisterIn(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- projects ----------

class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = ""


class ProjectOut(BaseModel):
    id: int
    name: str
    description: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- scenarios ----------

class StepDef(BaseModel):
    kind: Literal["sql", "checkpoint", "commit", "rollback"] = "sql"
    sql: str | None = None
    name: str | None = None
    save_as: str | None = Field(default=None, pattern=r"^[a-zA-Z_][\w]*$")

    @field_validator("sql")
    @classmethod
    def _sql_ok(cls, v, info):
        kind = info.data.get("kind", "sql")
        if kind == "sql":
            if not v:
                raise ValueError("sql step requires sql text")
            sqlguard.validate_step_sql(v)  # raises ValueError on rejection
        return v

    @field_validator("name")
    @classmethod
    def _name_ok(cls, v, info):
        if info.data.get("kind") == "checkpoint" and not v:
            raise ValueError("checkpoint step requires a name")
        return v


class TxDef(BaseModel):
    name: str = Field(pattern=r"^T[1-4]$")
    isolation: Literal["READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"] = "READ COMMITTED"
    steps: list[StepDef] = Field(min_length=1)


class InvariantDef(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    sql: str
    expect: str

    @field_validator("sql")
    @classmethod
    def _probe_ok(cls, v):
        sqlguard.validate_select_sql(v)
        return v


class ScenarioDefinition(BaseModel):
    seed_sql: list[str] = Field(min_length=1)
    transactions: list[TxDef] = Field(min_length=1, max_length=4)
    invariants: list[InvariantDef] = []
    final_state_sql: str | None = None

    @field_validator("seed_sql")
    @classmethod
    def _seed_ok(cls, v):
        for group in v:
            sqlguard.validate_seed_sql(group)
        return v

    @field_validator("final_state_sql")
    @classmethod
    def _probe_ok(cls, v):
        if v:
            sqlguard.validate_select_sql(v)
        return v

    @field_validator("transactions")
    @classmethod
    def _tx_ok(cls, v):
        names = [t.name for t in v]
        if len(names) != len(set(names)):
            raise ValueError("transaction names must be unique")
        return v


class ScenarioIn(BaseModel):
    project_id: int | None = None
    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_\-]+$")
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(default="custom", max_length=60)
    description: str = ""
    definition: ScenarioDefinition
    change_note: str = ""


class ScenarioVersionOut(BaseModel):
    id: int
    version: int
    definition: dict
    change_note: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ScenarioOut(BaseModel):
    id: int
    project_id: int | None
    is_template: bool
    key: str
    name: str
    category: str
    description: str
    created_at: datetime
    latest_version: ScenarioVersionOut | None = None

    model_config = {"from_attributes": True}


# ---------- runs ----------

class RunCreateIn(BaseModel):
    scenario_version_id: int


class RunControlIn(BaseModel):
    action: Literal["pause", "resume", "cancel"]


class TxSessionOut(BaseModel):
    tx_name: str
    isolation_level: str
    backend_pid: int | None
    outcome: str
    error_sqlstate: str | None
    error_message: str
    model_config = {"from_attributes": True}


class ExecutionEventOut(BaseModel):
    seq: int
    tx_name: str | None
    kind: str
    step_index: int | None
    sql_text: str
    result: dict
    duration_ms: float | None
    at: datetime
    model_config = {"from_attributes": True}


class RunMetricOut(BaseModel):
    wall_time_ms: float
    total_lock_wait_ms: float
    max_lock_wait_ms: float
    steps_executed: int
    commits: int
    rollbacks: int
    deadlocks: int
    serialization_failures: int
    invariant_violations: int
    model_config = {"from_attributes": True}


class RunOut(BaseModel):
    id: int
    scenario_id: int
    scenario_version_id: int
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    error: str
    analysis: dict
    created_at: datetime
    sessions: list[TxSessionOut] = []
    metrics: RunMetricOut | None = None
    model_config = {"from_attributes": True}


class RunDetailOut(RunOut):
    events: list[ExecutionEventOut] = []
    dependency_edges: list[dict] = []
    lock_snapshots: list[dict] = []


# ---------- comparison ----------

class ComparisonIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scenario_version_id: int
    change: dict  # {"isolation": "..."} | {"for_update": true} | {"lock_order": true}


class ComparisonOut(BaseModel):
    id: int
    name: str
    baseline_run_id: int | None
    candidate_run_id: int | None
    change: dict
    verdict: dict
    created_at: datetime
    model_config = {"from_attributes": True}


# ---------- misc ----------

class Page(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int


class ApiError(BaseModel):
    detail: str
    code: str = "error"
