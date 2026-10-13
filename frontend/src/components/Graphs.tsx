import { useMemo } from "react";
import ReactFlow, { Background, Controls, MarkerType } from "reactflow";
import "reactflow/dist/style.css";

type Edge = { from_tx: string; to_tx: string; kind: string; evidence: any };

const KIND_STYLE: Record<string, { color: string; dash?: string; label: string }> = {
  observed_wait: { color: "#f87171", label: "waits-on (observed)" },
  declared_rw: { color: "#fbbf24", dash: "6 4", label: "rw (declared)" },
  declared_wr: { color: "#22d3ee", dash: "6 4", label: "wr (declared)" },
  declared_ww: { color: "#c4b5fd", dash: "6 4", label: "ww (declared)" },
};

export function DependencyGraph({ edges, title }: { edges: Edge[]; title: string }) {
  const { nodes, rfEdges } = useMemo(() => {
    const names = Array.from(new Set(edges.flatMap(e => [e.from_tx, e.to_tx]))).sort();
    const nodes = names.map((n, i) => ({
      id: n,
      position: { x: 60 + (i % 4) * 170, y: 60 + Math.floor(i / 4) * 110 },
      data: { label: n },
      style: {
        background: "#111c33", color: "#e2e8f0", border: "1px solid #243354",
        borderRadius: 10, padding: "8px 14px", fontSize: 13, fontWeight: 600, width: 80, textAlign: "center" as const,
      },
    }));
    const rfEdges = edges.map((e, i) => {
      const st = KIND_STYLE[e.kind] ?? { color: "#64748b", label: e.kind };
      return {
        id: `e${i}`, source: e.from_tx, target: e.to_tx, label: st.label.split(" ")[0],
        animated: e.kind === "observed_wait",
        style: { stroke: st.color, strokeWidth: 1.6, strokeDasharray: st.dash },
        labelStyle: { fill: st.color, fontSize: 10 },
        labelBgStyle: { fill: "#0b1220" },
        markerEnd: { type: MarkerType.ArrowClosed, color: st.color },
      };
    });
    return { nodes, rfEdges };
  }, [edges]);

  if (!edges.length) return <p className="px-5 py-8 text-center text-xs text-slate-500">No edges recorded for this run.</p>;
  return (
    <div className="h-64 w-full">
      <ReactFlow nodes={nodes} edges={rfEdges} fitView proOptions={{ hideAttribution: true }}
        nodesDraggable={false} nodesConnectable={false} elementsSelectable={false} zoomOnScroll={false}>
        <Background color="#1a2742" gap={20} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

/** Split edges into the two graphs the product keeps separate: observed wait-for vs declared dependencies. */
export function GraphPair({ edges }: { edges: Edge[] }) {
  const wait = edges.filter(e => e.kind === "observed_wait");
  const declared = edges.filter(e => e.kind !== "observed_wait");
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div>
        <p className="mb-1 px-1 text-[11px] font-semibold uppercase tracking-wider text-bad">Wait-for graph (observed via pg_locks)</p>
        <div className="overflow-hidden rounded-lg border border-ink-600/60"><DependencyGraph edges={wait} title="wait" /></div>
      </div>
      <div>
        <p className="mb-1 px-1 text-[11px] font-semibold uppercase tracking-wider text-warn">Dependency graph (declared, table-level)</p>
        <div className="overflow-hidden rounded-lg border border-ink-600/60"><DependencyGraph edges={declared} title="dep" /></div>
      </div>
    </div>
  );
}
