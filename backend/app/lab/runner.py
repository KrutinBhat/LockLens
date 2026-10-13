"""Run manager: executes ScheduleEngine in background threads and persists
runs, sessions, events, lock snapshots, dependency edges, metrics and
analysis into the metadata database."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..db import SessionLocal
from .. import models
from . import analyzers
from .engine import ScheduleEngine

log = logging.getLogger("locklens.runner")


class RunHandle:
    def __init__(self, run_id: int, engine: ScheduleEngine, thread: threading.Thread):
        self.run_id = run_id
        self.engine = engine
        self.thread = thread


class RunManager:
    """In-process registry of active runs. (Single-process deployments; for
    multi-worker deployments use an external coordinator — documented.)"""

    def __init__(self) -> None:
        self._active: dict[int, RunHandle] = {}
        self._lock = threading.Lock()

    def launch(self, run_id: int) -> None:
        engine_holder: dict = {}

        def _work() -> None:
            db = SessionLocal()
            try:
                run = db.get(models.ExperimentRun, run_id)
                if run is None:
                    return
                run.status = "running"
                run.started_at = datetime.now(timezone.utc)
                db.commit()
                engine = ScheduleEngine(run.definition_snapshot, run_id=run_id)
                engine_holder["engine"] = engine
                with self._lock:
                    if run_id in self._active:
                        self._active[run_id].engine = engine
                engine.start()
                result = engine.join()
                self._persist_result(db, run, engine, result)
            except Exception as exc:  # pragma: no cover - defensive
                log.exception("run %s failed", run_id)
                try:
                    run = db.get(models.ExperimentRun, run_id)
                    if run:
                        run.status = "failed"
                        run.error = str(exc)
                        run.finished_at = datetime.now(timezone.utc)
                        db.commit()
                except Exception:
                    pass
            finally:
                db.close()
                with self._lock:
                    self._active.pop(run_id, None)

        t = threading.Thread(target=_work, daemon=True, name=f"run-{run_id}")
        with self._lock:
            self._active[run_id] = RunHandle(run_id, engine_holder.get("engine"), t)
        t.start()

    def control(self, run_id: int, action: str) -> bool:
        with self._lock:
            handle = self._active.get(run_id)
        if not handle or not handle.engine:
            return False
        if action == "pause":
            handle.engine.pause()
        elif action == "resume":
            handle.engine.resume()
        elif action == "cancel":
            handle.engine.cancel()
        return True

    def is_active(self, run_id: int) -> bool:
        with self._lock:
            return run_id in self._active

    # ---- persistence ---------------------------------------------------

    def _persist_result(self, db: Session, run: models.ExperimentRun, engine: ScheduleEngine, result) -> None:
        events_payload = [
            {"seq": e.seq, "tx_name": e.tx_name, "kind": e.kind, "step_index": e.step_index,
             "sql_text": e.sql_text, "result": e.result, "duration_ms": e.duration_ms, "at": e.at}
            for e in engine.recorder.events
        ]
        sessions_payload = [
            {"tx_name": s.tx_name, "isolation_level": s.isolation_level, "backend_pid": s.backend_pid,
             "outcome": s.outcome, "error_sqlstate": s.error_sqlstate, "error_message": s.error_message,
             "lock_wait_ms": s.lock_wait_ms}
            for s in result.sessions
        ]

        analysis = analyzers.analyze(
            run.definition_snapshot, events_payload, sessions_payload,
            result.invariant_results, result.final_state, result.serial_baselines,
        )

        run.status = (
            "cancelled" if result.status == "cancelled"
            else "anomaly_detected" if analysis["anomaly_detected"]
            else "succeeded"
        )
        if result.status == "timed_out":
            run.status = "timed_out"
        run.finished_at = datetime.now(timezone.utc)
        run.analysis = analysis

        for s in result.sessions:
            db.add(models.TxSession(
                run_id=run.id, tx_name=s.tx_name, isolation_level=s.isolation_level,
                backend_pid=s.backend_pid, outcome=s.outcome, error_sqlstate=s.error_sqlstate,
                error_message=s.error_message,
            ))
        for e in engine.recorder.events:
            db.add(models.ExecutionEvent(
                run_id=run.id, seq=e.seq, tx_name=e.tx_name, kind=e.kind, step_index=e.step_index,
                sql_text=e.sql_text, result=e.result, duration_ms=e.duration_ms,
                at=datetime.fromisoformat(e.at),
            ))
        for snap in result.lock_snapshots:
            db.add(models.LockObservation(run_id=run.id, observed_at=datetime.fromisoformat(snap["at"]),
                                          snapshot=snap))

        pid_to_tx = {s.backend_pid: s.tx_name for s in result.sessions if s.backend_pid}
        edges = analyzers.observed_wait_edges(result.lock_snapshots, pid_to_tx)
        edges += analyzers.declared_dependency_edges(run.definition_snapshot)
        for e in edges:
            db.add(models.DependencyEdge(run_id=run.id, from_tx=e["from_tx"], to_tx=e["to_tx"],
                                         kind=e["kind"], evidence=e["evidence"]))

        waits = [s.lock_wait_ms for s in result.sessions]
        db.add(models.RunMetric(
            run_id=run.id,
            wall_time_ms=result.wall_time_ms,
            total_lock_wait_ms=sum(waits),
            max_lock_wait_ms=max(waits, default=0),
            steps_executed=sum(1 for e in engine.recorder.events if e.kind in ("step_ok", "step_error")),
            commits=sum(1 for s in result.sessions if s.outcome == "committed"),
            rollbacks=sum(1 for s in result.sessions if s.outcome == "rolled_back"),
            deadlocks=sum(1 for s in result.sessions if s.outcome == "aborted_deadlock"),
            serialization_failures=sum(1 for s in result.sessions if s.outcome == "aborted_serialization"),
            invariant_violations=sum(1 for r in result.invariant_results if not r["ok"]),
        ))
        db.add(models.AuditEvent(user_id=run.initiated_by, action="run.finished",
                                 detail={"run_id": run.id, "status": run.status}))
        db.commit()


run_manager = RunManager()
