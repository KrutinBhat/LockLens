from app.lab import analyzers
from app.lab.library import LIBRARY


def _defn(key):
    return next(e["definition"] for e in LIBRARY if e["key"] == key)


def test_deadlock_detector_confirmed():
    sessions = [{"tx_name": "T2", "isolation_level": "READ COMMITTED",
                 "error_sqlstate": "40P01", "error_message": "deadlock detected"}]
    out = analyzers.analyze(_defn("deadlock"), [], sessions, [], [], {})
    assert any(f["detector"] == "deadlock_observed" and f["status"] == "confirmed"
               for f in out["findings"])
    assert out["anomaly_detected"]


def test_serialization_failure_detector():
    sessions = [{"tx_name": "T1", "isolation_level": "SERIALIZABLE",
                 "error_sqlstate": "40001", "error_message": "could not serialize"}]
    out = analyzers.analyze(_defn("serialization_failure"), [], sessions, [], [], {})
    assert any(f["detector"] == "serialization_failure_observed" for f in out["findings"])


def test_invariant_violation_detector():
    inv = [{"name": "n", "sql": "s", "expect": "60", "observed": "80", "ok": False}]
    out = analyzers.analyze(_defn("lost_update"), [], [], inv, [], {})
    assert any(f["detector"] == "invariant_violation" for f in out["findings"])


def test_non_repeatable_read_detector():
    defn = _defn("non_repeatable_read")
    events = [
        {"seq": 1, "tx_name": "T1", "kind": "step_ok", "sql_text": "SELECT price FROM lab.products WHERE id = 1",
         "result": {"rows": [["50"]]}},
        {"seq": 5, "tx_name": "T1", "kind": "step_ok", "sql_text": "SELECT price FROM lab.products WHERE id = 1",
         "result": {"rows": [["75"]]}},
    ]
    findings = analyzers.detect_non_repeatable_reads(events, defn)
    assert len(findings) == 1
    assert findings[0]["status"] == "confirmed"
    assert findings[0]["evidence_event_seqs"] == [1, 5]


def test_non_repeatable_read_negative_same_rows():
    defn = _defn("non_repeatable_read")
    events = [
        {"seq": 1, "tx_name": "T1", "kind": "step_ok", "sql_text": "SELECT price FROM lab.products WHERE id = 1",
         "result": {"rows": [["50"]]}},
        {"seq": 2, "tx_name": "T1", "kind": "step_ok", "sql_text": "SELECT price FROM lab.products WHERE id = 1",
         "result": {"rows": [["50"]]}},
    ]
    assert analyzers.detect_non_repeatable_reads(events, defn) == []


def test_non_serializable_outcome_vs_serial_replays():
    defn = _defn("lost_update")
    final = [{"id": "1", "balance": "80"}, {"id": "2", "balance": "100"}]
    serial = {
        "T1->T2": [{"id": "1", "balance": "60"}, {"id": "2", "balance": "100"}],
        "T2->T1": [{"id": "1", "balance": "60"}, {"id": "2", "balance": "100"}],
    }
    out = analyzers.analyze(defn, [], [], [], final, serial)
    ns = [f for f in out["findings"] if f["detector"] == "non_serializable_outcome"]
    assert ns and ns[0]["status"] == "confirmed"


def test_serializable_match_is_inconclusive():
    defn = _defn("lost_update")
    final = [{"id": "1", "balance": "60"}]
    serial = {"T1->T2": [{"id": "1", "balance": "60"}], "T2->T1": [{"id": "1", "balance": "60"}]}
    out = analyzers.analyze(defn, [], [], [], final, serial)
    ns = [f for f in out["findings"] if f["detector"] == "non_serializable_outcome"]
    assert ns and ns[0]["status"] == "inconclusive"
    assert not out["anomaly_detected"]


def test_declared_edges_write_skew():
    edges = analyzers.declared_dependency_edges(_defn("write_skew"))
    assert any(e["kind"] == "declared_rw" for e in edges)


def test_observed_wait_edges():
    snaps = [{"locks": [
        {"pid": 10, "granted": False, "blocked_by": [11], "locktype": "tuple", "mode": "AccessExclusiveLock",
         "relation": "accounts"},
        {"pid": 11, "granted": False, "blocked_by": [10], "locktype": "tuple", "mode": "AccessExclusiveLock",
         "relation": "accounts"},
    ]}]
    edges = analyzers.observed_wait_edges(snaps, {10: "T1", 11: "T2"})
    pairs = {(e["from_tx"], e["to_tx"]) for e in edges}
    assert pairs == {("T1", "T2"), ("T2", "T1")}
