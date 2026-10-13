"""SQLAlchemy models — application metadata schema (PostgreSQL).

Experiment execution happens in a separate lab database; this schema stores
durable records about users, projects, scenarios, runs, evidence and metrics.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)

    projects: Mapped[list["Project"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    owner: Mapped[User] = relationship(back_populates="projects")
    scenarios: Mapped[list["Scenario"]] = relationship(back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_project_owner_name"),)


class Scenario(Base, TimestampMixin):
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    # Library scenarios ship with the product (owner_id NULL, is_template True)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)  # lost_update, write_skew, ...
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    project: Mapped[Project | None] = relationship(back_populates="scenarios")
    versions: Mapped[list["ScenarioVersion"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan", order_by="ScenarioVersion.version"
    )
    runs: Mapped[list["ExperimentRun"]] = relationship(back_populates="scenario")

    __table_args__ = (UniqueConstraint("project_id", "key", name="uq_scenario_project_key"),)


class ScenarioVersion(Base, TimestampMixin):
    __tablename__ = "scenario_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # definition: {seed_sql: [...], transactions: [{name, isolation, steps:[...]}], invariants: [...]}
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    change_note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    scenario: Mapped[Scenario] = relationship(back_populates="versions")
    runs: Mapped[list["ExperimentRun"]] = relationship(back_populates="scenario_version")

    __table_args__ = (UniqueConstraint("scenario_id", "version", name="uq_scenario_version"),)


class ExperimentRun(Base, TimestampMixin):
    __tablename__ = "experiment_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id", ondelete="RESTRICT"), nullable=False, index=True)
    scenario_version_id: Mapped[int] = mapped_column(ForeignKey("scenario_versions.id", ondelete="RESTRICT"), nullable=False)
    initiated_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    # queued | running | paused | succeeded | anomaly_detected | failed | cancelled | timed_out
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", index=True)
    definition_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)  # reproducible config
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    analysis: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # findings w/ evidence refs

    scenario: Mapped[Scenario] = relationship(back_populates="runs")
    scenario_version: Mapped[ScenarioVersion] = relationship(back_populates="runs")
    sessions: Mapped[list["TxSession"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    events: Mapped[list["ExecutionEvent"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    lock_observations: Mapped[list["LockObservation"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    metrics: Mapped["RunMetric | None"] = relationship(back_populates="run", cascade="all, delete-orphan", uselist=False)

    __table_args__ = (Index("ix_runs_scenario_created", "scenario_id", "created_at"),)


class TxSession(Base):
    __tablename__ = "tx_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("experiment_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    tx_name: Mapped[str] = mapped_column(String(16), nullable=False)  # T1..T4
    isolation_level: Mapped[str] = mapped_column(String(40), nullable=False)
    backend_pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # committed | rolled_back | aborted_deadlock | aborted_serialization | aborted_timeout | cancelled | failed
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    error_sqlstate: Mapped[str | None] = mapped_column(String(8), nullable=True)
    error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped[ExperimentRun] = relationship(back_populates="sessions")

    __table_args__ = (UniqueConstraint("run_id", "tx_name", name="uq_txsession_run_tx"),)


class ExecutionEvent(Base):
    __tablename__ = "execution_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("experiment_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)  # global ordered sequence
    tx_name: Mapped[str | None] = mapped_column(String(16), nullable=True)  # NULL = orchestrator
    # step_start | step_ok | step_error | checkpoint_wait | checkpoint_release |
    # begin | commit | rollback | paused | resumed | cancelled | timeout | note
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    step_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sql_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # rows / rowcount / error
    duration_ms: Mapped[float | None] = mapped_column(Numeric(12, 3), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    run: Mapped[ExperimentRun] = relationship(back_populates="events")

    __table_args__ = (UniqueConstraint("run_id", "seq", name="uq_event_run_seq"),)


class LockObservation(Base):
    __tablename__ = "lock_observations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("experiment_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    # snapshot payload: list of {pid, locktype, mode, granted, relation, page, tuple, blocked_by[]}
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)

    run: Mapped[ExperimentRun] = relationship(back_populates="lock_observations")


class DependencyEdge(Base):
    __tablename__ = "dependency_edges"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("experiment_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    from_tx: Mapped[str] = mapped_column(String(16), nullable=False)
    to_tx: Mapped[str] = mapped_column(String(16), nullable=False)
    # observed_wait (from pg_locks) | declared_rw | declared_wr | declared_ww (from step metadata)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class RunMetric(Base):
    __tablename__ = "run_metrics"

    run_id: Mapped[int] = mapped_column(ForeignKey("experiment_runs.id", ondelete="CASCADE"), primary_key=True)
    wall_time_ms: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    total_lock_wait_ms: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    max_lock_wait_ms: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    steps_executed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    commits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rollbacks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deadlocks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    serialization_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invariant_violations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    run: Mapped[ExperimentRun] = relationship(back_populates="metrics")


class Comparison(Base, TimestampMixin):
    __tablename__ = "comparisons"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    baseline_run_id: Mapped[int | None] = mapped_column(ForeignKey("experiment_runs.id", ondelete="RESTRICT"), nullable=True)
    candidate_run_id: Mapped[int | None] = mapped_column(ForeignKey("experiment_runs.id", ondelete="RESTRICT"), nullable=True)
    # controlled change description, e.g. {"isolation": "SERIALIZABLE"} or {"step_patch": "FOR UPDATE"}
    change: Mapped[dict] = mapped_column(JSON, nullable=False)
    verdict: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
