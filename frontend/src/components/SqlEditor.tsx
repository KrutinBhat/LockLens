import { useMemo } from "react";

const KW = /\b(SELECT|FROM|WHERE|UPDATE|SET|INSERT|INTO|VALUES|DELETE|BEGIN|COMMIT|ROLLBACK|AND|OR|NOT|NULL|TRUE|FALSE|JOIN|ON|AS|ORDER|BY|GROUP|COUNT|SUM|CASE|WHEN|THEN|ELSE|END|FOR|CREATE|TABLE|PRIMARY|KEY|CHECK)\b/gi;

/** Lightweight SQL display with regex highlighting; used for read-only SQL and (plain) editing textarea. */
export function SqlHighlight({ sql, className = "" }: { sql: string; className?: string }) {
  const html = useMemo(() => highlight(sql), [sql]);
  return (
    <pre className={`sql-editor overflow-x-auto whitespace-pre-wrap break-all rounded-lg bg-ink-850 p-3 text-slate-300 ${className}`}
      dangerouslySetInnerHTML={{ __html: html }} />
  );
}

function esc(s: string) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }

export function highlight(sql: string): string {
  let out = esc(sql);
  out = out.replace(/('[^']*')/g, '<span class="str">$1</span>');
  out = out.replace(/\b(\d+(?:\.\d+)?)\b/g, '<span class="num">$1</span>');
  out = out.replace(KW, m => `<span class="kw">${m.toUpperCase()}</span>`);
  return out;
}

export default function SqlEditor({ value, onChange, rows = 2, placeholder, disabled }:
  { value: string; onChange?: (v: string) => void; rows?: number; placeholder?: string; disabled?: boolean }) {
  if (!onChange) return <SqlHighlight sql={value} />;
  return (
    <textarea
      value={value} disabled={disabled} rows={rows} placeholder={placeholder} spellCheck={false}
      onChange={e => onChange(e.target.value)}
      className="sql-editor w-full resize-y rounded-lg border border-ink-600/60 bg-ink-850 p-3 text-slate-200 placeholder:text-slate-600 focus:border-accent/60 focus:outline-none disabled:opacity-50"
    />
  );
}
