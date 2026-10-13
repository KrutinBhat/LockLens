"""Integration tests: real concurrent PostgreSQL transactions via ScheduleEngine.

These tests require a reachable PostgreSQL (LAB_DATABASE_URL). They verify the
actual database outcomes the product claims to reproduce.
"""
from __future__ import annotations

import threading
import time

import pytest

from app.lab.engine import ScheduleEngine
from app.lab.library import LIBRARY


def _defn(key):
    import copy
    return copy.deepcopy(next(e["definition"] for e in LIBRARY if e["key"] == key))


def _run(key, timeout=90):
    eng = ScheduleEngine(_defn(key))
    eng.start()
    return eng, eng.join(timeout_s=timeout)


def test_lost_update_produces_wrong_balance():
    eng, res = _run("lost_update")
    assert res.status == "succeeded"
    assert all(s.outcome == "committed" for s in res.sessions)
    # Both read 100, both wrote 80 -> invariant (expects 60) violated.
    assert res.invariant_results and res.invariant_results[0]["observed"] == "80"
    assert res.invariant_results[0]["ok"] is False
    # Final state matches NO serial order (serial orders both yield 60).
    for order, rows in res.serial_baselines.items():
        assert rows != res.final_state, order
        assert rows[0]["balance"] == "60", order


def test_non_repeatable_read_observed():
    eng, res = _run("non_repeatable_read")
    assert res.status == "succeeded"
    t1_reads = [e for e in eng.recorder.events
                if e.tx_name == "T1" and e.kind == "step_ok" and e.sql_text.lower().startswith("select")]
    assert len(t1_reads) == 2
    assert t1_reads[0].result["rows"] != t1_reads[1].result["rows"]
    assert t1_reads[0].result["rows"][0][0] == "50"
    assert t1_reads[1].result["rows"][0][0] == "75"


def test_write_skew_violates_invariant_under_repeatable_read():
    eng, res = _run("write_skew")
    assert res.status == "succeeded"
    assert all(s.outcome == "committed" for s in res.sessions)
    assert res.invariant_results[0]["observed"] == "2"  # both went off call
    assert res.invariant_results[0]["ok"] is False


def test_serializable_aborts_write_skew():
    eng, res = _run("serialization_failure")
    outcomes = {s.tx_name: s for s in res.sessions}
    aborted = [s for s in res.sessions if s.outcome == "aborted_serialization"]
    assert len(aborted) == 1, f"expected exactly one 40001, got {[s.outcome for s in res.sessions]}"
    assert aborted[0].error_sqlstate == "40001"
    committed = [s for s in res.sessions if s.outcome == "committed"]
    assert len(committed) == 1
    # Invariant preserved: exactly one doctor went off call.
    assert res.invariant_results[0]["observed"] == "1"


def test_deadlock_detected_and_victim_aborted():
    eng, res = _run("deadlock")
    victims = [s for s in res.sessions if s.outcome == "aborted_deadlock"]
    assert len(victims) == 1, f"outcomes: {[s.outcome for s in res.sessions]}"
    assert victims[0].error_sqlstate == "40P01"
    assert any(s.outcome == "committed" for s in res.sessions)
    # Wait-for evidence captured from pg_locks during the run.
    waited = any(
        any(not l["granted"] for l in snap["locks"]) for snap in res.lock_snapshots
    )
    assert waited, "expected at least one ungranted lock observation"


def test_cancellation_mid_run():
    defn = _defn("deadlock")
    # T1 holds the row lock across a 5s sleep so T2 is deterministically blocked.
    defn["transactions"][0]["steps"] = [
        {"kind": "sql", "sql": "UPDATE lab.accounts SET balance = balance - 10 WHERE id = 1"},
        {"kind": "checkpoint", "name": "t1_holds_lock"},
        {"kind": "sql", "sql": "SELECT pg_sleep(5)"},
        {"kind": "commit"},
    ]
    defn["transactions"][1]["steps"] = [
        {"kind": "checkpoint", "name": "t1_holds_lock"},
        {"kind": "sql", "sql": "UPDATE lab.accounts SET balance = balance - 10 WHERE id = 1"},
        {"kind": "commit"},
    ]
    eng = ScheduleEngine(defn)
    eng.start()
    # wait until T2 is genuinely blocked on T1's row lock, then cancel
    deadline = time.monotonic() + 30
    blocked = False
    while time.monotonic() < deadline and not blocked:
        blocked = any(
            any(not l["granted"] for l in snap["locks"]) for snap in eng._snapshots
        )
        time.sleep(0.05)
    assert blocked, "expected an observed lock wait before cancelling"
    eng.cancel()
    res = eng.join(timeout_s=30)
    assert res.status == "cancelled"
    assert any(s.outcome == "cancelled" for s in res.sessions)


def test_lock_timeout_bounds_blocked_step():
    defn = _defn("deadlock")
    # Replace the second UPDATE in T2 with a third conflicting update and remove
    # the deadlock by giving T1 only one lock; T2 blocks until lock_timeout fires.
    defn["transactions"][0]["steps"] = [
        {"kind": "sql", "sql": "UPDATE lab.accounts SET balance = balance - 10 WHERE id = 1"},
        {"kind": "checkpoint", "name": "first_locks"},
        {"kind": "sql", "sql": "SELECT pg_sleep(30)"},  # hold lock past T2's lock_timeout
        {"kind": "commit"},
    ]
    defn["transactions"][1]["steps"] = [
        {"kind": "checkpoint", "name": "first_locks"},
        {"kind": "sql", "sql": "UPDATE lab.accounts SET balance = balance - 10 WHERE id = 1"},
        {"kind": "commit"},
    ]
    eng = ScheduleEngine(defn)
    eng.start()
    res = eng.join(timeout_s=60)
    t2 = next(s for s in res.sessions if s.tx_name == "T2")
    assert t2.outcome == "aborted_lock_timeout" and t2.error_sqlstate == "55P03"
    eng.cancel()  # release T1's pg_sleep
