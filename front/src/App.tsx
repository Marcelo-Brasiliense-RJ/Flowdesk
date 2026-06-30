import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { useAuth } from "./lib/auth";
import { Spinner } from "./components/ui";
import Login from "./pages/Login";
import Console from "./pages/Console";
import Dashboard from "./pages/Dashboard";
import Chat from "./pages/Chat";
import Editor from "./pages/Editor";
import Wizard from "./pages/Wizard";
import WorkflowMonitor from "./pages/WorkflowMonitor";
import Builds from "./pages/Builds";
import Logs from "./pages/Logs";
import Files from "./pages/Files";
import AccessControl from "./pages/AccessControl";
import ProjectSettings from "./pages/ProjectSettings";
import PublishedApp from "./pages/PublishedApp";
import Manage from "./pages/Manage";
import Admin from "./pages/Admin";
import Agents from "./pages/Agents";
import ProjectChat from "./pages/ProjectChat";
import type { ReactNode } from "react";

function Protected({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading)
    return (
      <div className="flex h-full items-center justify-center text-brand-700">
        <Spinner className="h-8 w-8" />
      </div>
    );
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

/** Modo avançado (editor/código): restrito a admin e dev. Usuário comum vai
 * para o Assistente do mesmo projeto. */
function ManagerOnly({ children, fallback }: { children: ReactNode; fallback: string }) {
  const { user, loading } = useAuth();
  if (loading)
    return (
      <div className="flex h-full items-center justify-center text-brand-700">
        <Spinner className="h-8 w-8" />
      </div>
    );
  if (!user) return <Navigate to="/login" replace />;
  if (!user.is_admin && !user.is_dev) return <Navigate to={fallback} replace />;
  return <>{children}</>;
}

function EditorGate() {
  const { id } = useParams();
  return (
    <ManagerOnly fallback={`/projects/${id}/assistente`}>
      <Editor />
    </ManagerOnly>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      {/* Published app — independent experience, no console auth */}
      <Route path="/app/:subdomain" element={<PublishedApp />} />

      <Route path="/" element={<Protected><Console /></Protected>} />
      <Route path="/dashboard" element={<Protected><Dashboard /></Protected>} />
      <Route path="/manage" element={<Protected><Manage /></Protected>} />
      <Route path="/admin" element={<Protected><Admin /></Protected>} />
      <Route path="/agents" element={<Protected><Agents /></Protected>} />
      <Route path="/chat" element={<Protected><Chat /></Protected>} />
      <Route path="/projects/:id/assistente" element={<Protected><Wizard /></Protected>} />
      <Route path="/projects/:id/chat" element={<Protected><ProjectChat /></Protected>} />
      <Route path="/projects/:id/editor" element={<Protected><EditorGate /></Protected>} />
      <Route path="/projects/:id/workflow" element={<Protected><WorkflowMonitor /></Protected>} />
      <Route path="/projects/:id/builds" element={<Protected><Builds /></Protected>} />
      <Route path="/projects/:id/logs" element={<Protected><Logs /></Protected>} />
      <Route path="/projects/:id/files" element={<Protected><Files /></Protected>} />
      <Route path="/projects/:id/access" element={<Protected><AccessControl /></Protected>} />
      <Route path="/projects/:id/settings/*" element={<Protected><ProjectSettings /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
