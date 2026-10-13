"""Export routes: JSON experiment bundles, CSV metrics, self-contained HTML reports."""
from __future__ import annotations

import csv
import html
import io
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import (DependencyEdge, ExecutionEvent, ExperimentRun, LockObservation,
                      RunMetric, Scenario, ScenarioVersion, TxSession, User)

router = APIRouter(prefix="/api/export", tags=["export"])


def _bundle(db: Session, user: User, run_id: int) -> dict:
    run = db.get(ExperimentRun, run_id)
    if not run or run.initiated_by != user.id:
        raise HTTPException(status_code=404, detail="run not found")
    scenario = db.get(Scenario, run.scenario_id)
    version = db.get(ScenarioVersion, run.scenario_version_id)
    events = db.scalars(select(ExecutionEvent).where(ExecutionEvent.run_id == run.id)
                        .order_by(ExecutionEvent.seq)).all()
    sessions = db.scalars(select(TxSession).where(TxSession.run_id == run.id)).all()
    edges = db.scalars(select(DependencyEdge).where(DependencyEdge.run_id == run.id)).all()
    snaps = db.scalars(select(LockObservation).where(LockObservation.run_id == run.id)
                       .order_by(LockObservation.observed_at)).all()
    metrics = db.get(RunMetric, run.id)
    return {
        "format": "locklens-experiment-bundle/1",
        "run": {"id": run.id, "status": run.status, "started_at": str(run.started_at),
                "finished_at": str(run.finished_at), "error": run.error,
                "analysis": run.analysis},
        "scenario": {"key": scenario.key, "name": scenario.name, "category": scenario.category,
                     "version": version.version, "definition": version.definition},
        "sessions": [{"tx_name": s.tx_name, "isolation_level": s.isolation_level,
                      "backend_pid": s.backend_pid, "outcome": s.outcome,
                      "error_sqlstate": s.error_sqlstate, "error_message": s.error_message} for s in sessions],
        "events": [{"seq": e.seq, "tx_name": e.tx_name, "kind": e.kind, "step_index": e.step_index,
                    "sql_text": e.sql_text, "result": e.result,
                    "duration_ms": float(e.duration_ms) if e.duration_ms is not None else None,
                    "at": str(e.at)} for e in events],
        "dependency_edges": [{"from_tx": e.from_tx, "to_tx": e.to_tx, "kind": e.kind,
                              "evidence": e.evidence} for e in edges],
        "lock_snapshots": [s.snapshot for s in snaps],
        "metrics": ({"wall_time_ms": float(metrics.wall_time_ms),
                     "total_lock_wait_ms": float(metrics.total_lock_wait_ms),
                     "max_lock_wait_ms": float(metrics.max_lock_wait_ms),
                     "steps_executed": metrics.steps_executed, "commits": metrics.commits,
                     "rollbacks": metrics.rollbacks, "deadlocks": metrics.deadlocks,
                     "serialization_failures": metrics.serialization_failures,
                     "invariant_violations": metrics.invariant_violations} if metrics else None),
    }


@router.get("/runs/{run_id}.json")
def export_json(run_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    bundle = _bundle(db, user, run_id)
    return Response(content=json.dumps(bundle, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="locklens-run-{run_id}.json"'})


@router.get("/runs/{run_id}.csv")
def export_csv(run_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    bundle = _bundle(db, user, run_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["seq", "tx_name", "kind", "step_index", "sql_text", "duration_ms", "at", "result_json"])
    for e in bundle["events"]:
        w.writerow([e["seq"], e["tx_name"], e["kind"], e["step_index"], e["sql_text"],
                    e["duration_ms"], e["at"], json.dumps(e["result"])])
    w.writerow([])
    w.writerow(["metric", "value"])
    for k, v in (bundle["metrics"] or {}).items():
        w.writerow([k, v])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="locklens-run-{run_id}.csv"'})


@router.get("/runs/{run_id}.html")
def export_html_report(run_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    b = _bundle(db, user, run_id)
    esc = html.escape
    findings = b["run"]["analysis"].get("findings", [])
    finding_rows = "".join(
        f"<tr><td>{esc(f['detector'])}</td><td><span class='badge {esc(f['status'])}'>{esc(f['status'])}</span></td>"
        f"<td>{esc(f['severity'])}</td><td>{esc(f['summary'])}</td></tr>" for f in findings)
    event_rows = "".join(
        f"<tr><td>{e['seq']}</td><td>{esc(str(e['tx_name'] or '—'))}</td><td>{esc(e['kind'])}</td>"
        f"<td><code>{esc(e['sql_text'][:120])}</code></td><td>{esc(str(e['duration_ms'] or ''))}</td></tr>"
        for e in b["events"])
    session_rows = "".join(
        f"<tr><td>{esc(s['tx_name'])}</td><td>{esc(s['isolation_level'])}</td>"
        f"<td>{esc(s['outcome'])}</td><td>{esc(str(s['error_sqlstate'] or ''))}</td></tr>"
        for s in b["sessions"])
    metrics = b["metrics"] or {}
    metric_rows = "".join(f"<tr><td>{esc(k)}</td><td>{v}</td></tr>" for k, v in metrics.items())
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>LockLens Run #{run_id}</title>
<style>body{{font-family:ui-sans-serif,system-ui;margin:40px;color:#0f172a;max-width:1000px}}
h1{{font-size:22px}} h2{{font-size:16px;margin-top:28px;color:#334155}}
table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{border:1px solid #e2e8f0;padding:6px 8px;text-align:left;vertical-align:top}}
code{{background:#f1f5f9;padding:1px 4px;border-radius:4px;font-size:12px}}
.badge{{padding:1px 8px;border-radius:99px;font-size:11px}}
.confirmed{{background:#fee2e2;color:#991b1b}}.potential{{background:#fef3c7;color:#92400e}}.inconclusive{{background:#e2e8f0;color:#475569}}
.meta{{color:#64748b;font-size:13px}}</style></head><body>
<h1>LockLens Experiment Report — Run #{run_id}</h1>
<p class="meta">Scenario: {esc(b['scenario']['name'])} (v{b['scenario']['version']}) · Status: <b>{esc(b['run']['status'])}</b> ·
Started: {esc(str(b['run']['started_at']))}</p>
<h2>Findings</h2><table><tr><th>Detector</th><th>Status</th><th>Severity</th><th>Summary</th></tr>{finding_rows or '<tr><td colspan=4>No findings</td></tr>'}</table>
<h2>Transaction Sessions</h2><table><tr><th>Tx</th><th>Isolation</th><th>Outcome</th><th>SQLSTATE</th></tr>{session_rows}</table>
<h2>Metrics</h2><table>{metric_rows}</table>
<h2>Execution Trace</h2><table><tr><th>#</th><th>Tx</th><th>Kind</th><th>SQL</th><th>ms</th></tr>{event_rows}</table>
<p class="meta">Generated by LockLens. Evidence: ordered execution events, lock snapshots and counterfactual serial replays as stored in the JSON bundle.</p>
</body></html>"""
    return Response(content=page, media_type="text/html",
                    headers={"Content-Disposition": f'attachment; filename="locklens-report-{run_id}.html"'})
