import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Plus, Save, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import type { Scenario, ScenarioDefinition, StepDef, TxDef } from "../lib/types";
import { Btn, Card, CardHeader, Spinner } from "../components/ui";
import SqlEditor from "../components/SqlEditor";

const ISO = ["READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"];

const EMPTY_DEF: ScenarioDefinition = {
  seed_sql: ["CREATE TABLE lab.items (id int PRIMARY KEY, n int NOT NULL)\nINSERT INTO lab.items VALUES (1, 0)"],
  transactions: [
    { name: "T1", isolation: "READ COMMITTED", steps: [{ kind: "sql", sql: "SELECT n FROM lab.items WHERE id = 1" }, { kind: "commit" }] },
    { name: "T2", isolation: "READ COMMITTED", steps: [{ kind: "sql", sql: "SELECT n FROM lab.items WHERE id = 1" }, { kind: "commit" }] },
  ],
  invariants: [],
  final_state_sql: "SELECT * FROM lab.items ORDER BY id",
};

export default function ScenarioEditor() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  const [category, setCategory] = useState("custom");
  const [description, setDescription] = useState("");
  const [def, setDef] = useState<ScenarioDefinition>(EMPTY_DEF);
  const [changeNote, setChangeNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(!!id);

  useEffect(() => {
    if (!id) return;
    api<Scenario>(`/api/scenarios/${id}`).then(s => {
      setScenario(s); setName(s.name); setKey(s.key); setCategory(s.category); setDescription(s.description);
      setDef(s.latest_version!.definition); setLoading(false);
    }).catch(e => { setError(e.message); setLoading(false); });
  }, [id]);

  function patchTx(i: number, patch: Partial<TxDef>) {
    const txs = def.transactions.slice(); txs[i] = { ...txs[i], ...patch };
    setDef({ ...def, transactions: txs });
  }
  function patchStep(ti: number, si: number, patch: Partial<StepDef>) {
    const steps = def.transactions[ti].steps.slice(); steps[si] = { ...steps[si], ...patch };
    patchTx(ti, { steps });
  }
  function addStep(ti: number, kind: StepDef["kind"]) {
    const steps = [...def.transactions[ti].steps];
    steps.splice(steps.length - 1, 0,
      kind === "sql" ? { kind, sql: "" } : kind === "checkpoint" ? { kind, name: "barrier" } : { kind });
    patchTx(ti, { steps });
  }

  async function save() {
    setBusy(true); setError("");
    const body = { key: key || name.toLowerCase().replace(/[^a-z0-9]+/g, "_").slice(0, 60), name, category, description, definition: def, change_note: changeNote };
    try {
      if (scenario) {
        await api(`/api/scenarios/${scenario.id}/versions`, { method: "POST", body: JSON.stringify(body) });
        navigate("/scenarios");
      } else {
        const s = await api<Scenario>("/api/scenarios", { method: "POST", body: JSON.stringify(body) });
        navigate("/scenarios");
      }
    } catch (e: any) {
      setError(typeof e.message === "string" ? e.message : "validation failed");
    } finally { setBusy(false); }
  }

  if (loading) return <Spinner />;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">{scenario ? `Edit: ${scenario.name}` : "New scenario"}</h1>
          <p className="text-sm text-slate-500">
            {scenario ? `Saved as v${(scenario.latest_version?.version ?? 0) + 1} — versions are immutable, runs reference an exact version.` : "Define seed data, per-transaction steps and business invariants."}
          </p>
        </div>
        <Btn onClick={save} disabled={busy}><Save className="h-4 w-4" /> {busy ? "Saving…" : "Save version"}</Btn>
      </div>
      {error && <div className="rounded-lg border border-bad/40 bg-bad/10 px-4 py-2 text-sm text-bad">{error}</div>}

      <Card className="grid gap-3 p-5 sm:grid-cols-2">
        <label className="text-xs text-slate-400">Name
          <input value={name} onChange={e => setName(e.target.value)} className="mt-1 min-h-[40px] w-full rounded-lg border border-ink-600 bg-ink-850 px-3 text-sm focus:border-accent/60 focus:outline-none" /></label>
        {!scenario && (
          <label className="text-xs text-slate-400">Key (optional)
            <input value={key} onChange={e => setKey(e.target.value)} placeholder="auto-from-name" className="mt-1 min-h-[40px] w-full rounded-lg border border-ink-600 bg-ink-850 px-3 text-sm focus:border-accent/60 focus:outline-none" /></label>
        )}
        <label className="text-xs text-slate-400 sm:col-span-2">Description
          <textarea value={description} onChange={e => setDescription(e.target.value)} rows={2} className="mt-1 w-full rounded-lg border border-ink-600 bg-ink-850 px-3 py-2 text-sm focus:border-accent/60 focus:outline-none" /></label>
        <label className="text-xs text-slate-400">Change note
          <input value={changeNote} onChange={e => setChangeNote(e.target.value)} className="mt-1 min-h-[40px] w-full rounded-lg border border-ink-600 bg-ink-850 px-3 text-sm focus:border-accent/60 focus:outline-none" /></label>
      </Card>

      <Card>
        <CardHeader title="Seed data" sub="Executed fresh before every run (schema lab, reset between runs)" />
        <div className="p-4 space-y-2">
          {def.seed_sql.map((s, i) => (
            <div key={i} className="flex gap-2">
              <SqlEditor value={s} rows={3} onChange={v => { const ss = def.seed_sql.slice(); ss[i] = v; setDef({ ...def, seed_sql: ss }); }} />
              <button onClick={() => setDef({ ...def, seed_sql: def.seed_sql.filter((_, j) => j !== i) })}
                className="self-start rounded-lg p-2 text-slate-500 hover:text-bad" aria-label="remove seed"><Trash2 className="h-4 w-4" /></button>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        {def.transactions.map((tx, ti) => (
          <Card key={tx.name}>
            <CardHeader
              title={<span className="font-mono text-accent">{tx.name}</span>}
              right={
                <select value={tx.isolation} onChange={e => patchTx(ti, { isolation: e.target.value })}
                  className="min-h-[36px] rounded-lg border border-ink-600 bg-ink-850 px-2 text-xs focus:border-accent/60 focus:outline-none">
                  {ISO.map(i => <option key={i}>{i}</option>)}
                </select>
              } />
            <div className="space-y-2 p-4">
              {tx.steps.map((step, si) => (
                <div key={si} className="flex items-start gap-2">
                  <span className="mt-2 w-5 text-right font-mono text-[10px] text-slate-600">{si}</span>
                  {step.kind === "sql" ? (
                    <div className="flex-1">
                      <SqlEditor value={step.sql ?? ""} onChange={v => patchStep(ti, si, { sql: v })} />
                      <input value={step.save_as ?? ""} onChange={e => patchStep(ti, si, { save_as: e.target.value || undefined })}
                        placeholder="save first cell as {{var}} (optional)"
                        className="mt-1 w-full rounded-md border border-ink-700 bg-ink-900 px-2 py-1 font-mono text-[11px] text-slate-400 focus:border-accent/60 focus:outline-none" />
                    </div>
                  ) : step.kind === "checkpoint" ? (
                    <div className="flex flex-1 items-center gap-2 rounded-lg border border-warn/30 bg-warn/5 px-3 py-2">
                      <span className="text-[10px] font-semibold uppercase tracking-wide text-warn">barrier</span>
                      <input value={step.name ?? ""} onChange={e => patchStep(ti, si, { name: e.target.value })}
                        className="w-full bg-transparent font-mono text-xs text-warn focus:outline-none" />
                    </div>
                  ) : (
                    <div className={`flex-1 rounded-lg border px-3 py-2 text-[11px] font-semibold uppercase tracking-wide ${step.kind === "commit" ? "border-ok/30 bg-ok/5 text-ok" : "border-slate-500/30 bg-slate-500/5 text-slate-400"}`}>
                      {step.kind}
                    </div>
                  )}
                  <button onClick={() => patchTx(ti, { steps: tx.steps.filter((_, j) => j !== si) })}
                    className="mt-2 rounded p-1 text-slate-600 hover:text-bad" aria-label="remove step"><Trash2 className="h-3.5 w-3.5" /></button>
                </div>
              ))}
              <div className="flex gap-2 pt-1">
                {(["sql", "checkpoint"] as const).map(k => (
                  <button key={k} onClick={() => addStep(ti, k)}
                    className="inline-flex min-h-[32px] items-center gap-1 rounded-md border border-ink-600 px-2 text-[11px] text-slate-400 hover:bg-ink-700">
                    <Plus className="h-3 w-3" /> {k === "sql" ? "SQL step" : "barrier"}
                  </button>
                ))}
              </div>
            </div>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader title="Invariants & final-state probe" sub="Checked after all transactions finish; final state is compared against every serial order (counterfactual)" />
        <div className="space-y-2 p-4">
          {def.invariants.map((inv, i) => (
            <div key={i} className="grid gap-2 rounded-lg border border-ink-700 p-3 sm:grid-cols-[160px_1fr_120px_36px]">
              <input value={inv.name} onChange={e => { const a = def.invariants.slice(); a[i] = { ...inv, name: e.target.value }; setDef({ ...def, invariants: a }); }}
                placeholder="invariant name" className="min-h-[36px] rounded-md border border-ink-600 bg-ink-850 px-2 text-xs focus:outline-none" />
              <SqlEditor value={inv.sql} onChange={v => { const a = def.invariants.slice(); a[i] = { ...inv, sql: v }; setDef({ ...def, invariants: a }); }} />
              <input value={inv.expect} onChange={e => { const a = def.invariants.slice(); a[i] = { ...inv, expect: e.target.value }; setDef({ ...def, invariants: a }); }}
                placeholder="expect" className="min-h-[36px] self-start rounded-md border border-ink-600 bg-ink-850 px-2 font-mono text-xs focus:outline-none" />
              <button onClick={() => setDef({ ...def, invariants: def.invariants.filter((_, j) => j !== i) })} className="self-start rounded p-2 text-slate-600 hover:text-bad" aria-label="remove invariant"><Trash2 className="h-3.5 w-3.5" /></button>
            </div>
          ))}
          <button onClick={() => setDef({ ...def, invariants: [...def.invariants, { name: "", sql: "", expect: "" }] })}
            className="inline-flex min-h-[32px] items-center gap-1 rounded-md border border-ink-600 px-2 text-[11px] text-slate-400 hover:bg-ink-700">
            <Plus className="h-3 w-3" /> invariant
          </button>
          <label className="block pt-2 text-xs text-slate-400">Final state probe (single SELECT)
            <SqlEditor value={def.final_state_sql ?? ""} onChange={v => setDef({ ...def, final_state_sql: v || null })} />
          </label>
        </div>
      </Card>
    </div>
  );
}
