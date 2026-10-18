"""Evidence-backed anomaly detectors.

Scope (documented and tested):
- deadlock_observed: a session aborted with SQLSTATE 40P01 (confirmed).
- serialization_failure_observed: SQLSTATE 40001 (confirmed).
- invariant_violation: a declared business invariant fails after all surviving
  transactions committed (confirmed observation; anomaly class from pattern).
- non_repeatable_read: same SELECT text executed twice in one transaction
  under READ COMMITTED returned different row payloads with no intervening
  write by that transaction (confirmed observation).
- non_serializable_outcome: concurrent final state matches NO serial
  permutation replay of the same steps (strong evidence of an anomaly; the
  specific class is inferred from declared table-level rw/ww patterns).

Detectors never claim universal detection: anything outside this scope is
reported as inconclusive or not reported at all.
"""
from __future__ import annotations

from typing import Any

from . import sqlguard


def _step_reads_writes(sql: str) -> tuple[set[str], set[str]]:
    tables = sqlguard.referenced_tables(sql)
    if sqlguard.is_write(sql):
        # UPDATE/DELETE also read their target; INSERT writes.
        verb = sql.strip().split(None, 1)[0].lower()
        if verb == "insert":
            return tables - {next(iter(tables), "")}, tables
        return tables, tables
    return tables, set()


def declared_dependency_edges(definition: dict) -> list[dict]:
    """Table-level rw/wr/ww edges derived from step SQL (labelled 'declared')."""
    txs = definition.get("transactions", [])
    ops: dict[str, list[tuple[int, str, str]]] = {}  # tx -> [(idx, table, mode)]
    for tx in txs:
        ops[tx["name"]] = []
        for idx, step in enumerate(tx.get("steps", [])):
            if step.get("kind", "sql") != "sql":
                continue
            reads, writes = _step_reads_writes(step["sql"])
            for t in reads:
                ops[tx["name"]].append((idx, t, "r"))
            for t in writes:
                ops[tx["name"]].append((idx, t, "w"))
    edges: list[dict] = []
    names = list(ops)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for ia, ta, ma in ops[a]:
                for ib, tb, mb in ops[b]:
                    if ta != tb:
                        continue
                    if ma == "r" and mb == "w":
                        edges.append({"from_tx": a, "to_tx": b, "kind": "declared_rw",
                                      "evidence": {"table": ta, "steps": [ia, ib]}})
                    elif ma == "w" and mb == "r":
                        edges.append({"from_tx": b, "to_tx": a, "kind": "declared_wr",
                                      "evidence": {"table": ta, "steps": [ib, ia]}})
                    elif ma == "w" and mb == "w":
                        edges.append({"from_tx": a, "to_tx": b, "kind": "declared_ww",
                                      "evidence": {"table": ta, "steps": [ia, ib]}})
                        edges.append({"from_tx": b, "to_tx": a, "kind": "declared_ww",
                                      "evidence": {"table": ta, "steps": [ib, ia]}})
    # dedupe
    seen = set()
    out = []
    for e in edges:
        key = (e["from_tx"], e["to_tx"], e["kind"], e["evidence"]["table"])
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


def observed_wait_edges(snapshots: list[dict], pid_to_tx: dict[int, str]) -> list[dict]:
    """Wait-for edges from lock snapshots: waiting_tx -> blocking_tx."""
    edges: dict[tuple[str, str], dict] = {}
    for snap in snapshots:
        for lock in snap.get("locks", []):
            if lock.get("granted"):
                continue
            waiter = pid_to_tx.get(lock.get("pid"))
            for blocker_pid in lock.get("blocked_by") or []:
                blocker = pid_to_tx.get(blocker_pid)
                if waiter and blocker and waiter != blocker:
                    key = (waiter, blocker)
                    e = edges.setdefault(key, {
                        "from_tx": waiter, "to_tx": blocker, "kind": "observed_wait",
                        "evidence": {"locktype": lock.get("locktype"), "mode": lock.get("mode"),
                                     "relation": lock.get("relation"), "samples": 0},
                    })
                    e["evidence"]["samples"] += 1
    return list(edges.values())


def _norm_sql(sql: str) -> str:
    return " ".join(sql.lower().split())


def detect_non_repeatable_reads(events: list[dict], definition: dict) -> list[dict]:
    findings = []
    iso_by_tx = {t["name"]: t.get("isolation", "READ COMMITTED") for t in definition.get("transactions", [])}
    by_tx: dict[str, list[dict]] = {}
    for ev in events:
        if ev["kind"] in ("step_ok", "step_error") and ev.get("tx_name"):
            by_tx.setdefault(ev["tx_name"], []).append(ev)
    for tx, evs in by_tx.items():
        selects: dict[str, list[dict]] = {}
        wrote = False
        for ev in evs:
            sql = ev.get("sql_text", "")
            if sqlguard.is_write(sql):
                wrote = True
            if sql.lower().lstrip().startswith("select") and ev["kind"] == "step_ok":
                key = _norm_sql(sql)
                prior = selects.get(key)
                if prior:
                    prev_rows = prior[-1]["result"].get("rows")
                    cur_rows = ev["result"].get("rows")
                    if prev_rows != cur_rows and not wrote:
                        status = "confirmed" if iso_by_tx.get(tx, "").upper() == "READ COMMITTED" else "potential"
                        findings.append({
                            "detector": "non_repeatable_read",
                            "status": status,
                            "severity": "high",
                            "summary": f"{tx} re-read the same row set and observed a change "
                                       f"(isolation: {iso_by_tx.get(tx)})",
                            "evidence_event_seqs": [prior[-1]["seq"], ev["seq"]],
                            "detail": {"sql": sql, "first": prev_rows, "second": cur_rows},
                        })
                    selects.setdefault(key, []).append(ev)
                else:
                    selects[key] = [ev]
    return findings


def analyze(definition: dict, events: list[dict], sessions: list[dict],
            invariant_results: list[dict], final_state: list[dict],
            serial_baselines: dict[str, list[dict]]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []

    for s in sessions:
        if s.get("error_sqlstate") == "40P01":
            findings.append({
                "detector": "deadlock_observed", "status": "confirmed", "severity": "critical",
                "summary": f"{s['tx_name']} was chosen as deadlock victim (SQLSTATE 40P01)",
                "evidence_event_seqs": [], "detail": {"message": s.get("error_message", "")},
            })
        if s.get("error_sqlstate") == "40001":
            findings.append({
                "detector": "serialization_failure_observed", "status": "confirmed", "severity": "high",
                "summary": f"{s['tx_name']} aborted with serialization failure (SQLSTATE 40001) "
                           f"under {s.get('isolation_level')}",
                "evidence_event_seqs": [], "detail": {"message": s.get("error_message", "")},
            })

    violations = [r for r in invariant_results if not r["ok"]]
    for v in violations:
        findings.append({
            "detector": "invariant_violation", "status": "confirmed", "severity": "critical",
            "summary": f"Business invariant {v['name']!r} violated: expected {v['expect']}, observed {v['observed']}",
            "evidence_event_seqs": [], "detail": v,
        })

    findings.extend(detect_non_repeatable_reads(events, definition))

    # Non-serializable outcome check against counterfactual serial replays.
    if serial_baselines and final_state:
        failed_replays = {order: rows for order, rows in serial_baselines.items()
                          if rows and isinstance(rows[0], dict) and "__replay_error__" in rows[0]}
        matches = [order for order, rows in serial_baselines.items()
                   if order not in failed_replays and rows == final_state]
        if not matches:
            pattern_hint = ""
            edges = declared_dependency_edges(definition)
            kinds = {e["kind"] for e in edges}
            if "declared_rw" in kinds and "declared_ww" not in kinds:
                pattern_hint = "declared rw-antidependency pattern is consistent with write skew"
            elif "declared_ww" in kinds:
                pattern_hint = "declared ww/rw pattern is consistent with a lost update"
            if failed_replays:
                findings.append({
                    "detector": "non_serializable_outcome", "status": "inconclusive", "severity": "info",
                    "summary": f"Could not compare against every serial order: {len(failed_replays)} replay(s) failed.",
                    "evidence_event_seqs": [],
                    "detail": {"final_state": final_state, "serial_baselines": serial_baselines},
                })
            else:
                findings.append({
                    "detector": "non_serializable_outcome", "status": "confirmed", "severity": "high",
                    "summary": "Concurrent final state matches no serial execution order of the same "
                               f"transactions. {pattern_hint}".strip(),
                    "evidence_event_seqs": [],
                    "detail": {"final_state": final_state, "serial_baselines": serial_baselines},
                })
        else:
            findings.append({
                "detector": "non_serializable_outcome", "status": "inconclusive", "severity": "info",
                "summary": f"Final state matches serial order(s): {', '.join(matches)} — "
                           "no non-serializable outcome detected in this run",
                "evidence_event_seqs": [], "detail": {},
            })

    confirmed = [f for f in findings if f["status"] == "confirmed" and f["severity"] in ("high", "critical")]
    return {
        "findings": findings,
        "anomaly_detected": bool(confirmed),
        "scope_note": "Detectors cover deadlock (40P01), serialization failure (40001), "
                      "declared-invariant violations, same-transaction non-repeatable reads under "
                      "READ COMMITTED, and non-serializable final states vs. counterfactual serial "
                      "replays. Other anomaly classes are out of scope.",
    }
