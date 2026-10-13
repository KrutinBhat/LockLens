import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Activity, FlaskConical, GitCompareArrows, Play, Zap } from "lucide-react";
import { api } from "../lib/api";
import type { Page, Run, Scenario } from "../lib/types";
import { Btn, Card, CardHeader, EmptyState, ErrorState, Spinner, StatusBadge } from "../components/ui";

export default function Dashboard() {
  const [runs, setRuns] = useState<Page<Run> | null>(null);
  const [scenarios, setScenarios] = useState<Page<Scenario> | null>(null);
  const [error, setError] = useState("");
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
  const quick = scenarios.items.slice(0, 4);

  async function runNow(s: Scenario) {
    if (!s.latest_version) return;
    const run = await api<Run>("/api/runs", { method: "POST", body: JSON.stringify({ scenario_version_id: s.latest_version.id }) });
    navigate(`/runs/${run.id}`);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Dashboard</h1>
          <p className="text-sm text-slate-500">Reproduce, observe and repair database concurrency anomalies.</p>
        </div>
        <Link to="/scenarios"><Btn><Play className="h-4 w-4" /> New experiment</Btn></Link>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          { icon: Activity, label: "Recent runs", value: runs.total },
          { icon: Zap, label: "Anomalies (recent)", value: anomalies },
          { icon: FlaskConical, label: "Scenarios", value: scenarios.total },
          { icon: GitCompareArrows, label: "Repair Lab", value: "compare", to: "/compare" },
        ].map(({ icon: Icon, label, value, to }) => (
          <Card key={label} className="p-4">
            <div className="flex items-center gap-2 text-slate-500"><Icon className="h-4 w-4" /><span className="text-xs">{label}</span></div>
            {to ? <Link to={to} className="mt-1 block text-lg font-semibold text-accent hover:underline">{value}</Link>
              : <div className="mt-1 text-2xl font-semibold text-slate-100">{value}</div>}
          </Card>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Recent experiments" sub="Latest runs across your projects" right={<Link to="/history" className="text-xs text-accent hover:underline">View all</Link>} />
          {runs.items.length === 0 ? (
            <EmptyState title="No runs yet" hint="Execute a scenario from the library to see live transaction evidence here." />
          ) : (
            <ul className="divide-y divide-ink-700/50">
              {runs.items.map(r => (
                <li key={r.id}>
                  <Link to={`/runs/${r.id}`} className="flex items-center justify-between gap-3 px-5 py-3 hover:bg-ink-800/60">
                    <div className="min-w-0">
                      <div className="truncate text-sm text-slate-200">Run #{r.id}</div>
                      <div className="text-xs text-slate-500">{new Date(r.created_at).toLocaleString()}</div>
                    </div>
                    <StatusBadge status={r.status} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card>
          <CardHeader title="Quick actions" sub="Launch a library anomaly in one click" />
          <div className="grid gap-2 p-4 sm:grid-cols-2">
            {quick.map(s => (
              <button key={s.id} onClick={() => runNow(s)}
                className="rounded-lg border border-ink-600/60 bg-ink-850 p-3 text-left transition hover:border-accent/50 hover:bg-ink-800">
                <div className="text-sm font-medium text-slate-200">{s.name.split("—")[0]}</div>
                <div className="mt-0.5 text-[11px] uppercase tracking-wide text-slate-500">{s.category.replace(/_/g, " ")}</div>
              </button>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
