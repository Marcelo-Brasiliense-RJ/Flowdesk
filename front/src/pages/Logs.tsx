import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Execution, Stage } from "../lib/types";
import { StatusBadge } from "../components/ui";
import ProjectLayout, { useProject } from "../components/ProjectLayout";

export default function Logs() {
  const { id, project } = useProject();
  const [stages, setStages] = useState<Stage[]>([]);
  const [items, setItems] = useState<Execution[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [filters, setFilters] = useState({
    stage_id: "",
    status: "",
    execution_id: "",
    date_from: "",
    date_to: "",
  });

  useEffect(() => {
    api.get<Stage[]>(`/api/projects/${id}/stages`).then(setStages);
  }, [id]);

  async function load() {
    const q = new URLSearchParams({ page: String(page), page_size: "10" });
    Object.entries(filters).forEach(([k, v]) => v && q.set(k, v));
    const res = await api.get<{ items: Execution[]; total: number }>(
      `/api/projects/${id}/executions?${q.toString()}`
    );
    setItems(res.items);
    setTotal(res.total);
  }
  useEffect(() => {
    load();
  }, [id, page, filters]);

  const totalPages = Math.max(1, Math.ceil(total / 10));

  return (
    <ProjectLayout project={project}>
      <div className="p-6">
        <h1 className="mb-1 text-xl font-bold text-brand-900">Logs de execução</h1>
        <p className="mb-4 text-sm text-slate-500">{total} execução(ões)</p>

        <div className="card mb-4 grid grid-cols-2 gap-3 p-4 sm:grid-cols-5">
          <Field label="Etapa">
            <select
              className="input"
              value={filters.stage_id}
              onChange={(e) => setFilters((f) => ({ ...f, stage_id: e.target.value }))}
            >
              <option value="">Todas</option>
              {stages.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Status">
            <select
              className="input"
              value={filters.status}
              onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
            >
              <option value="">Todos</option>
              <option value="success">Sucesso</option>
              <option value="error">Erro</option>
              <option value="running">Em andamento</option>
              <option value="queued">Na fila</option>
            </select>
          </Field>
          <Field label="De">
            <input
              type="date"
              className="input"
              value={filters.date_from}
              onChange={(e) => setFilters((f) => ({ ...f, date_from: e.target.value }))}
            />
          </Field>
          <Field label="Até">
            <input
              type="date"
              className="input"
              value={filters.date_to}
              onChange={(e) => setFilters((f) => ({ ...f, date_to: e.target.value }))}
            />
          </Field>
          <Field label="ID de Execução">
            <input
              className="input"
              placeholder="hash..."
              value={filters.execution_id}
              onChange={(e) =>
                setFilters((f) => ({ ...f, execution_id: e.target.value }))
              }
            />
          </Field>
        </div>

        <div className="card overflow-hidden">
          {items.map((e) => (
            <div key={e.id} className="border-b border-slate-100 last:border-0">
              <button
                onClick={() => setExpanded(expanded === e.id ? null : e.id)}
                className="flex w-full items-center gap-4 px-4 py-2.5 text-left text-sm hover:bg-slate-50"
              >
                <span className="w-40 truncate font-medium text-brand-900">
                  {e.stage_name}
                </span>
                <span className="w-16 text-slate-400">{e.stage_type}</span>
                <StatusBadge status={e.status} />
                <span className="font-mono text-xs text-slate-400">
                  {e.id.slice(0, 8)}
                </span>
                <span className="ml-auto text-xs text-slate-400">
                  {new Date(e.started_at).toLocaleString("pt-BR")}
                </span>
                <span className="text-slate-300">{expanded === e.id ? "▲" : "▼"}</span>
              </button>
              {expanded === e.id && (
                <div className="space-y-2 bg-slate-50 px-4 py-3">
                  <LogBlock title="stdout" color="text-emerald-200" body={e.stdout} />
                  {e.stderr && (
                    <LogBlock title="stderr" color="text-red-300" body={e.stderr} />
                  )}
                  <div>
                    <div className="mb-1 text-xs font-semibold uppercase text-slate-400">
                      output
                    </div>
                    <pre className="overflow-auto rounded bg-white p-2 text-xs">
                      {JSON.stringify(e.output_data, null, 2)}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          ))}
          {items.length === 0 && (
            <div className="px-4 py-8 text-center text-slate-400">
              Nenhuma execução encontrada.
            </div>
          )}
        </div>

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
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
            className="btn-outline py-1 disabled:opacity-40"
          >
            Próxima
          </button>
        </div>
      </div>
    </ProjectLayout>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-500">{label}</span>
      {children}
    </label>
  );
}

function LogBlock({ title, color, body }: { title: string; color: string; body: string }) {
  return (
    <div>
      <div className="mb-1 text-xs font-semibold uppercase text-slate-400">{title}</div>
      <pre className={`max-h-60 overflow-auto rounded bg-slate-900 p-2 text-xs ${color}`}>
        {body || "(vazio)"}
      </pre>
    </div>
  );
}
