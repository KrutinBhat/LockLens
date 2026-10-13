import React from "react";
import { CheckCircle2, AlertTriangle, XCircle, Info, Loader2, Inbox } from "lucide-react";

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-ink-600/60 bg-ink-900/80 shadow-lg shadow-black/20 ${className}`}>{children}</div>;
}

export function CardHeader({ title, sub, right }: { title: React.ReactNode; sub?: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-ink-600/50 px-5 py-3.5">
      <div>
        <h3 className="text-sm font-semibold tracking-wide text-slate-100">{title}</h3>
        {sub && <p className="mt-0.5 text-xs text-slate-400">{sub}</p>}
      </div>
      {right}
    </div>
  );
}

const STATUS_STYLE: Record<string, string> = {
  succeeded: "text-ok border-ok/30 bg-ok/10",
  anomaly_detected: "text-bad border-bad/30 bg-bad/10",
  failed: "text-bad border-bad/30 bg-bad/10",
  cancelled: "text-warn border-warn/30 bg-warn/10",
  timed_out: "text-warn border-warn/30 bg-warn/10",
  running: "text-accent border-accent/30 bg-accent/10",
  paused: "text-warn border-warn/30 bg-warn/10",
  queued: "text-slate-300 border-slate-500/30 bg-slate-500/10",
  confirmed: "text-bad border-bad/30 bg-bad/10",
  potential: "text-warn border-warn/30 bg-warn/10",
  inconclusive: "text-slate-300 border-slate-500/30 bg-slate-500/10",
  committed: "text-ok border-ok/30 bg-ok/10",
  rolled_back: "text-slate-300 border-slate-500/30 bg-slate-500/10",
  aborted_deadlock: "text-bad border-bad/30 bg-bad/10",
  aborted_serialization: "text-warn border-warn/30 bg-warn/10",
  aborted_lock_timeout: "text-warn border-warn/30 bg-warn/10",
  aborted_statement_timeout: "text-warn border-warn/30 bg-warn/10",
};

export function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_STYLE[status] ?? "text-slate-300 border-slate-500/30 bg-slate-500/10";
  const live = status === "running" || status === "queued";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${cls}`}>
      {live && <span className="live-dot inline-block h-1.5 w-1.5 rounded-full bg-current" />}
      {status.replace(/_/g, " ")}
    </span>
  );
}

export function FindingIcon({ status }: { status: string }) {
  if (status === "confirmed") return <XCircle className="h-4 w-4 text-bad" />;
  if (status === "potential") return <AlertTriangle className="h-4 w-4 text-warn" />;
  if (status === "ok") return <CheckCircle2 className="h-4 w-4 text-ok" />;
  return <Info className="h-4 w-4 text-slate-400" />;
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-slate-400">
      <Loader2 className="h-4 w-4 animate-spin" /> <span className="text-sm">{label}</span>
    </div>
  );
}

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 py-14 text-center">
      <Inbox className="h-8 w-8 text-slate-600" />
      <p className="text-sm font-medium text-slate-300">{title}</p>
      {hint && <p className="max-w-sm text-xs text-slate-500">{hint}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 py-14 text-center">
      <XCircle className="h-8 w-8 text-bad" />
      <p className="text-sm text-slate-300">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="rounded-lg border border-ink-600 px-3 py-1.5 text-xs text-slate-300 hover:bg-ink-700">
          Retry
        </button>
      )}
    </div>
  );
}

export function Btn({ children, variant = "primary", className = "", ...rest }: any) {
  const base = "inline-flex min-h-[36px] items-center justify-center gap-1.5 rounded-lg px-3.5 py-1.5 text-sm font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-40";
  const styles: Record<string, string> = {
    primary: "bg-accent text-ink-950 hover:bg-cyan-300",
    ghost: "border border-ink-600 text-slate-300 hover:bg-ink-700",
    danger: "border border-bad/40 text-bad hover:bg-bad/10",
  };
  return <button className={`${base} ${styles[variant]} ${className}`} {...rest}>{children}</button>;
}
