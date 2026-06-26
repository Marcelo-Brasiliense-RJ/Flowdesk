import { useEffect, useRef, useState } from "react";
import { api, getToken } from "../lib/api";
import ProjectLayout, { useProject } from "../components/ProjectLayout";

interface Entry {
  name: string;
  is_dir: boolean;
  size: number;
  modified_at: string;
  path: string;
}

export default function Files() {
  const { id, project } = useProject();
  const [path, setPath] = useState("");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const fileInput = useRef<HTMLInputElement>(null);
  const pageSize = 20;

  async function load() {
    const res = await api.get<{ entries: Entry[] }>(
      `/api/projects/${id}/fs?path=${encodeURIComponent(path)}`
    );
    setEntries(res.entries);
    setPage(1);
  }
  useEffect(() => {
    load();
  }, [id, path]);

  async function upload(file: File) {
    const fd = new FormData();
    fd.append("path", path);
    fd.append("file", file);
    await api.postForm(`/api/projects/${id}/fs/upload`, fd);
    load();
  }

  async function newFolder() {
    const name = prompt("Nome da pasta:");
    if (!name) return;
    const fd = new FormData();
    fd.append("path", path ? `${path}/${name}` : name);
    await api.postForm(`/api/projects/${id}/fs/folder`, fd);
    load();
  }

  async function rename(entry: Entry) {
    const name = prompt("Novo nome:", entry.name);
    if (!name) return;
    const fd = new FormData();
    fd.append("path", entry.path);
    fd.append("new_name", name);
    await api.postForm(`/api/projects/${id}/fs/rename`, fd);
    load();
  }

  async function remove(entry: Entry) {
    if (!confirm(`Excluir ${entry.name}?`)) return;
    await api.del(`/api/projects/${id}/fs?path=${encodeURIComponent(entry.path)}`);
    load();
  }

  function download(entry: Entry) {
    const url = `/api/projects/${id}/fs/download?path=${encodeURIComponent(
      entry.path
    )}`;
    fetch(url, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then((r) => r.blob())
      .then((blob) => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = entry.name;
        a.click();
      });
  }

  const crumbs = path ? path.split("/") : [];
  const filtered = entries.filter((e) =>
    e.name.toLowerCase().includes(search.toLowerCase())
  );
  const paged = filtered.slice((page - 1) * pageSize, page * pageSize);

  return (
    <ProjectLayout project={project}>
      <div className="p-6">
        <div className="mb-4 flex items-center justify-between">
          <h1 className="text-xl font-bold text-ink">Arquivos</h1>
          <div className="flex gap-2">
            <button onClick={newFolder} className="btn-outline py-1.5 text-sm">
              + Nova pasta
            </button>
            <button
              onClick={() => fileInput.current?.click()}
              className="btn-primary py-1.5 text-sm"
            >
              Enviar
            </button>
            <input
              ref={fileInput}
              type="file"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
            />
          </div>
        </div>

        <div className="mb-3 flex items-center gap-2 text-sm">
          <button onClick={() => setPath("")} className="text-brandv hover:underline">
            raiz
          </button>
          {crumbs.map((c, i) => (
            <span key={i} className="flex items-center gap-2">
              <span className="text-ink3">/</span>
              <button
                onClick={() => setPath(crumbs.slice(0, i + 1).join("/"))}
                className="text-brandv hover:underline"
              >
                {c}
              </button>
            </span>
          ))}
          <input
            className="input ml-auto max-w-xs"
            placeholder="Buscar nesta pasta..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </div>

        <div className="card overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="bg-surface-2 text-xs uppercase text-ink3">
              <tr>
                <th className="px-4 py-2">
                  <input type="checkbox" disabled />
                </th>
                <th className="px-4 py-2 font-bold tracking-wide">Nome</th>
                <th className="px-4 py-2 font-bold tracking-wide">Tamanho</th>
                <th className="px-4 py-2 font-bold tracking-wide">Modificado</th>
                <th className="px-4 py-2 text-right font-bold tracking-wide">Ações</th>
              </tr>
            </thead>
            <tbody>
              {paged.map((e) => (
                <tr key={e.path} className="border-t border-line hover:bg-surface-2">
                  <td className="px-4 py-2">
                    <input type="checkbox" />
                  </td>
                  <td className="px-4 py-2">
                    {e.is_dir ? (
                      <button
                        onClick={() => setPath(e.path)}
                        className="font-medium text-brandv hover:underline"
                      >
                        📁 {e.name}
                      </button>
                    ) : (
                      <span className="text-ink">📄 {e.name}</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-ink3">
                    {e.is_dir ? "—" : formatSize(e.size)}
                  </td>
                  <td className="px-4 py-2 text-ink3">
                    {new Date(e.modified_at).toLocaleString("pt-BR")}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <div className="flex justify-end gap-2 text-xs">
                      <button onClick={() => rename(e)} className="text-ink2 hover:text-accentv">
                        Renomear
                      </button>
                      {!e.is_dir && (
                        <button onClick={() => download(e)} className="text-ink2 hover:text-accentv">
                          Baixar
                        </button>
                      )}
                      <button onClick={() => remove(e)} className="text-err hover:underline">
                        Excluir
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-ink3">
                    Pasta vazia.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {filtered.length > pageSize && (
          <div className="mt-3 flex items-center justify-end gap-3 text-sm text-ink3">
            <span>
              {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, filtered.length)} de {filtered.length}
            </span>
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="btn-outline py-1 text-sm disabled:opacity-50"
            >
              Anterior
            </button>
            <button
              onClick={() => setPage((p) => (p * pageSize < filtered.length ? p + 1 : p))}
              disabled={page * pageSize >= filtered.length}
              className="btn-outline py-1 text-sm disabled:opacity-50"
            >
              Próxima
            </button>
          </div>
        )}
      </div>
    </ProjectLayout>
  );
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
