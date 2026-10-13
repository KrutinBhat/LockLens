"""Experiment run routes: launch, control (pause/resume/cancel), detail, history."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, paginate
from ..lab.runner import run_manager
from ..models import (DependencyEdge, ExecutionEvent, ExperimentRun, LockObservation,
                      Project, RunMetric, Scenario, ScenarioVersion, TxSession, User)
from ..schemas import (ExecutionEventOut, RunControlIn, RunCreateIn, RunDetailOut,
                       RunMetricOut, RunOut, TxSessionOut)

router = APIRouter(prefix="/api/runs", tags=["runs"])


def _can_access_scenario(db: Session, user: User, scenario: Scenario) -> bool:
    if scenario.is_template:
        return True
    project = db.get(Project, scenario.project_id)
    return bool(project and project.owner_id == user.id)


def _get_run(db: Session, user: User, run_id: int) -> ExperimentRun:
    run = db.get(ExperimentRun, run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="run not found")
    scenario = db.get(Scenario, run.scenario_id)
    if run.initiated_by != user.id and not _can_access_scenario(db, user, scenario):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="run not found")
    return run


def _run_out(db: Session, run: ExperimentRun) -> RunOut:
    sessions = db.scalars(select(TxSession).where(TxSession.run_id == run.id)).all()
    metrics = db.get(RunMetric, run.id)
    out = RunOut.model_validate(run)
    out.sessions = [TxSessionOut.model_validate(s) for s in sessions]
    out.metrics = RunMetricOut.model_validate(metrics) if metrics else None
    return out


@router.post("", response_model=RunOut, status_code=status.HTTP_201_CREATED)
def create_run(body: RunCreateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    version = db.get(ScenarioVersion, body.scenario_version_id)
    if not version:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="scenario version not found")
    scenario = db.get(Scenario, version.scenario_id)
    if not _can_access_scenario(db, user, scenario):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="scenario version not found")
    run = ExperimentRun(
        scenario_id=scenario.id, scenario_version_id=version.id, initiated_by=user.id,
        status="queued", definition_snapshot=version.definition,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    run_manager.launch(run.id)
    return _run_out(db, run)


@router.get("")
def list_runs(q: str = "", status_filter: str = "", page: int = 1, page_size: int = 20,
              user: User = Depends(current_user), db: Session = Depends(get_db)):
    page, page_size = paginate(page, page_size)
    cond = ExperimentRun.initiated_by == user.id
    stmt = select(ExperimentRun).where(cond)
    count_stmt = select(func.count(ExperimentRun.id)).where(cond)
    if status_filter:
        stmt = stmt.where(ExperimentRun.status == status_filter)
        count_stmt = count_stmt.where(ExperimentRun.status == status_filter)
    if q:
        like = f"%{q}%"
        sub = select(Scenario.id).where(Scenario.name.ilike(like))
        stmt = stmt.where(ExperimentRun.scenario_id.in_(sub))
        count_stmt = count_stmt.where(ExperimentRun.scenario_id.in_(sub))
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(ExperimentRun.created_at.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_run_out(db, r) for r in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/{run_id}", response_model=RunDetailOut)
def get_run(run_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    run = _get_run(db, user, run_id)
    base = _run_out(db, run)
    events = db.scalars(select(ExecutionEvent).where(ExecutionEvent.run_id == run.id)
                        .order_by(ExecutionEvent.seq)).all()
    edges = db.scalars(select(DependencyEdge).where(DependencyEdge.run_id == run.id)).all()
    snaps = db.scalars(select(LockObservation).where(LockObservation.run_id == run.id)
                       .order_by(LockObservation.observed_at).limit(400)).all()
    detail = RunDetailOut(**base.model_dump())
    detail.events = [ExecutionEventOut.model_validate(e) for e in events]
    detail.dependency_edges = [{"from_tx": e.from_tx, "to_tx": e.to_tx, "kind": e.kind, "evidence": e.evidence} for e in edges]
    detail.lock_snapshots = [s.snapshot for s in snaps]
    return detail


@router.post("/{run_id}/control", response_model=RunOut)
def control_run(run_id: int, body: RunControlIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    run = _get_run(db, user, run_id)
    if run.initiated_by != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="only the initiator can control a run")
    if run.status not in ("queued", "running", "paused"):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"run is {run.status}; cannot {body.action}")
    ok = run_manager.control(run.id, body.action)
    if not ok:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="run is not active in this process")
    if body.action == "pause":
        run.status = "paused"
    elif body.action == "resume":
        run.status = "running"
    elif body.action == "cancel":
        run.status = "cancelled"
    db.commit()
    return _run_out(db, run)
