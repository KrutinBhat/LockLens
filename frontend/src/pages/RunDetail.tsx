import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Download, Pause, Play, Square } from "lucide-react";
import { api, downloadFile } from "../lib/api";
import type { RunDetail as RunDetailT } from "../lib/types";
import { Btn, Card, CardHeader, ErrorState, FindingIcon, Spinner, StatusBadge } from "../components/ui";
import TxTimeline from "../components/TxTimeline";
import { GraphPair } from "../components/Graphs";
import { SqlHighlight } from "../components/SqlEditor";

export default function RunDetail() {
  const { id } = useParams();
  const [run, setRun] = useState<RunDetailT | null>(null);
  const [error, setError] = useState("");
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);

  useEffect(() => {
    let timer: any;
    let stop = false;
    async function poll() {
      try {
        const r = await api<RunDetailT>(`/api/runs/${id}`);
        if (stop) return;
        setRun(r); setError("");
        if (["queued", "running", "paused"].includes(r.status)) timer = setTimeout(poll, 700);
      } catch (e: any) { if (!stop) { setError(e.message); timer = setTimeout(poll, 2500); } }
    }
    poll();
    return () => { stop = true; clearTimeout(timer); };
  }, [id]);

  async function control(action: string) {
    try { await api(`/api/runs/${id}/control`, { method: "POST", body: JSON.stringify({ action }) }); } catch (e: any) { setError(e.message); }
  }

  const selectedEvent = useMemo(() => run?.events.find(e => e.seq === selectedSeq) ?? null, [run, selectedSeq]);
  const lockTimeline = useMemo(() => (run?.lock_snapshots ?? []).map((s, i) => ({
    i, waiting: s.locks.filter(l => !l.granted).length,
  })), [run]);

  if (error && !run) return <ErrorState message={error} />;
  if (!run) return <Spinner label="Loading run…" />;

  const live = ["queued", "running", "paused"].includes(run.status);
  const findings = run.analysis?.findings ?? [];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-slate-100">Run #{run.id}</h1>
          <StatusBadge status={run.status} />
        </div>
        <div className="flex flex-wrap gap-2">
          {live && (
            <>
              {run.status === "paused"
                ? <Btn variant="ghost" onClick={() => control("resume")}><Play className="h-3.5 w-3.5" /> Resume</Btn>
                : <Btn variant="ghost" onClick={() => control("pause")}><Pause className="h-3.5 w-3.5" /> Pause</Btn>}
              <Btn variant="danger" onClick={() => control("cancel")}><Square className="h-3.5 w-3.5" /> Cancel</Btn>
            </>
          )}
          {!live && (
            <>
              <Btn variant="ghost" onClick={() => downloadFile(`/api/export/runs/${run.id}.json`, `locklens-run-${run.id}.json`)}><Download className="h-3.5 w-3.5" /> JSON</Btn>
              <Btn variant="ghost" onClick={() => downloadFile(`/api/export/runs/${run.id}.csv`, `locklens-run-${run.id}.csv`)}><Download className="h-3.5 w-3.5" /> CSV</Btn>
              <Btn variant="ghost" onClick={() => downloadFile(`/api/export/runs/${run.id}.html`, `locklens-report-${run.id}.html`)}><Download className="h-3.5 w-3.5" /> Report</Btn>
            </>
          )}
        </div>
      </div>

      {live && (
        <div className="flex items-center gap-2 rounded-lg border border-accent/30 bg-accent/5 px-4 py-2 text-xs text-accent">
          <span className="live-dot h-2 w-2 rounded-full bg-accent" /> Live — polling every 0.7s. Events stream in as transactions execute.
        </div>
      )}

      {/* sessions + metrics */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Transaction sessions" sub="Real PostgreSQL backends, one per transaction" />
          <div className="divide-y divide-ink-700/50">
            {run.sessions.length === 0 && <p className="px-5 py-6 text-xs text-slate-500">Sessions appear once workers start.</p>}
            {run.sessions.map(s => (
              <div key={s.tx_name} className="flex items-center justify-between gap-3 px-5 py-3">
                <div>
                  <span className="font-mono text-sm font-semibold text-accent">{s.tx_name}</span>
                  <span className="ml-2 text-xs text-slate-500">{s.isolation_level}{s.backend_pid ? ` · pid ${s.backend_pid}` : ""}</span>
                  {s.error_message && <p className="mt-0.5 max-w-md truncate text-xs text-bad" title={s.error_message}>{s.error_sqlstate} · {s.error_message}</p>}
                </div>
                <StatusBadge status={s.outcome} />
              </div>
            ))}
          </div>
        </Card>
        <Card>
          <CardHeader title="Metrics" sub="Measured during execution" />
          {run.metrics ? (
            <div className="grid grid-cols-2 gap-px overflow-hidden bg-ink-700/40 sm:grid-cols-3">
              {[
                ["wall time", `${run.metrics.wall_time_ms.toFixed(1)} ms`],
                ["lock wait (total)", `${run.metrics.total_lock_wait_ms.toFixed(0)} ms`],
                ["lock wait (max)", `${run.metrics.max_lock_wait_ms.toFixed(0)} ms`],
                ["steps", run.metrics.steps_executed],
                ["commits", run.metrics.commits],
                ["rollbacks", run.metrics.rollbacks],
                ["deadlocks", run.metrics.deadlocks],
                ["serialization failures", run.metrics.serialization_failures],
                ["invariant violations", run.metrics.invariant_violations],
              ].map(([k, v]) => (
                <div key={k as string} className="bg-ink-900 px-4 py-3">
                  <div className="text-[10px] uppercase tracking-wide text-slate-500">{k}</div>
                  <div className="mt-0.5 text-lg font-semibold text-slate-100">{v}</div>
                </div>
              ))}
            </div>
          ) : <p className="px-5 py-6 text-xs text-slate-500">Metrics are recorded when the run finishes.</p>}
        </Card>
      </div>

      {/* timeline */}
      <Card>
        <CardHeader title="Execution timeline" sub="Click an event to inspect its evidence" />
        <div className="p-5">
          {run.events.length ? <TxTimeline events={run.events} selected={selectedSeq} onSelect={setSelectedSeq} />
            : <p className="text-xs text-slate-500">Waiting for first events…</p>}
          {selectedEvent && (
            <div className="mt-4 rounded-lg border border-ink-600/60 bg-ink-850 p-4">
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <span className="font-mono text-accent">#{selectedEvent.seq}</span>
                <span>{selectedEvent.tx_name ?? "engine"}</span>
                <StatusBadge status={selectedEvent.kind} />
                {selectedEvent.duration_ms != null && <span>{selectedEvent.duration_ms.toFixed(1)} ms</span>}
              </div>
              {selectedEvent.sql_text && <SqlHighlight sql={selectedEvent.sql_text} className="mt-2" />}
              {Object.keys(selectedEvent.result ?? {}).length > 0 && (
                <pre className="sql-editor mt-2 max-h-48 overflow-auto rounded-lg bg-ink-950 p-3 text-xs text-slate-400">
                  {JSON.stringify(selectedEvent.result, null, 2)}
                </pre>
              )}
            </div>
          )}
        </div>
      </Card>

      {/* findings */}
      <Card>
        <CardHeader title="Evidence-backed findings" sub={run.analysis?.scope_note ?? undefined} />
        {findings.length === 0 ? (
          <p className="px-5 py-6 text-xs text-slate-500">{live ? "Analysis runs when execution completes." : "No findings."}</p>
        ) : (
          <ul className="divide-y divide-ink-700/50">
            {findings.map((f, i) => (
              <li key={i} className="flex gap-3 px-5 py-3">
                <FindingIcon status={f.status} />
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-slate-200">{f.detector.replace(/_/g, " ")}</span>
                    <StatusBadge status={f.status} />
                    <span className="text-[10px] uppercase tracking-wide text-slate-500">{f.severity}</span>
                  </div>
                  <p className="mt-0.5 text-xs text-slate-400">{f.summary}</p>
                  {f.evidence_event_seqs.length > 0 && (
                    <p className="mt-1 text-[11px] text-slate-500">Evidence events:{" "}
                      {f.evidence_event_seqs.map(seq => (
                        <button key={seq} onClick={() => setSelectedSeq(seq)} className="mr-1 rounded bg-ink-700 px-1.5 py-0.5 font-mono text-accent hover:bg-ink-600">#{seq}</button>
                      ))}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* graphs */}
      {!live && (
        <Card>
          <CardHeader title="Blocking & dependency graphs" sub="Wait-for edges observed from pg_locks; rw/wr/ww edges declared from step SQL (table-level)" />
          <div className="p-4"><GraphPair edges={run.dependency_edges} /></div>
        </Card>
      )}

      {/* lock observations */}
      {!live && lockTimeline.length > 0 && (
        <Card>
          <CardHeader title="Lock observations" sub={`${lockTimeline.length} snapshots from pg_locks during execution`} />
          <div className="p-5">
            <div className="flex h-20 items-end gap-px">
              {lockTimeline.map(s => (
                <div key={s.i} className={`flex-1 rounded-t ${s.waiting > 0 ? "bg-bad/80" : "bg-ink-600"}`}
                  style={{ height: `${Math.max(6, Math.min(100, s.waiting * 40))}%` }}
                  title={`snapshot ${s.i}: ${s.waiting} waiting`} />
              ))}
            </div>
            <p className="mt-2 text-[11px] text-slate-500">Red bars mark snapshots with ungranted (waiting) locks.</p>
          </div>
        </Card>
      )}

      <div className="text-xs text-slate-500">
        <Link to="/history" className="text-accent hover:underline">← Back to history</Link>
      </div>
    </div>
  );
}
