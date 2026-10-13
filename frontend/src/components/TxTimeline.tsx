import { useMemo } from "react";
import type { ExecutionEvent } from "../lib/types";

const KIND_COLOR: Record<string, string> = {
  begin: "bg-slate-500", commit: "bg-ok", rollback: "bg-slate-400",
  step_start: "bg-accent/60", step_ok: "bg-accent", step_error: "bg-bad",
  checkpoint_wait: "bg-warn/70", checkpoint_release: "bg-warn",
  paused: "bg-warn", resumed: "bg-ok", cancelled: "bg-bad", timeout: "bg-bad", seeded: "bg-violet-400",
};

const TX_ORDER = ["T1", "T2", "T3", "T4"];

/** Interactive per-transaction execution timeline: one lane per transaction,
 * events positioned by global sequence; click an event to inspect it. */
export default function TxTimeline({ events, selected, onSelect }:
  { events: ExecutionEvent[]; selected: number | null; onSelect: (seq: number) => void }) {
  const lanes = useMemo(() => {
    const txs = Array.from(new Set(events.map(e => e.tx_name).filter(Boolean) as string[]))
      .sort((a, b) => TX_ORDER.indexOf(a) - TX_ORDER.indexOf(b));
    return ["orchestrator", ...txs];
  }, [events]);

  const laneOf = (tx: string | null) => (tx ? lanes.indexOf(tx) : 0);
  const laneH = 34;

  return (
    <div className="overflow-x-auto">
      <div style={{ minWidth: Math.max(560, events.length * 26) }} className="relative">
        <div className="flex">
          <div className="w-24 shrink-0" />
          <div className="relative flex-1" style={{ height: lanes.length * laneH }}>
            {lanes.map((l, i) => (
              <div key={l} className="absolute inset-x-0 border-t border-ink-700/60" style={{ top: i * laneH + laneH / 2 }} />
            ))}
            {events.map((e, i) => {
              const lane = laneOf(e.tx_name);
              const left = events.length > 1 ? (i / (events.length - 1)) * 100 : 50;
              const isSel = selected === e.seq;
              return (
                <button key={e.seq} onClick={() => onSelect(e.seq)} title={`#${e.seq} ${e.kind} ${e.sql_text}`}
                  aria-label={`event ${e.seq} ${e.kind}`}
                  className={`absolute h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border transition hover:scale-125 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent
                    ${KIND_COLOR[e.kind] ?? "bg-slate-500"} ${isSel ? "ring-2 ring-white scale-125 z-10" : "border-ink-950"}`}
                  style={{ left: `${left}%`, top: lane * laneH + laneH / 2 }} />
              );
            })}
          </div>
        </div>
        <div className="pointer-events-none absolute left-0 top-0 w-24">
          {lanes.map((l, i) => (
            <div key={l} className="flex items-center text-[11px] font-semibold text-slate-400" style={{ height: laneH }}>
              {l === "orchestrator" ? "engine" : l}
            </div>
          ))}
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-slate-500">
        {Object.entries(KIND_COLOR).map(([k, c]) => (
          <span key={k} className="inline-flex items-center gap-1"><span className={`h-2 w-2 rounded-full ${c}`} />{k.replace(/_/g, " ")}</span>
        ))}
      </div>
    </div>
  );
}
