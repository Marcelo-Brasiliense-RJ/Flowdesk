import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Build } from "../lib/types";
import { StatusBadge } from "../components/ui";
import ProjectLayout, { useProject } from "../components/ProjectLayout";

export default function Builds() {
  const { id, project } = useProject();
  const [builds, setBuilds] = useState<Build[]>([]);
  const [page, setPage] = useState(1);
  const [menu, setMenu] = useState<number | null>(null);
  const pageSize = 10;

  async function load() {
    setBuilds(await api.get<Build[]>(`/api/projects/${id}/builds`));
  }
  useEffect(() => {
    load();
  }, [id]);

  async function activate(buildId: number) {
    await api.post(`/api/projects/${id}/builds/${buildId}/activate`);
    setMenu(null);
    load();
  }

  const paged = builds.slice((page - 1) * pageSize, page * pageSize);
  const totalPages = Math.max(1, Math.ceil(builds.length / pageSize));

  return (
    <ProjectLayout project={project}>
      <div className="p-6">
        <h1 className="mb-1 text-xl font-bold text-brand-900">Histórico de versões</h1>
        <p className="mb-4 text-sm text-slate-500">
          Cada publicação gera uma versão imutável. Apenas uma fica "No ar".
        </p>
        <div className="card overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-2">ID</th>
                <th className="px-4 py-2">Data/Hora</th>
                <th className="px-4 py-2">Framework</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {paged.map((b) => (
                <tr key={b.id} className="border-t border-slate-100">
                  <td className="px-4 py-2 font-mono text-brand-600">{b.hash}</td>
                  <td className="px-4 py-2 text-slate-500">
                    {new Date(b.created_at).toLocaleString("pt-BR")}
                  </td>
                  <td className="px-4 py-2 text-slate-500">{b.framework_version}</td>
                  <td className="px-4 py-2">
                    <StatusBadge status={b.status} />
                  </td>
                  <td className="relative px-4 py-2 text-right">
                    <button
                      onClick={() => setMenu(menu === b.id ? null : b.id)}
                      className="rounded px-2 text-slate-400 hover:bg-slate-100"
                    >
                      ⋮
                    </button>
                    {menu === b.id && (
                      <div className="absolute right-4 z-10 mt-1 w-48 rounded-lg border border-slate-200 bg-white py-1 text-left shadow-lg">
                        <MenuItem label="Inspecionar versão" />
                        <MenuItem label="Ver logs da aplicação" />
                        <MenuItem label="Baixar arquivos" />
                        {b.status !== "live" && (
                          <button
                            onClick={() => activate(b.id)}
                            className="block w-full px-4 py-1.5 text-left text-sm text-emerald-600 hover:bg-slate-50"
                          >
                            Tornar "No ar"
                          </button>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {builds.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-slate-400">
                    Nenhuma versão publicada ainda.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {totalPages > 1 && (
          <div className="mt-3 flex items-center justify-end gap-2 text-sm">
            <button
              disabled={page === 1}
              onClick={() => setPage((p) => p - 1)}
              className="btn-outline py-1 disabled:opacity-40"
            >
              Anterior
            </button>
            <span className="text-slate-500">
              {page} / {totalPages}
            </span>
            <button
              disabled={page === totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="btn-outline py-1 disabled:opacity-40"
            >
              Próxima
            </button>
          </div>
        )}
      </div>
    </ProjectLayout>
  );
}

function MenuItem({ label }: { label: string }) {
  return (
    <button className="block w-full px-4 py-1.5 text-left text-sm text-slate-600 hover:bg-slate-50">
      {label}
    </button>
  );
}
