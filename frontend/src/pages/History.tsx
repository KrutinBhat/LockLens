import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Search } from "lucide-react";
import { api } from "../lib/api";
import type { Page, Run } from "../lib/types";
import { Card, EmptyState, ErrorState, Spinner, StatusBadge } from "../components/ui";

export default function History() {
  const [data, setData] = useState<Page<Run> | null>(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");

  function load() {
    setError("");
    api<Page<Run>>(`/api/runs?q=${encodeURIComponent(q)}&status_filter=${status}&page=${page}&page_size=15`)
      .then(setData).catch(e => setError(e.message));
  }
  useEffect(load, [q, status, page]);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Run History</h1>
        <p className="text-sm text-slate-500">Every run is durable and reproducible from its stored configuration snapshot.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
          <input value={q} onChange={e => { setQ(e.target.value); setPage(1); }} placeholder="Search by scenario…"
            className="min-h-[40px] w-64 rounded-lg border border-ink-600 bg-ink-850 pl-9 pr-3 text-sm focus:border-accent/60 focus:outline-none" />
        </div>
        <select value={status} onChange={e => { setStatus(e.target.value); setPage(1); }}
          className="min-h-[40px] rounded-lg border border-ink-600 bg-ink-850 px-2 text-sm focus:border-accent/60 focus:outline-none">
          <option value="">All statuses</option>
          {["succeeded", "anomaly_detected", "failed", "cancelled", "timed_out"].map(s => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
        </select>
      </div>
      <Card>
        {error ? <ErrorState message={error} onRetry={load} /> : !data ? <Spinner /> : data.items.length === 0 ? (
          <EmptyState title="No runs found" hint="Launch a scenario to build history." />
        ) : (
          <>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-ink-600/60 text-left text-[11px] uppercase tracking-wide text-slate-500">
                  <th className="px-5 py-3">Run</th><th className="px-5 py-3">Status</th>
                  <th className="hidden px-5 py-3 md:table-cell">Commits</th>
                  <th className="hidden px-5 py-3 md:table-cell">Wall time</th>
                  <th className="px-5 py-3">Started</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-700/50">
                {data.items.map(r => (
                  <tr key={r.id} className="hover:bg-ink-800/50">
                    <td className="px-5 py-3"><Link to={`/runs/${r.id}`} className="font-mono text-accent hover:underline">#{r.id}</Link></td>
                    <td className="px-5 py-3"><StatusBadge status={r.status} /></td>
                    <td className="hidden px-5 py-3 text-slate-400 md:table-cell">{r.metrics?.commits ?? "—"}</td>
                    <td className="hidden px-5 py-3 text-slate-400 md:table-cell">{r.metrics ? `${r.metrics.wall_time_ms.toFixed(0)} ms` : "—"}</td>
                    <td className="px-5 py-3 text-xs text-slate-500">{r.started_at ? new Date(r.started_at).toLocaleString() : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="flex items-center justify-between border-t border-ink-600/60 px-5 py-3 text-xs text-slate-500">
              <span>{data.total} runs</span>
              <div className="flex gap-2">
                <button disabled={page <= 1} onClick={() => setPage(p => p - 1)} className="min-h-[36px] rounded-md border border-ink-600 px-3 disabled:opacity-30">Prev</button>
                <button disabled={page * data.page_size >= data.total} onClick={() => setPage(p => p + 1)} className="min-h-[36px] rounded-md border border-ink-600 px-3 disabled:opacity-30">Next</button>
              </div>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
