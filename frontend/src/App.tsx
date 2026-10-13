import { Navigate, Route, Routes } from "react-router-dom";
import { getToken } from "./lib/api";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Scenarios from "./pages/Scenarios";
import ScenarioEditor from "./pages/ScenarioEditor";
import RunDetail from "./pages/RunDetail";
import History from "./pages/History";
import Compare from "./pages/Compare";
import Lab from "./pages/Lab";

function RequireAuth({ children }: { children: JSX.Element }) {
  return getToken() ? children : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<RequireAuth><Layout /></RequireAuth>}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/scenarios" element={<Scenarios />} />
        <Route path="/scenarios/:id/edit" element={<ScenarioEditor />} />
        <Route path="/scenarios/new" element={<ScenarioEditor />} />
        <Route path="/runs/:id" element={<RunDetail />} />
        <Route path="/history" element={<History />} />
        <Route path="/compare" element={<Compare />} />
        <Route path="/lab" element={<Lab />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
