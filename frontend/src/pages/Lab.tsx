import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Card, CardHeader, ErrorState, Spinner, Btn } from "../components/ui";
import SqlEditor, { SqlHighlight } from "../components/SqlEditor";

export default function Lab() {
  const [info, setInfo] = useState<any>(null);
  const [schema, setSchema] = useState<any>(null);
  const [sql, setSql] = useState("SELECT * FROM lab.accounts WHERE id = 1");
  const [plan, setPlan] = useState<string[] | null>(null);
  const [error, setError] = useState("");
  const [explainError, setExplainError] = useState("");

  function load() {
    setError("");
    Promise.all([api("/api/lab/info"), api("/api/lab/schema")])
      .then(([i, s]) => { setInfo(i); setSchema(s); })
      .catch(e => setError(e.message));
  }
  useEffect(load, []);

  async function explain() {
    setExplainError(""); setPlan(null);
    try {
      const r = await api<{ plan: string[] }>("/api/lab/explain", { method: "POST", body: JSON.stringify({ sql }) });
      setPlan(r.plan);
    } catch (e: any) { setExplainError(e.message); }
  }

  if (error) return <ErrorState message={`Lab database unreachable: ${error}`} onRetry={load} />;
  if (!info || !schema) return <Spinner />;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Lab Database</h1>
        <p className="text-sm text-slate-500">The isolated PostgreSQL environment where experiments execute. Application metadata lives in a separate database.</p>
      </div>

      <Card>
        <CardHeader title="Server metadata" />
        <div className="space-y-1 px-5 py-4 text-xs">
          <p className="text-slate-300">{info.version}</p>
          <p className="text-slate-500">database: <span className="font-mono text-accent">{info.database}</span></p>
          <div className="mt-2 grid gap-1 sm:grid-cols-2">
            {Object.entries(info.settings).map(([k, v]) => (
              <div key={k} className="flex justify-between rounded bg-ink-850 px-3 py-1.5">
                <span className="font-mono text-slate-400">{k}</span><span className="font-mono text-slate-300">{String(v)}</span>
              </div>
            ))}
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader title="Lab schema" sub="Tables in schema lab (reset before every experiment run)" />
        {schema.tables.length === 0 ? (
          <p className="px-5 py-6 text-xs text-slate-500">No tables yet — run a scenario to seed the lab schema.</p>
        ) : (
          <div className="grid gap-3 p-5 md:grid-cols-2">
            {schema.tables.map((t: any) => (
              <div key={t.table} className="rounded-lg border border-ink-600/60 bg-ink-850 p-4">
                <div className="font-mono text-sm font-semibold text-accent">lab.{t.table}</div>
                <table className="mt-2 w-full text-xs">
                  <tbody>
                    {t.columns.map((c: any) => (
                      <tr key={c.name} className="border-t border-ink-700/40">
                        <td className="py-1 font-mono text-slate-300">{c.name}</td>
                        <td className="py-1 text-right font-mono text-slate-500">{c.type}{c.nullable ? "" : " NOT NULL"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {t.constraints.length > 0 && (
                  <div className="mt-2 space-y-0.5">
                    {t.constraints.map((c: any) => (
                      <div key={c.name} className="font-mono text-[10px] text-slate-500">{c.name}: {c.definition}</div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <CardHeader title="EXPLAIN" sub="Single-statement plan inspection against the lab database (validated, read/write DML only)" />
        <div className="space-y-3 p-5">
          <SqlEditor value={sql} onChange={setSql} />
          <div><Btn onClick={explain}>Explain</Btn></div>
          {explainError && <p className="text-xs text-bad">{explainError}</p>}
          {plan && <SqlHighlight sql={plan.join("\n")} />}
        </div>
      </Card>
    </div>
  );
}
