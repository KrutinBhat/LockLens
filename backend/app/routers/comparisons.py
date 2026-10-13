"""Counterfactual Repair Lab: baseline vs controlled-candidate comparisons."""
from __future__ import annotations

import copy
import re
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_db
from ..deps import current_user
from ..lab.runner import run_manager
from ..models import Comparison, ExperimentRun, RunMetric, Project, Scenario, ScenarioVersion, TxSession, User
from ..schemas import ComparisonIn, ComparisonOut

router = APIRouter(prefix="/api/comparisons", tags=["comparisons"])


def apply_change(definition: dict, change: dict) -> dict:
    """Produce a candidate definition with exactly one controlled change applied.
    Supported: isolation override, SELECT ... FOR UPDATE rewrite, consistent lock ordering."""
    d = copy.deepcopy(definition)
    if iso := change.get("isolation"):
        iso = str(iso).upper()
        if iso not in ("READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"unsupported isolation {iso}")
        for tx in d["transactions"]:
            tx["isolation"] = iso
    if change.get("for_update"):
        for tx in d["transactions"]:
            for step in tx["steps"]:
                sql = (step.get("sql") or "").strip()
                if step.get("kind", "sql") == "sql" and sql.lower().startswith("select") \
                        and " for update" not in sql.lower():
                    step["sql"] = sql.rstrip(";") + " FOR UPDATE"
    if change.get("lock_order"):
        # Consistent lock ordering: sort UPDATE steps in every transaction by target id literal,
        # so all transactions touch rows in the same order.
        key_re = re.compile(r"where\s+id\s*=\s*(\d+)", re.IGNORECASE)
        for tx in d["transactions"]:
            steps = tx["steps"]
            updates = [s for s in steps if (s.get("sql") or "").lower().startswith("update")]
            if len(updates) > 1 and all(key_re.search(u["sql"]) for u in updates):
                updates_sorted = sorted(updates, key=lambda s: int(key_re.search(s["sql"]).group(1)))
                it = iter(updates_sorted)
                tx["steps"] = [next(it) if s in updates else s for s in steps]
    return d


def _run_sync(db_factory, scenario_id: int, definition: dict, user_id: int, note: str) -> int:
    """Create a scenario version + run and block until finished (bounded). Returns run id."""
    db: Session = db_factory()
    try:
        next_version = (db.scalar(
            select(func.max(ScenarioVersion.version)).where(ScenarioVersion.scenario_id == scenario_id)
        ) or 0) + 1
        v = ScenarioVersion(scenario_id=scenario_id, version=next_version,
                            definition=definition, change_note=note)
        db.add(v)
        db.flush()
        run = ExperimentRun(scenario_id=scenario_id, scenario_version_id=v.id,
                            initiated_by=user_id, status="queued", definition_snapshot=definition)
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id
    finally:
        db.close()
    run_manager.launch(run_id)
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        db = db_factory()
        try:
            r = db.get(ExperimentRun, run_id)
            if r.status not in ("queued", "running", "paused"):
                return r.id
        finally:
            db.close()
        time.sleep(0.25)
    raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, detail="comparison run timed out")


def _verdict(db: Session, baseline: ExperimentRun, candidate: ExperimentRun, change: dict) -> dict:
    def summarize(run: ExperimentRun):
        m = db.get(RunMetric, run.id)
        sessions = db.scalars(select(TxSession).where(TxSession.run_id == run.id)).all()
        return {
            "run_id": run.id, "status": run.status,
            "wall_time_ms": float(m.wall_time_ms) if m else None,
            "total_lock_wait_ms": float(m.total_lock_wait_ms) if m else None,
            "deadlocks": m.deadlocks if m else 0,
            "serialization_failures": m.serialization_failures if m else 0,
            "invariant_violations": m.invariant_violations if m else 0,
            "anomalies": [f["detector"] for f in (run.analysis or {}).get("findings", [])
                          if f["status"] == "confirmed" and f["severity"] in ("high", "critical")],
            "outcomes": {s.tx_name: s.outcome for s in sessions},
        }
    b, c = summarize(baseline), summarize(candidate)
    improved_correctness = c["invariant_violations"] < b["invariant_violations"] or (
        len(c["anomalies"]) < len(b["anomalies"]))
    verdict = {
        "baseline": b, "candidate": c, "change": change,
        "correctness_improved": improved_correctness,
        "latency_delta_ms": (c["wall_time_ms"] or 0) - (b["wall_time_ms"] or 0),
        "lock_wait_delta_ms": (c["total_lock_wait_ms"] or 0) - (b["total_lock_wait_ms"] or 0),
        "limitations": [
            "Single-run comparison: results are indicative, not proof of a fix.",
            "Schedules are checkpoint-deterministic, but timing metrics vary with load.",
            "Candidate was produced by a documented mechanical transformation; production SQL was never modified.",
        ],
    }
    return verdict


@router.post("", response_model=ComparisonOut, status_code=status.HTTP_201_CREATED)
def create_comparison(body: ComparisonIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    version = db.get(ScenarioVersion, body.scenario_version_id)
    if not version:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="scenario version not found")
    scenario = db.get(Scenario, version.scenario_id)
    project = db.get(Project, scenario.project_id) if scenario.project_id else None
    if not scenario.is_template and (not project or project.owner_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="scenario version not found")
    candidate_def = apply_change(version.definition, body.change)
    if candidate_def == version.definition:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="change had no effect on the scenario definition")
    # Persist comparison row first; execute both runs in a background thread.
    comp = Comparison(owner_id=user.id, name=body.name, baseline_run_id=None, candidate_run_id=None,
                      change=body.change, verdict={"status": "running"})
    db.add(comp)
    db.commit()
    db.refresh(comp)
    comp_id = comp.id
    scenario_id = scenario.id
    user_id = user.id

    def _work():
        db2 = SessionLocal()
        try:
            baseline_id = _run_sync(SessionLocal, scenario_id, version.definition, user_id, "comparison baseline")
            candidate_id = _run_sync(SessionLocal, scenario_id, candidate_def, user_id, f"candidate: {body.change}")
            baseline = db2.get(ExperimentRun, baseline_id)
            candidate = db2.get(ExperimentRun, candidate_id)
            c = db2.get(Comparison, comp_id)
            c.baseline_run_id = baseline_id
            c.candidate_run_id = candidate_id
            c.verdict = _verdict(db2, baseline, candidate, body.change)
            db2.commit()
        except Exception as exc:
            c = db2.get(Comparison, comp_id)
            if c:
                c.verdict = {"status": "failed", "error": str(exc)}
                db2.commit()
        finally:
            db2.close()

    threading.Thread(target=_work, daemon=True, name=f"comparison-{comp_id}").start()
    return ComparisonOut.model_validate(comp)


@router.get("", response_model=list[ComparisonOut])
def list_comparisons(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Comparison).where(Comparison.owner_id == user.id)
                      .order_by(Comparison.created_at.desc()).limit(100)).all()


@router.get("/{comp_id}", response_model=ComparisonOut)
def get_comparison(comp_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(Comparison, comp_id)
    if not c or c.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="comparison not found")
    return c
