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

  const [restoreMsg, setRestoreMsg] = useState("");
  async function restore(b: Build) {
    setMenu(null);
    if (!confirm(`Restaurar o código para a versão ${b.hash}? Os arquivos atuais serão sobrescritos.`)) return;
    try {
      const r = await api.post<{ restaurados: number }>(
        `/api/projects/${id}/builds/${b.id}/restore`
      );
      setRestoreMsg(`Código restaurado para a versão ${b.hash} (${r.restaurados} arquivo(s)).`);
    } catch (e: any) {
      setRestoreMsg(e?.message || "Não foi possível restaurar esta versão.");
    }
    setTimeout(() => setRestoreMsg(""), 6000);
  }

  const paged = builds.slice((page - 1) * pageSize, page * pageSize);
  const totalPages = Math.max(1, Math.ceil(builds.length / pageSize));

  return (
    <ProjectLayout project={project}>
      <div className="p-6">
        <h1 className="mb-1.5 text-xl font-extrabold tracking-tight text-ink">Histórico de versões</h1>
        <p className="mb-4 text-sm text-ink2">
          Cada publicação gera uma versão imutável. Apenas uma fica "No ar".
        </p>
        {restoreMsg && (
          <div className="mb-3 rounded-lg border border-line px-3 py-2 text-sm text-accentv" style={{ background: "var(--accent-soft)" }}>
            {restoreMsg}
          </div>
        )}
        <div className="card overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="bg-surface-2 text-[11px] font-bold uppercase tracking-wide text-ink3">
              <tr>
                <th className="px-[18px] py-3 font-bold">ID</th>
                <th className="px-[18px] py-3 font-bold">Data/Hora</th>
                <th className="px-[18px] py-3 font-bold">Framework</th>
                <th className="px-[18px] py-3 font-bold">Status</th>
                <th className="px-[18px] py-3"></th>
              </tr>
            </thead>
            <tbody>
              {paged.map((b) => (
                <tr key={b.id} className="border-t border-line">
                  <td className="px-[18px] py-3 font-mono text-[12.5px] text-brandv">{b.hash}</td>
                  <td className="px-[18px] py-3 text-ink2">
                    {new Date(b.created_at).toLocaleString("pt-BR")}
                  </td>
                  <td className="px-[18px] py-3 text-ink2">{b.framework_version}</td>
                  <td className="px-[18px] py-3">
                    <StatusBadge status={b.status} />
                  </td>
                  <td className="relative px-[18px] py-3 text-right">
                    <button
                      onClick={() => setMenu(menu === b.id ? null : b.id)}
                      className="rounded-md px-2 text-lg leading-none text-ink3 transition hover:bg-surface-2 hover:text-ink2"
                    >
                      ⋮
                    </button>
                    {menu === b.id && (
                      <div className="absolute right-4 z-10 mt-1 w-48 overflow-hidden rounded-xl border border-line bg-surface py-1 text-left shadow-token-lg">
                        <button
                          onClick={() => restore(b)}
                          className="block w-full px-4 py-2 text-left text-sm text-brandv transition hover:bg-surface-2"
                        >
                          Restaurar código desta versão
                        </button>
                        {b.status !== "live" && (
                          <button
                            onClick={() => activate(b.id)}
                            className="block w-full px-4 py-2 text-left text-sm text-ok transition hover:bg-surface-2"
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
                  <td colSpan={5} className="px-[18px] py-10 text-center text-ink3">
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
            <span className="text-ink2">
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

