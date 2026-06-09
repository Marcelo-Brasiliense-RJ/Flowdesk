import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { api } from "../lib/api";
import type { Project } from "../lib/types";
import { Logo, StatusBadge } from "./ui";

const NAV = [
  ["editor", "Editor", "✎"],
  ["workflow", "Workflow", "⌗"],
  ["builds", "Versões", "⎘"],
  ["logs", "Logs", "≣"],
  ["files", "Arquivos", "🗂"],
  ["access", "Controle de Acesso", "🔒"],
  ["settings", "Configurações", "⚙"],
];

export function useProject() {
  const { id } = useParams();
  const [project, setProject] = useState<Project | null>(null);
  useEffect(() => {
    api.get<Project>(`/api/projects/${id}`).then(setProject);
  }, [id]);
  return { id: Number(id), project, setProject };
}

export default function ProjectLayout({
  children,
  project,
}: {
  children: ReactNode;
  project: Project | null;
}) {
  const { id } = useParams();
  const loc = useLocation();
  const active = loc.pathname.split("/")[3] || "editor";

  return (
    <div className="flex h-full">
      <aside className="flex w-56 flex-col border-r border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-4 py-3">
          <Link to="/">
            <Logo />
          </Link>
        </div>
        <div className="px-4 py-3">
          <div className="truncate font-semibold text-brand-900">
            {project?.name || "..."}
          </div>
          {project && <StatusBadge status={project.status} />}
        </div>
        <nav className="flex-1 space-y-0.5 px-2">
          {NAV.map(([key, label, icon]) => (
            <Link
              key={key}
              to={`/projects/${id}/${key}`}
              className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
                active === key
                  ? "bg-brand-50 text-brand-700 shadow-sm"
                  : "text-slate-600 hover:bg-slate-50 hover:text-brand-700"
              }`}
            >
              <span className="w-4 text-center text-xs opacity-70">{icon}</span>
              {label}
            </Link>
          ))}
        </nav>
        <div className="border-t border-slate-200 p-3">
          <Link to="/" className="btn-outline w-full py-1.5 text-sm">
            ← Console
          </Link>
        </div>
      </aside>
      <main className="flex-1 overflow-auto bg-slate-50">{children}</main>
    </div>
  );
}
