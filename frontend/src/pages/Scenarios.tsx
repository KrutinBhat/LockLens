import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Copy, Pencil, Play, Plus, Search } from "lucide-react";
import { api } from "../lib/api";
import type { Page, Run, Scenario } from "../lib/types";
import { Btn, Card, CardHeader, EmptyState, ErrorState, Spinner } from "../components/ui";

const CATEGORIES = ["", "lost_update", "non_repeatable_read", "write_skew", "deadlock", "serialization_failure", "custom"];

export default function Scenarios() {
  const [data, setData] = useState<Page<Scenario> | null>(null);
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  function load() {
    setError("");
    api<Page<Scenario>>(`/api/scenarios?q=${encodeURIComponent(q)}&category=${category}&page_size=50`)
      .then(setData).catch(e => setError(e.message));
  }
  useEffect(load, [q, category]);

  async function runNow(s: Scenario) {
    if (!s.latest_version) return;
    const run = await api<Run>("/api/runs", { method: "POST", body: JSON.stringify({ scenario_version_id: s.latest_version.id }) });
    navigate(`/runs/${run.id}`);
  }
  async function clone(s: Scenario) {
    await api(`/api/scenarios/${s.id}/clone`, { method: "POST" });
    load();
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Scenario Library</h1>
          <p className="text-sm text-slate-500">Deterministic multi-transaction schedules over a real PostgreSQL lab.</p>
        </div>
        <Link to="/scenarios/new"><Btn><Plus className="h-4 w-4" /> New scenario</Btn></Link>
      </div>

      <div className="flex flex-wrap gap-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search scenarios…"
            className="min-h-[40px] w-64 rounded-lg border border-ink-600 bg-ink-850 pl-9 pr-3 text-sm focus:border-accent/60 focus:outline-none" />
        </div>
        <div className="flex flex-wrap gap-1">
          {CATEGORIES.map(c => (
            <button key={c} onClick={() => setCategory(c)}
              className={`min-h-[40px] rounded-lg px-3 text-xs font-medium transition ${category === c ? "bg-accent/15 text-accent" : "text-slate-400 hover:bg-ink-800"}`}>
              {c === "" ? "All" : c.replace(/_/g, " ")}
            </button>
          ))}
        </div>
      </div>

      {error ? <ErrorState message={error} onRetry={load} /> : !data ? <Spinner /> : data.items.length === 0 ? (
        <Card><EmptyState title="No scenarios match" hint="Adjust the filter, or create a new scenario." /></Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {data.items.map(s => (
            <Card key={s.id} className="flex flex-col p-5">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="truncate text-sm font-semibold text-slate-100">{s.name}</h3>
                    {s.is_template && <span className="rounded-full border border-accent/30 bg-accent/10 px-2 py-0.5 text-[10px] text-accent">library</span>}
                  </div>
                  <span className="text-[11px] uppercase tracking-wide text-slate-500">{s.category.replace(/_/g, " ")} · v{s.latest_version?.version ?? 0}</span>
                </div>
              </div>
              <p className="mt-2 line-clamp-3 flex-1 text-xs leading-relaxed text-slate-400">{s.description}</p>
              <div className="mt-4 flex gap-2">
                <Btn onClick={() => runNow(s)} className="flex-1"><Play className="h-3.5 w-3.5" /> Run</Btn>
                {s.is_template ? (
                  <Btn variant="ghost" onClick={() => clone(s)} title="Clone into your project to edit"><Copy className="h-3.5 w-3.5" /> Clone</Btn>
                ) : (
                  <Link to={`/scenarios/${s.id}/edit`} className="flex-1"><Btn variant="ghost" className="w-full"><Pencil className="h-3.5 w-3.5" /> Edit</Btn></Link>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
