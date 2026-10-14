import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Activity, ArrowRight, FlaskConical, GitCompareArrows, Play, ShieldCheck, Sparkles, Zap } from "lucide-react";
import { api } from "../lib/api";
import type { Page, Run, Scenario } from "../lib/types";
import { Btn, Card, CardHeader, EmptyState, ErrorState, Spinner, StatusBadge } from "../components/ui";

export default function Dashboard() {
  const [runs, setRuns] = useState<Page<Run> | null>(null);
  const [scenarios, setScenarios] = useState<Page<Scenario> | null>(null);
  const [error, setError] = useState("");
  const [launchingId, setLaunchingId] = useState<number | null>(null);
  const navigate = useNavigate();

  function load() {
    setError("");
    Promise.all([api<Page<Run>>("/api/runs?page_size=6"), api<Page<Scenario>>("/api/scenarios?page_size=6")])
      .then(([r, s]) => { setRuns(r); setScenarios(s); })
      .catch(e => setError(e.message));
  }
  useEffect(load, []);

  if (error) return <ErrorState message={`Could not reach the LockLens API: ${error}`} onRetry={load} />;
  if (!runs || !scenarios) return <Spinner />;

  const anomalies = runs.items.filter(r => r.status === "anomaly_detected").length;
  const activeRuns = runs.items.filter(r => ["running", "queued", "paused"].includes(r.status)).length;
  const completedRuns = runs.items.filter(r => ["succeeded", "anomaly_detected"].includes(r.status)).length;
  const quick = scenarios.items.slice(0, 4);
  const stats = [
    { icon: Activity, label: "All runs", value: runs.total, hint: `${completedRuns} recently completed` },
    { icon: Zap, label: "Findings", value: anomalies, hint: anomalies ? "Needs investigation" : "No recent anomalies" },
    { icon: FlaskConical, label: "Scenarios", value: scenarios.total, hint: "Ready to run" },
    { icon: GitCompareArrows, label: "Active runs", value: activeRuns, hint: activeRuns ? "Live now" : "Ready when you are", to: "/history" },
  ];

  async function runNow(s: Scenario) {
    if (!s.latest_version) return;
    setLaunchingId(s.id);
    try {
      const run = await api<Run>("/api/runs", { method: "POST", body: JSON.stringify({ scenario_version_id: s.latest_version.id }) });
      navigate(`/runs/${run.id}`);
    } catch (e: any) {
      setError(e.message || "Could not start the experiment.");
    } finally {
      setLaunchingId(null);
    }
  }

  return <div className="space-y-6">
    <section className="relative overflow-hidden rounded-2xl border border-accent/20 bg-gradient-to-br from-ink-850 via-ink-900 to-ink-950 px-5 py-6 shadow-xl shadow-black/20 sm:px-7">
      <div className="absolute -right-8 -top-10 h-40 w-40 rounded-full bg-accent/10 blur-3xl" />
      <div className="relative flex flex-wrap items-end justify-between gap-5">
        <div><div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-[.16em] text-accent"><Sparkles className="h-3.5 w-3.5" /> Concurrency command center</div><h1 className="text-2xl font-bold tracking-tight text-slate-100 sm:text-3xl">Dashboard</h1><p className="mt-1 text-base font-medium text-slate-300">See every transaction decision.</p><p className="mt-2 max-w-xl text-sm leading-6 text-slate-400">Launch deterministic schedules, inspect lock evidence, and test repair strategies without leaving your lab.</p></div>
        <Link to="/scenarios"><Btn><Play className="h-4 w-4" /> Explore scenarios</Btn></Link>
      </div>
    </section>

    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {stats.map(({ icon: Icon, label, value, hint, to }) => <Card key={label} className="p-4 transition hover:-translate-y-0.5 hover:border-ink-600 hover:shadow-xl hover:shadow-black/25"><div className="flex items-center justify-between gap-2 text-slate-500"><span className="text-xs font-medium">{label}</span><Icon className="h-4 w-4 text-accent/80" /></div>{to ? <Link to={to} className="mt-1 block text-2xl font-semibold text-slate-100 hover:text-accent">{value}</Link> : <div className="mt-1 text-2xl font-semibold text-slate-100">{value}</div>}<div className="mt-1 text-[11px] text-slate-500">{hint}</div></Card>)}
    </div>

    <div className="grid gap-4 lg:grid-cols-2">
      <Card><CardHeader title="Recent experiments" sub="Latest activity across your projects" right={<Link to="/history" className="inline-flex items-center gap-1 text-xs text-accent hover:underline">View all <ArrowRight className="h-3 w-3" /></Link>} />
        {runs.items.length === 0 ? <EmptyState title="No runs yet" hint="Execute a scenario from the library to see live transaction evidence here." /> : <ul className="divide-y divide-ink-700/50">{runs.items.map(r => <li key={r.id}><Link to={`/runs/${r.id}`} className="flex items-center justify-between gap-3 px-5 py-3.5 transition hover:bg-ink-800/60"><div className="min-w-0"><div className="truncate text-sm text-slate-200">Run #{r.id}</div><div className="text-xs text-slate-500">{new Date(r.created_at).toLocaleString()}</div></div><StatusBadge status={r.status} /></Link></li>)}</ul>}
      </Card>
      <Card><CardHeader title="Run a trusted scenario" sub="Start a reproducible lab schedule in one click" />
        <div className="grid gap-2 p-4 sm:grid-cols-2">{quick.map(s => <button key={s.id} onClick={() => runNow(s)} disabled={launchingId !== null} className="group rounded-xl border border-ink-600/60 bg-ink-850 p-3 text-left transition hover:border-accent/50 hover:bg-ink-800 disabled:cursor-wait disabled:opacity-60"><div className="flex items-center justify-between gap-2 text-sm font-medium text-slate-200"><span>{s.name.split("—")[0]}</span>{launchingId === s.id ? <span className="soft-pulse text-xs text-accent">Starting…</span> : <Play className="h-3.5 w-3.5 text-slate-500 transition group-hover:text-accent" />}</div><div className="mt-0.5 text-[11px] uppercase tracking-wide text-slate-500">{s.category.replace(/_/g, " ")}</div></button>)}{quick.length === 0 && <EmptyState title="No scenarios available" hint="Create a scenario to begin experimenting." />}</div>
      </Card>
    </div>
    <div className="flex items-center gap-2 rounded-xl border border-ink-700/70 bg-ink-900/50 px-4 py-3 text-xs text-slate-400"><ShieldCheck className="h-4 w-4 shrink-0 text-ok" /> Experiments run in the isolated lab database; application records remain separate.</div>
  </div>;
}
