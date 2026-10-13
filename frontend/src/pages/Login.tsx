import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Microscope } from "lucide-react";
import { api, setToken } from "../lib/api";
import { Btn } from "../components/ui";

export default function Login() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const res = mode === "login"
        ? await api<{ access_token: string }>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) })
        : await api<{ access_token: string }>("/api/auth/register", { method: "POST", body: JSON.stringify({ email, display_name: name || email.split("@")[0], password }) });
      setToken(res.access_token);
      navigate("/");
    } catch (err: any) {
      setError(err.message || "authentication failed");
    } finally { setBusy(false); }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-ink-950 px-4">
      <div className="w-full max-w-sm fade-up">
        <div className="mb-8 flex flex-col items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent/15">
            <Microscope className="h-6 w-6 text-accent" />
          </div>
          <h1 className="text-xl font-bold text-slate-100">LockLens</h1>
          <p className="text-center text-xs text-slate-500">Transaction Intelligence &amp; Concurrency Experiment Platform</p>
        </div>
        <form onSubmit={submit} className="space-y-3 rounded-xl border border-ink-600/60 bg-ink-900 p-6 shadow-xl">
          <div className="flex rounded-lg bg-ink-800 p-1 text-xs font-medium">
            {(["login", "register"] as const).map(m => (
              <button type="button" key={m} onClick={() => setMode(m)}
                className={`min-h-[36px] flex-1 rounded-md capitalize transition ${mode === m ? "bg-ink-600 text-slate-100" : "text-slate-400"}`}>
                {m === "login" ? "Sign in" : "Create account"}
              </button>
            ))}
          </div>
          <input required type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="Email"
            className="min-h-[44px] w-full rounded-lg border border-ink-600 bg-ink-850 px-3 text-sm focus:border-accent/60 focus:outline-none" />
          {mode === "register" && (
            <input value={name} onChange={e => setName(e.target.value)} placeholder="Display name"
              className="min-h-[44px] w-full rounded-lg border border-ink-600 bg-ink-850 px-3 text-sm focus:border-accent/60 focus:outline-none" />
          )}
          <input required type="password" minLength={8} value={password} onChange={e => setPassword(e.target.value)}
            placeholder="Password (min 8 chars)"
            className="min-h-[44px] w-full rounded-lg border border-ink-600 bg-ink-850 px-3 text-sm focus:border-accent/60 focus:outline-none" />
          {error && <p className="text-xs text-bad">{error}</p>}
          <Btn type="submit" disabled={busy} className="w-full">
            {busy ? "…" : mode === "login" ? "Sign in" : "Create account"}
          </Btn>
        </form>
      </div>
    </div>
  );
}
