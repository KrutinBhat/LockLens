"""Deterministic schedule engine.

Coordinates real PostgreSQL sessions (one psycopg connection + thread per
transaction) through named checkpoints (application-level barriers), with
pause/resume, cancellation, timeouts, ordered event recording and lock
polling. All experiment SQL runs against the lab database ONLY.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg import errors as pgerr

from ..config import settings
from . import sqlguard

log = logging.getLogger("locklens.engine")

ISOLATION_LEVELS = {
    "READ COMMITTED": "read committed",
    "REPEATABLE READ": "repeatable read",
    "SERIALIZABLE": "serializable",
}


class Cancelled(Exception):
    pass


class StepError(Exception):
    def __init__(self, sqlstate: str | None, message: str):
        super().__init__(message)
        self.sqlstate = sqlstate
        self.message = message


class Checkpoint:
    """Named, counted barrier with cancellation/timeout release."""

    def __init__(self, name: str, parties: int):
        self.name = name
        self.parties = max(1, parties)
        self._arrived = 0
        self._released = False
        self._cond = threading.Condition()

    def wait(self, cancel: threading.Event, timeout_s: float) -> str:
        with self._cond:
            self._arrived += 1
            if self._arrived >= self.parties:
                self._released = True
                self._cond.notify_all()
                return "released"
            deadline = time.monotonic() + timeout_s
            while not self._released:
                if cancel.is_set():
                    raise Cancelled()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"checkpoint {self.name!r} timed out")
                self._cond.wait(min(0.1, remaining))
            return "released"

    def release(self) -> None:
        with self._cond:
            self._released = True
            self._cond.notify_all()


@dataclass
class RecordedEvent:
    seq: int
    tx_name: str | None
    kind: str
    step_index: int | None
    sql_text: str
    result: dict[str, Any]
    duration_ms: float | None
    at: str


class EventRecorder:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seq = 0
        self.events: list[RecordedEvent] = []

    def record(self, tx_name: str | None, kind: str, step_index: int | None = None,
               sql_text: str = "", result: dict | None = None, duration_ms: float | None = None) -> int:
        with self._lock:
            self._seq += 1
            ev = RecordedEvent(
                seq=self._seq, tx_name=tx_name, kind=kind, step_index=step_index,
                sql_text=sql_text, result=result or {}, duration_ms=duration_ms,
                at=datetime.now(timezone.utc).isoformat(),
            )
            self.events.append(ev)
            return ev.seq


@dataclass
class SessionResult:
    tx_name: str
    isolation_level: str
    backend_pid: int | None = None
    outcome: str = "pending"
    error_sqlstate: str | None = None
    error_message: str = ""
    lock_wait_ms: float = 0.0


@dataclass
class RunResult:
    status: str  # succeeded | anomaly_detected | failed | cancelled | timed_out
    sessions: list[SessionResult] = field(default_factory=list)
    lock_snapshots: list[dict] = field(default_factory=list)
    invariant_results: list[dict] = field(default_factory=list)
    final_state: list[dict] = field(default_factory=list)
    serial_baselines: dict[str, list[dict]] = field(default_factory=dict)  # order -> probe rows
    wall_time_ms: float = 0.0
    error: str = ""


class LockPoller(threading.Thread):
    """Polls pg_locks/pg_stat_activity on the lab DB while a run executes."""

    def __init__(self, lab_dsn: str, pids: callable, stop: threading.Event,
                 snapshots: list[dict], interval_ms: int, wait_tracker: dict[int, float],
                 max_snapshots: int = 400):
        super().__init__(daemon=True, name="locklens-lock-poller")
        self.lab_dsn = lab_dsn
        self.pids = pids
        self.stop_event = stop
        self.snapshots = snapshots
        self.interval = max(20, interval_ms) / 1000.0
        self.wait_tracker = wait_tracker
        self.max_snapshots = max_snapshots

    def run(self) -> None:
        try:
            conn = psycopg.connect(self.lab_dsn, autocommit=True)
        except Exception as exc:  # pragma: no cover
            log.warning("lock poller could not connect: %s", exc)
            return
        query = """
            SELECT l.pid, l.locktype, l.mode, l.granted,
                   COALESCE(l.relation::regclass::text, '') AS relation,
                   l.page, l.tuple,
                   a.wait_event_type, a.wait_event,
                   pg_blocking_pids(l.pid) AS blocked_by
            FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid
            WHERE l.pid = ANY(%s)
            ORDER BY l.pid, l.locktype
        """
        while not self.stop_event.is_set():
            pids = [p for p in self.pids() if p]
            if pids:
                try:
                    rows = conn.execute(query, (pids,)).fetchall()
                    cols = ["pid", "locktype", "mode", "granted", "relation", "page", "tuple",
                            "wait_event_type", "wait_event", "blocked_by"]
                    snap = {
                        "at": datetime.now(timezone.utc).isoformat(),
                        "locks": [dict(zip(cols, r)) for r in rows],
                    }
                    if len(self.snapshots) < self.max_snapshots:
                        self.snapshots.append(snap)
                    # approximate lock-wait attribution: pid observed waiting on a Lock
                    waiting = {r[0] for r in rows if r[7] == "Lock"}
                    for pid in pids:
                        if pid in waiting:
                            self.wait_tracker[pid] = self.wait_tracker.get(pid, 0.0) + self.interval * 1000.0
                except Exception as exc:
                    log.debug("lock poll failed: %s", exc)
            self.stop_event.wait(self.interval)
        conn.close()


def _connect_lab(autocommit: bool = False) -> psycopg.Connection:
    conn = psycopg.connect(settings.lab_database_url, autocommit=autocommit)
    return conn


def _bounded_rows(cur: psycopg.Cursor, limit: int) -> dict:
    if cur.description is None:
        return {"rowcount": cur.rowcount}
    cols = [d.name for d in cur.description]
    rows = cur.fetchmany(limit + 1)
    truncated = len(rows) > limit
    rows = rows[:limit]
    return {
        "columns": cols,
        "rows": [[None if v is None else (str(v) if not isinstance(v, (int, float, bool)) else v) for v in r] for r in rows],
        "rowcount": cur.rowcount,
        "truncated": truncated,
    }


class TxWorker(threading.Thread):
    def __init__(self, engine: "ScheduleEngine", txdef: dict):
        super().__init__(daemon=True, name=f"locklens-{txdef['name']}")
        self.engine = engine
        self.txdef = txdef
        self.result = SessionResult(tx_name=txdef["name"], isolation_level=txdef.get("isolation", "READ COMMITTED"))


    def run(self) -> None:
        eng = self.engine
        tx = self.txdef["name"]
        rec = eng.recorder
        conn: psycopg.Connection | None = None
        try:
            conn = _connect_lab()
            conn.execute(f"SET statement_timeout = {int(settings.statement_timeout_ms)}")
            conn.execute(f"SET lock_timeout = {int(settings.lock_timeout_ms)}")
            conn.execute(f"SET idle_in_transaction_session_timeout = {int(settings.run_hard_timeout_seconds * 1000)}")
            iso = ISOLATION_LEVELS.get(self.result.isolation_level.upper())
            if iso is None:
                raise StepError(None, f"unsupported isolation level {self.result.isolation_level!r}")
            conn.execute(f"BEGIN ISOLATION LEVEL {iso}")
            self.result.backend_pid = conn.info.backend_pid
            rec.record(tx, "begin", result={"isolation": self.result.isolation_level, "pid": self.result.backend_pid})
            eng._register_pid(self.result.backend_pid)
            eng._worker_started()
            variables: dict[str, str] = {}

            for idx, step in enumerate(self.txdef.get("steps", [])):
                eng._check_cancel()
                eng._pause_gate(tx)
                kind = step.get("kind", "sql")
                if kind == "checkpoint":
                    name = step["name"]
                    rec.record(tx, "checkpoint_wait", step_index=idx, result={"checkpoint": name})
                    status = eng.wait_checkpoint(name)
                    rec.record(tx, "checkpoint_release", step_index=idx, result={"checkpoint": name, "status": status})
                    continue
                if kind == "commit":
                    t0 = time.perf_counter()
                    try:
                        conn.commit()
                    except psycopg.Error as exc:
                        rec.record(tx, "step_error", step_index=idx, sql_text="COMMIT",
                                   result={"sqlstate": exc.sqlstate, "message": str(exc).strip()},
                                   duration_ms=_ms(t0))
                        raise StepError(exc.sqlstate, str(exc).strip()) from exc
                    rec.record(tx, "commit", step_index=idx, duration_ms=_ms(t0))
                    self.result.outcome = "committed"
                    if idx < len(self.txdef.get("steps", [])) - 1:
                        # mid-sequence commit: start the next transaction in this session
                        conn.execute(f"BEGIN ISOLATION LEVEL {iso}")
                        rec.record(tx, "begin", result={"isolation": self.result.isolation_level,
                                                        "pid": self.result.backend_pid, "seq": idx + 1})
                        continue
                    return
                if kind == "rollback":
                    t0 = time.perf_counter()
                    conn.rollback()
                    rec.record(tx, "rollback", step_index=idx, duration_ms=_ms(t0))
                    self.result.outcome = "rolled_back"
                    return
                # sql step
                sql = sqlguard.validate_step_sql(substitute_placeholders(step["sql"], variables))
                rec.record(tx, "step_start", step_index=idx, sql_text=sql)
                t0 = time.perf_counter()
                try:
                    cur = conn.execute(sql)
                    payload = _bounded_rows(cur, settings.max_step_rows)
                    rec.record(tx, "step_ok", step_index=idx, sql_text=sql, result=payload, duration_ms=_ms(t0))
                    if step.get("save_as"):
                        rows = payload.get("rows") or []
                        if not rows or not rows[0]:
                            raise StepError(None, f"save_as {step['save_as']!r}: step returned no rows")
                        variables[step["save_as"]] = to_literal(rows[0][0])
                except psycopg.Error as exc:
                    sqlstate = exc.sqlstate
                    rec.record(tx, "step_error", step_index=idx, sql_text=sql,
                               result={"sqlstate": sqlstate, "message": str(exc).strip()}, duration_ms=_ms(t0))
                    raise StepError(sqlstate, str(exc).strip()) from exc
            # no explicit commit step -> engine commits by default
            eng._check_cancel()
            try:
                conn.commit()
            except psycopg.Error as exc:
                rec.record(tx, "step_error", sql_text="COMMIT",
                           result={"sqlstate": exc.sqlstate, "message": str(exc).strip()})
                raise StepError(exc.sqlstate, str(exc).strip()) from exc
            rec.record(tx, "commit", result={"implicit": True})
            self.result.outcome = "committed"
        except Cancelled:
            self.result.outcome = "cancelled"
            rec.record(tx, "cancelled")
            self._safe_rollback(conn)
        except TimeoutError as exc:
            self.result.outcome = "aborted_timeout"
            self.result.error_message = str(exc)
            rec.record(tx, "timeout", result={"message": str(exc)})
            self._safe_rollback(conn)
        except StepError as exc:
            self.result.error_sqlstate = exc.sqlstate
            self.result.error_message = exc.message
            if eng.cancel_event.is_set():
                self.result.outcome = "cancelled"
            elif exc.sqlstate == "40P01":
                self.result.outcome = "aborted_deadlock"
            elif exc.sqlstate == "40001":
                self.result.outcome = "aborted_serialization"
            elif exc.sqlstate == "55P03":
                self.result.outcome = "aborted_lock_timeout"
            elif exc.sqlstate == "57014":
                self.result.outcome = "aborted_statement_timeout"
            else:
                self.result.outcome = "failed"
            self._safe_rollback(conn)
        except Exception as exc:  # pragma: no cover - defensive
            self.result.outcome = "failed"
            self.result.error_message = str(exc)
            rec.record(tx, "error", result={"message": str(exc)})
            self._safe_rollback(conn)
        finally:
            eng._worker_done()
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def _safe_rollback(self, conn) -> None:
        if conn is None:
            return
        try:
            conn.rollback()
            self.engine.recorder.record(self.txdef["name"], "rollback", result={"implicit": True})
            if self.result.outcome in ("pending",):
                self.result.outcome = "rolled_back"
        except Exception:
            pass


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000.0, 3)


_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z_][\w]*)\s*\}\}")


def to_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return "'" + str(value).replace("'", "''") + "'"


def substitute_placeholders(sql: str, variables: dict[str, str]) -> str:
    """Replace {{name}} with a saved, safely-quoted literal from a prior step."""
    def rep(m: re.Match) -> str:
        name = m.group(1)
        if name not in variables:
            raise StepError(None, f"placeholder {{{{{name}}}}} has no saved value in this transaction")
        return variables[name]
    return _PLACEHOLDER.sub(rep, sql)


class ScheduleEngine:
    """Runs one scenario definition against the lab database."""

    def __init__(self, definition: dict, run_id: int | None = None):
        self.definition = definition
        self.run_id = run_id
        self.recorder = EventRecorder()
        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()  # set => paused
        self._pause_cond = threading.Condition()
        self._checkpoints: dict[str, Checkpoint] = {}
        self._pids: list[int] = []
        self._pids_lock = threading.Lock()
        self._started = threading.Event()
        self._active_workers = 0
        self._workers_cond = threading.Condition()
        self._snapshots: list[dict] = []
        self._wait_tracker: dict[int, float] = {}
        self._poller_stop = threading.Event()
        self._poller: LockPoller | None = None
        self.workers: list[TxWorker] = []
        self._t_start: float = 0.0
        self._t_workers_done: float = 0.0

    # ---- lifecycle -----------------------------------------------------

    def prepare(self) -> None:
        counts: dict[str, int] = {}
        for tx in self.definition.get("transactions", []):
            for step in tx.get("steps", []):
                if step.get("kind") == "checkpoint":
                    counts[step["name"]] = counts.get(step["name"], 0) + 1
        self._checkpoints = {n: Checkpoint(n, c) for n, c in counts.items()}

    def start(self) -> None:
        self.prepare()
        self._reset_and_seed()
        self.recorder.record(None, "seeded", result={"seed_statements": len(self.definition.get("seed_sql", []))})
        self._poller = LockPoller(
            settings.lab_database_url, self._current_pids, self._poller_stop,
            self._snapshots, settings.lock_poll_interval_ms, self._wait_tracker,
        )
        self._poller.start()
        self._t_start = time.perf_counter()
        for txdef in self.definition.get("transactions", []):
            w = TxWorker(self, txdef)
            self.workers.append(w)
            with self._workers_cond:
                self._active_workers += 1
            w.start()

    def join(self, timeout_s: float | None = None) -> RunResult:
        deadline = time.monotonic() + (timeout_s or settings.run_hard_timeout_seconds)
        with self._workers_cond:
            while self._active_workers > 0:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.cancel()
                    self.recorder.record(None, "timeout", result={"scope": "run"})
                    break
                self._workers_cond.wait(min(0.2, remaining))
        self._t_workers_done = time.perf_counter()
        self._stop_poller()
        return self._collect()

    # ---- control -------------------------------------------------------

    def pause(self) -> None:
        self.pause_event.set()
        self.recorder.record(None, "paused")

    def resume(self) -> None:
        self.recorder.record(None, "resumed")
        self.pause_event.clear()
        with self._pause_cond:
            self._pause_cond.notify_all()

    def cancel(self) -> None:
        self.cancel_event.set()
        for cp in self._checkpoints.values():
            cp.release()
        with self._pause_cond:
            self._pause_cond.notify_all()
        # hard-stop any still-blocked backends
        try:
            conn = _connect_lab(autocommit=True)
            for pid in self._current_pids():
                conn.execute("SELECT pg_cancel_backend(%s)", (pid,))
            conn.close()
        except Exception:
            pass
        self.recorder.record(None, "cancelled")

    # ---- internals used by workers -------------------------------------

    def wait_checkpoint(self, name: str) -> str:
        cp = self._checkpoints.get(name)
        if cp is None:
            raise StepError(None, f"unknown checkpoint {name!r}")
        return cp.wait(self.cancel_event, settings.run_hard_timeout_seconds)

    def _pause_gate(self, tx: str) -> None:
        if not self.pause_event.is_set():
            return
        with self._pause_cond:
            while self.pause_event.is_set():
                if self.cancel_event.is_set():
                    raise Cancelled()
                self._pause_cond.wait(0.1)

    def _check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise Cancelled()

    def _register_pid(self, pid: int) -> None:
        with self._pids_lock:
            self._pids.append(pid)

    def _current_pids(self) -> list[int]:
        with self._pids_lock:
            return list(self._pids)

    def _worker_started(self) -> None:
        pass

    def _worker_done(self) -> None:
        with self._workers_cond:
            self._active_workers -= 1
            self._workers_cond.notify_all()

    def _stop_poller(self) -> None:
        if self._poller:
            self._poller_stop.set()
            self._poller.join(timeout=2)

    # ---- lab db helpers -------------------------------------------------

    def _reset_and_seed(self) -> None:
        conn = _connect_lab(autocommit=True)
        try:
            conn.execute("CREATE SCHEMA IF NOT EXISTS lab")
            # drop every table in lab schema for a clean slate
            rows = conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'lab'"
            ).fetchall()
            for (t,) in rows:
                conn.execute(f'DROP TABLE IF EXISTS lab."{t}" CASCADE')
            seed = self.definition.get("seed_sql", [])
            for stmt_group in seed:
                for stmt in sqlguard.validate_seed_sql(stmt_group):
                    conn.execute(stmt)
        finally:
            conn.close()

    def _run_probe(self, sql: str) -> list[dict]:
        conn = _connect_lab(autocommit=True)
        try:
            cur = conn.execute(sql)
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, [str(v) for v in row])) for row in cur.fetchall()]
        finally:
            conn.close()

    def _evaluate_invariants(self) -> list[dict]:
        results = []
        for inv in self.definition.get("invariants", []):
            rows = self._run_probe(inv["sql"])
            observed = rows[0][list(rows[0].keys())[0]] if rows else None
            ok = str(observed) == str(inv.get("expect"))
            results.append({"name": inv["name"], "sql": inv["sql"], "expect": str(inv.get("expect")),
                            "observed": observed, "ok": ok})
        return results

    def _final_state(self) -> list[dict]:
        probe = self.definition.get("final_state_sql")
        return self._run_probe(probe) if probe else []

    def _serial_baseline(self, order: list[str]) -> list[dict]:
        """Replay the named transactions serially in one connection; capture final probe."""
        conn = _connect_lab(autocommit=True)
        try:
            conn.execute("CREATE SCHEMA IF NOT EXISTS lab")
            rows = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='lab'").fetchall()
            for (t,) in rows:
                conn.execute(f'DROP TABLE IF EXISTS lab."{t}" CASCADE')
            for stmt_group in self.definition.get("seed_sql", []):
                for stmt in sqlguard.validate_seed_sql(stmt_group):
                    conn.execute(stmt)
            by_name = {t["name"]: t for t in self.definition.get("transactions", [])}
            for name in order:
                txdef = by_name[name]
                variables: dict[str, str] = {}
                conn.execute("BEGIN")
                for step in txdef.get("steps", []):
                    if step.get("kind", "sql") == "sql":
                        sql = sqlguard.validate_step_sql(substitute_placeholders(step["sql"], variables))
                        cur = conn.execute(sql)
                        if cur.description:
                            rows = cur.fetchmany(settings.max_step_rows)
                            if step.get("save_as") and rows:
                                variables[step["save_as"]] = to_literal(rows[0][0])
                    elif step.get("kind") == "rollback":
                        conn.rollback()
                        conn.execute("BEGIN")
                conn.commit()
            probe = self.definition.get("final_state_sql")
            if not probe:
                return []
            cur = conn.execute(probe)
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, [str(v) for v in row])) for row in cur.fetchall()]
        finally:
            conn.close()

    # ---- result assembly -------------------------------------------------

    def _collect(self) -> RunResult:
        sessions = [w.result for w in self.workers]
        for s in sessions:
            if s.backend_pid:
                s.lock_wait_ms = round(self._wait_tracker.get(s.backend_pid, 0.0), 1)
        if self.cancel_event.is_set():
            status = "cancelled"
        else:
            status = "succeeded"
        # restore lab to post-run state for invariant/final probes (workers already committed/rolled back)
        invariant_results = self._evaluate_invariants() if status == "succeeded" else []
        final_state = self._final_state() if status == "succeeded" else []
        serial: dict[str, list[dict]] = {}
        if status == "succeeded" and self.definition.get("final_state_sql"):
            txnames = [t["name"] for t in self.definition.get("transactions", [])]
            import itertools
            for order in itertools.permutations(txnames):
                try:
                    serial["->".join(order)] = self._serial_baseline(list(order))
                except Exception as exc:
                    serial["->".join(order)] = [{"error": str(exc)}]
            # leave the lab in the concurrent run's final state: re-run seed + concurrent? No —
            # serial baselines reseeded the lab. Re-apply the concurrent final state is impossible,
            # so reseed + note that serial replay was last. Instead: capture concurrent final FIRST
            # (done above), then restore concurrent state is not needed for correctness of evidence.
        # NOTE: serial baselines mutate the lab db; run them last and reseed for next run in start().
        result = RunResult(
            status=status, sessions=sessions, lock_snapshots=self._snapshots,
            invariant_results=invariant_results, final_state=final_state,
            serial_baselines=serial, wall_time_ms=round((self._t_workers_done - self._t_start) * 1000.0, 3),
        )
        return result
