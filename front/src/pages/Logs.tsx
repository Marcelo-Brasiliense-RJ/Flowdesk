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
        <h1 className="mb-1.5 text-xl font-extrabold text-ink">Logs de execução</h1>
        <p className="mb-4 text-sm text-ink2">{total} execuções</p>

        <div className="mb-4 grid grid-cols-2 gap-2.5 sm:grid-cols-5">
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
            <div key={e.id} className="border-b border-line last:border-0">
              <button
                onClick={() => setExpanded(expanded === e.id ? null : e.id)}
                className="flex w-full items-center gap-3.5 px-[18px] py-3 text-left text-sm transition hover:bg-surface-2"
              >
                <span className="w-[150px] shrink-0 truncate font-semibold text-ink">
                  {e.stage_name}
                </span>
                <span className="w-[54px] shrink-0 text-xs text-ink3">{e.stage_type}</span>
                <StatusBadge status={e.status} />
                <span className="shrink-0 font-mono text-[11px] text-ink3">
                  {e.id.slice(0, 8)}
                </span>
                <span className="ml-auto text-xs text-ink3">
                  {new Date(e.started_at).toLocaleString("pt-BR")}
                </span>
                <span className="shrink-0 text-[11px] text-ink3">{expanded === e.id ? "▲" : "▼"}</span>
              </button>
              {expanded === e.id && (
                <div className="space-y-2 bg-surface-2 px-[18px] pb-3.5 pt-1">
                  <LogBlock title="stdout" color="text-emerald-200" body={e.stdout} />
                  {e.stderr && (
                    <LogBlock title="stderr" color="text-red-300" body={e.stderr} />
                  )}
                  <div>
                    <div className="mb-1 text-xs font-semibold uppercase text-ink3">
                      output
                    </div>
                    <pre className="overflow-auto rounded bg-surface p-2 text-xs">
                      {JSON.stringify(e.output_data, null, 2)}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          ))}
          {items.length === 0 && (
            <div className="px-4 py-8 text-center text-ink3">
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
          <span className="text-ink2">
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
      <span className="mb-1 block text-xs font-medium text-ink2">{label}</span>
      {children}
    </label>
  );
}

function LogBlock({ title, color, body }: { title: string; color: string; body: string }) {
  return (
    <div>
      <div className="mb-1 text-xs font-semibold uppercase text-ink3">{title}</div>
      <pre className={`max-h-60 overflow-auto rounded p-2 text-xs ${color}`} style={{ background: "#0b1f33" }}>
        {body || "(vazio)"}
      </pre>
    </div>
  );
}
