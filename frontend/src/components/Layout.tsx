import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { Database, FlaskConical, GitCompareArrows, History, LayoutDashboard, LogOut, Microscope } from "lucide-react";
import { setToken } from "../lib/api";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/scenarios", label: "Scenarios", icon: FlaskConical },
  { to: "/history", label: "Run History", icon: History },
  { to: "/compare", label: "Repair Lab", icon: GitCompareArrows },
  { to: "/lab", label: "Lab Database", icon: Database },
];

export default function Layout() {
  const navigate = useNavigate();
  return (
    <div className="flex min-h-screen">
      <aside className="fixed inset-y-0 z-20 hidden w-60 flex-col border-r border-ink-600/60 bg-ink-900 lg:flex">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent/15">
            <Microscope className="h-4.5 w-4.5 h-5 w-5 text-accent" />
          </div>
          <div>
            <div className="text-sm font-bold tracking-wide text-slate-100">LockLens</div>
            <div className="text-[10px] uppercase tracking-widest text-slate-500">transaction intelligence</div>
          </div>
        </div>
        <nav className="mt-2 flex-1 space-y-0.5 px-3">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === "/"}
              className={({ isActive }) =>
                `flex min-h-[44px] items-center gap-2.5 rounded-lg px-3 text-sm transition ${
                  isActive ? "bg-ink-700 text-accent" : "text-slate-400 hover:bg-ink-800 hover:text-slate-200"}`}>
              <Icon className="h-4 w-4" /> {label}
            </NavLink>
          ))}
        </nav>
        <button
          onClick={() => { setToken(null); navigate("/login"); }}
          className="m-3 flex min-h-[44px] items-center gap-2.5 rounded-lg px-3 text-sm text-slate-400 hover:bg-ink-800 hover:text-slate-200">
          <LogOut className="h-4 w-4" /> Sign out
        </button>
      </aside>
      {/* mobile top bar */}
      <div className="fixed inset-x-0 top-0 z-20 flex items-center gap-1 overflow-x-auto border-b border-ink-600/60 bg-ink-900/95 px-2 py-1.5 backdrop-blur lg:hidden">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} end={to === "/"}
            className={({ isActive }) =>
              `flex min-h-[40px] shrink-0 items-center gap-1.5 rounded-lg px-2.5 text-xs ${isActive ? "bg-ink-700 text-accent" : "text-slate-400"}`}>
            <Icon className="h-3.5 w-3.5" /> {label}
          </NavLink>
        ))}
      </div>
      <main className="min-w-0 flex-1 px-4 pb-16 pt-20 sm:px-6 lg:ml-60 lg:px-8 lg:pt-8">
        <div className="mx-auto max-w-6xl fade-up"><Outlet /></div>
      </main>
    </div>
  );
}
