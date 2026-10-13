import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { GitCompareArrows } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../lib/api";
import type { Comparison, Page, Scenario } from "../lib/types";
import { Btn, Card, CardHeader, EmptyState, ErrorState, Spinner } from "../components/ui";

const CHANGES = [
  { value: "for_update", label: "Add SELECT … FOR UPDATE", desc: "Explicit row locks on reads" },
  { value: "isolation:REPEATABLE READ", label: "Isolation → REPEATABLE READ", desc: "Snapshot isolation" },
  { value: "isolation:SERIALIZABLE", label: "Isolation → SERIALIZABLE", desc: "SSI — aborts dangerous structures" },
  { value: "lock_order", label: "Consistent lock ordering", desc: "Sort UPDATE steps by row id" },
];

function parseChange(v: string) {
  if (v === "for_update") return { for_update: true };
  if (v === "lock_order") return { lock_order: true };
  if (v.startsWith("isolation:")) return { isolation: v.split(":")[1] };
  return {};
}

export default function Compare() {
  const [scenarios, setScenarios] = useState<Page<Scenario> | null>(null);
  const [comparisons, setComparisons] = useState<Comparison[] | null>(null);
  const [scenarioId, setScenarioId] = useState<number | null>(null);
  const [change, setChange] = useState(CHANGES[0].value);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function load() {
    api<Page<Scenario>>("/api/scenarios?page_size=100").then(s => { setScenarios(s); setScenarioId(s.items[0]?.id ?? null); }).catch(e => setError(e.message));
    api<Comparison[]>("/api/comparisons").then(setComparisons).catch(() => setComparisons([]));
  }
  useEffect(load, []);
  useEffect(() => {
    const t = setInterval(() => api<Comparison[]>("/api/comparisons").then(setComparisons).catch(() => {}), 2000);
    return () => clearInterval(t);
  }, []);

  async function submit() {
    const s = scenarios?.items.find(x => x.id === scenarioId);
    if (!s?.latest_version) return;
    setBusy(true); setError("");
    try {
      await api("/api/comparisons", { method: "POST", body: JSON.stringify({
        name: name || `${s.key} · ${change}`, scenario_version_id: s.latest_version.id, change: parseChange(change) }) });
      setName("");
      load();
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  }

  if (error && !scenarios) return <ErrorState message={error} onRetry={load} />;
  if (!scenarios || !comparisons) return <Spinner />;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Counterfactual Repair Lab</h1>
        <p className="text-sm text-slate-500">Run a baseline and a controlled variant; compare correctness and measured cost. Production SQL is never modified — candidates run in the lab.</p>
      </div>

      <Card>
        <CardHeader title="New comparison" sub="Both sides execute as fresh, checkpoint-deterministic runs" />
        <div className="grid gap-3 p-5 sm:grid-cols-3">
          <label className="text-xs text-slate-400">Scenario
            <select value={scenarioId ?? ""} onChange={e => setScenarioId(Number(e.target.value))}
              className="mt-1 min-h-[40px] w-full rounded-lg border border-ink-600 bg-ink-850 px-2 text-sm focus:border-accent/60 focus:outline-none">
              {scenarios.items.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select></label>
          <label className="text-xs text-slate-400">Controlled change
            <select value={change} onChange={e => setChange(e.target.value)}
              className="mt-1 min-h-[40px] w-full rounded-lg border border-ink-600 bg-ink-850 px-2 text-sm focus:border-accent/60 focus:outline-none">
              {CHANGES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select></label>
          <label className="text-xs text-slate-400">Name (optional)
            <input value={name} onChange={e => setName(e.target.value)}
              className="mt-1 min-h-[40px] w-full rounded-lg border border-ink-600 bg-ink-850 px-3 text-sm focus:border-accent/60 focus:outline-none" /></label>
        </div>
        <div className="flex items-center justify-between border-t border-ink-600/50 px-5 py-3">
          <p className="text-xs text-slate-500">{CHANGES.find(c => c.value === change)?.desc}</p>
          <Btn onClick={submit} disabled={busy || scenarioId == null}><GitCompareArrows className="h-4 w-4" /> {busy ? "Launching…" : "Run comparison"}</Btn>
        </div>
      </Card>

      {comparisons.length === 0 ? (
        <Card><EmptyState title="No comparisons yet" hint="Compare a baseline anomaly with a repair to measure its effect." /></Card>
      ) : comparisons.map(c => {
        const v = c.verdict ?? {};
        const running = !c.baseline_run_id || v.status === "running";
        const chartData = v.baseline && v.candidate ? [
          { metric: "wall ms", baseline: v.baseline.wall_time_ms, candidate: v.candidate.wall_time_ms },
          { metric: "lock-wait ms", baseline: v.baseline.total_lock_wait_ms, candidate: v.candidate.total_lock_wait_ms },
          { metric: "invariant violations", baseline: v.baseline.invariant_violations, candidate: v.candidate.invariant_violations },
          { metric: "aborts", baseline: (v.baseline.deadlocks + v.baseline.serialization_failures), candidate: (v.candidate.deadlocks + v.candidate.serialization_failures) },
        ] : [];
        return (
          <Card key={c.id}>
            <CardHeader title={c.name}
              sub={running ? "Running baseline and candidate…" : `baseline #${c.baseline_run_id} vs candidate #${c.candidate_run_id}`}
              right={!running && (v.correctness_improved
                ? <span className="rounded-full border border-ok/30 bg-ok/10 px-2.5 py-0.5 text-[11px] text-ok">correctness improved</span>
                : <span className="rounded-full border border-warn/30 bg-warn/10 px-2.5 py-0.5 text-[11px] text-warn">no correctness gain</span>)} />
            {running ? <Spinner label="Executing both runs against the lab database…" /> : v.status === "failed" ? (
              <p className="px-5 py-4 text-sm text-bad">{v.error}</p>
            ) : (
              <div className="grid gap-4 p-5 lg:grid-cols-2">
                <div className="h-56">
                  <ResponsiveContainer>
                    <BarChart data={chartData}>
                      <CartesianGrid stroke="#1a2742" strokeDasharray="3 3" />
                      <XAxis dataKey="metric" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                      <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
                      <Tooltip contentStyle={{ background: "#0e1628", border: "1px solid #243354", borderRadius: 8, fontSize: 12 }} />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      <Bar dataKey="baseline" fill="#f87171" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="candidate" fill="#22d3ee" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="space-y-2 text-xs">
                  <div className="grid grid-cols-2 gap-2">
                    {[["Baseline", v.baseline], ["Candidate", v.candidate]].map(([label, s]: any) => (
                      <div key={label} className="rounded-lg border border-ink-600/60 bg-ink-850 p-3">
                        <div className="mb-1 font-semibold text-slate-300">{label} <Link className="font-mono text-accent hover:underline" to={`/runs/${s.run_id}`}>#{s.run_id}</Link></div>
                        <div className="space-y-0.5 text-slate-400">
                          <div>status: {s.status}</div>
                          <div>anomalies: {s.anomalies.length ? s.anomalies.join(", ") : "none"}</div>
                          <div>outcomes: {Object.entries(s.outcomes).map(([k, o]) => `${k}:${o}`).join(" ")}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="rounded-lg border border-warn/30 bg-warn/5 p-3 text-warn/90">
                    <div className="mb-1 font-semibold">Limitations</div>
                    <ul className="list-inside list-disc space-y-0.5">{(v.limitations ?? []).map((l: string, i: number) => <li key={i}>{l}</li>)}</ul>
                  </div>
                </div>
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}
