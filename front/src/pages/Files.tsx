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
          <h1 className="text-xl font-bold text-brand-900">Arquivos</h1>
          <div className="flex gap-2">
            <button onClick={newFolder} className="btn-outline py-1.5 text-sm">
              + Novo
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
          <button onClick={() => setPath("")} className="text-brand-600 hover:underline">
            raiz
          </button>
          {crumbs.map((c, i) => (
            <span key={i} className="flex items-center gap-2">
              <span className="text-slate-300">/</span>
              <button
                onClick={() => setPath(crumbs.slice(0, i + 1).join("/"))}
                className="text-brand-600 hover:underline"
              >
                {c}
              </button>
            </span>
          ))}
          <input
            className="input ml-auto max-w-xs"
            placeholder="Buscar nesta pasta..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="card overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-2">
                  <input type="checkbox" disabled />
                </th>
                <th className="px-4 py-2">Nome</th>
                <th className="px-4 py-2">Tamanho</th>
                <th className="px-4 py-2">Modificado</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {paged.map((e) => (
                <tr key={e.path} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-4 py-2">
                    <input type="checkbox" />
                  </td>
                  <td className="px-4 py-2">
                    {e.is_dir ? (
                      <button
                        onClick={() => setPath(e.path)}
                        className="font-medium text-brand-700 hover:underline"
                      >
                        📁 {e.name}
                      </button>
                    ) : (
                      <span className="text-slate-700">📄 {e.name}</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-slate-400">
                    {e.is_dir ? "—" : formatSize(e.size)}
                  </td>
                  <td className="px-4 py-2 text-slate-400">
                    {new Date(e.modified_at).toLocaleString("pt-BR")}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <div className="flex justify-end gap-2 text-xs">
                      <button onClick={() => rename(e)} className="text-slate-500 hover:text-brand-600">
                        Renomear
                      </button>
                      {!e.is_dir && (
                        <button onClick={() => download(e)} className="text-slate-500 hover:text-brand-600">
                          Baixar
                        </button>
                      )}
                      <button onClick={() => remove(e)} className="text-red-500 hover:text-red-700">
                        Excluir
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-slate-400">
                    Pasta vazia.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </ProjectLayout>
  );
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
