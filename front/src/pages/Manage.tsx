import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useDialog } from "../components/Dialog";
import { Spinner, StatusBadge } from "../components/ui";
import TopNav from "../components/TopNav";

interface ManageApp {
  id: number;
  name: string;
  subdomain: string;
  status: "draft" | "live";
  folder: string | null;
  created_at: string | null;
  updated_at: string | null;
  last_execution: { status: string; stage: string; finished_at: string | null } | null;
  errors: number;
  executions: number;
}

function fmt(dt: string | null): string {
  if (!dt) return "—";
  const d = new Date(dt);
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function Manage() {
  const { user } = useAuth();
  const nav = useNavigate();
  const dlg = useDialog();
  const isAdmin = !!user?.is_admin;
  const canManage = !!(user?.is_admin || user?.is_dev);

  const [apps, setApps] = useState<ManageApp[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  async function load() {
    setApps(await api.get<ManageApp[]>("/api/manage/apps"));
    setLoading(false);
  }
  useEffect(() => {
    if (canManage) load();
    else setLoading(false);
  }, [canManage]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return apps;
    return apps.filter(
      (a) =>
        a.name.toLowerCase().includes(q) ||
        a.subdomain.toLowerCase().includes(q) ||
        (a.folder || "").toLowerCase().includes(q)
    );
  }, [apps, query]);

  const stats = useMemo(() => {
    const live = apps.filter((a) => a.status === "live").length;
    const withErrors = apps.filter((a) => a.errors > 0).length;
    return { total: apps.length, live, draft: apps.length - live, withErrors };
  }, [apps]);

  async function toggleStatus(a: ManageApp) {
    const next = a.status === "live" ? "draft" : "live";
    setBusy(a.id);
    try {
      await api.post(`/api/manage/apps/${a.id}/status`, { status: next });
      setApps((cur) => cur.map((x) => (x.id === a.id ? { ...x, status: next } : x)));
    } finally {
      setBusy(null);
    }
  }

  async function deleteApp(a: ManageApp) {
    const ok = await dlg.confirm({
      title: `Excluir "${a.name}"`,
      message: "Esta ação não pode ser desfeita. Versões, execuções e arquivos serão removidos.",
      confirmLabel: "Excluir",
      danger: true,
    });
    if (!ok) return;
    setBusy(a.id);
    try {
      await api.del(`/api/projects/${a.id}`);
      setApps((cur) => cur.filter((x) => x.id !== a.id));
    } finally {
      setBusy(null);
    }
  }

  function toggleSelect(id: number) {
    setSelected((prev) => {
      const n = new Set(prev);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  }

  async function bulkDelete() {
    if (selected.size === 0) return;
    const ok = await dlg.confirm({
      title: `Excluir ${selected.size} aplicação(ões)`,
      message: "Esta ação não pode ser desfeita. Tudo das aplicações selecionadas será removido.",
      confirmLabel: "Excluir selecionadas",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.post("/api/projects/bulk-delete", { ids: [...selected] });
      setApps((cur) => cur.filter((x) => !selected.has(x.id)));
      setSelected(new Set());
    } catch (e: any) {
      await dlg.confirm({
        title: "Não foi possível excluir",
        message: e?.message || "Erro ao excluir.",
        confirmLabel: "Entendi",
      });
    }
  }

  if (!canManage) {
    return (
      <div className="min-h-full">
        <TopNav />
        <main className="mx-auto max-w-3xl px-6 py-20 text-center">
          <h1 className="text-xl font-bold text-ink">Acesso restrito</h1>
          <p className="mt-2 text-sm text-ink2">
            Esta área é exclusiva para administradores e desenvolvedores.
          </p>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-full">
      <TopNav />
      <main className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-ink">Gerenciamento de automações</h1>
            <p className="text-sm text-ink2">
              Manutenção e saúde de todas as automações da organização.
            </p>
          </div>
          {isAdmin && selected.size > 0 && (
            <button
              onClick={bulkDelete}
              className="rounded-xl px-4 py-2 text-sm font-semibold text-white transition hover:brightness-105"
              style={{ background: "var(--err)" }}
            >
              Excluir selecionadas ({selected.size})
            </button>
          )}
        </div>

        {/* indicadores de saúde (skeleton enquanto carrega, sem "0" falso) */}
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {loading ? (
            [0, 1, 2, 3].map((i) => (
              <div key={i} className="card animate-pulse p-4">
                <div className="h-3 w-20 rounded" style={{ background: "var(--border-strong)" }} />
                <div className="mt-2 h-7 w-12 rounded" style={{ background: "var(--border-strong)" }} />
              </div>
            ))
          ) : (
            <>
              <StatCard label="Automações" value={stats.total} tone="brand" />
              <StatCard label="No ar" value={stats.live} tone="accent" />
              <StatCard label="Rascunho" value={stats.draft} tone="slate" />
              <StatCard label="Com erros" value={stats.withErrors} tone="red" />
            </>
          )}
        </div>

        <div className="mb-3 flex items-center justify-between gap-3">
          <input
            className="input max-w-xs"
            placeholder="Buscar por nome, link ou pasta…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <span className="text-xs text-ink3">{filtered.length} de {apps.length}</span>
        </div>

        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line bg-surface-2 text-left text-[11px] uppercase tracking-wide text-ink3">
                  {isAdmin && <th className="w-10 px-4 py-3"></th>}
                  <th className="px-4 py-3 font-semibold">Aplicação</th>
                  <th className="px-4 py-3 font-semibold">Pasta</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                  <th className="px-4 py-3 font-semibold">Última execução</th>
                  <th className="px-4 py-3 text-center font-semibold">Erros</th>
                  <th className="px-4 py-3 text-right font-semibold">Ações</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[color:var(--border)]">
                {loading ? (
                  <tr>
                    <td colSpan={isAdmin ? 7 : 6} className="px-4 py-16 text-center">
                      <Spinner className="mx-auto h-7 w-7 text-ink3" />
                    </td>
                  </tr>
                ) : filtered.length === 0 ? (
                  <tr>
                    <td colSpan={isAdmin ? 7 : 6} className="px-4 py-16 text-center text-sm text-ink3">
                      Nenhuma aplicação encontrada.
                    </td>
                  </tr>
                ) : (
                  filtered.map((a) => (
                    <tr key={a.id} className="transition hover:bg-surface-2">
                      {isAdmin && (
                        <td className="px-4 py-3">
                          <input
                            type="checkbox"
                            checked={selected.has(a.id)}
                            onChange={() => toggleSelect(a.id)}
                            className="h-4 w-4 accent-brand-600"
                          />
                        </td>
                      )}
                      <td className="px-4 py-3">
                        <button
                          onClick={() => nav(`/projects/${a.id}/assistente`)}
                          className="text-left font-semibold text-ink transition hover:text-accentv"
                        >
                          {a.name}
                        </button>
                        <a
                          href={`/app/${a.subdomain}`}
                          target="_blank"
                          rel="noreferrer"
                          className="block truncate font-mono text-[11px] text-brandv hover:underline"
                        >
                          /app/{a.subdomain}
                        </a>
                      </td>
                      <td className="px-4 py-3 text-ink2">{a.folder || "—"}</td>
                      <td className="px-4 py-3">
                        <StatusBadge status={a.status} />
                      </td>
                      <td className="px-4 py-3">
                        {a.last_execution ? (
                          <div className="flex items-center gap-2">
                            <StatusBadge status={a.last_execution.status} />
                            <span className="text-xs text-ink3">{fmt(a.last_execution.finished_at)}</span>
                          </div>
                        ) : (
                          <span className="text-xs text-ink3">sem execuções</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {a.errors > 0 ? (
                          <span
                            className="inline-flex min-w-[1.5rem] justify-center rounded-full px-2 py-0.5 text-xs font-semibold"
                            data-status="error"
                          >
                            {a.errors}
                          </span>
                        ) : (
                          <span className="text-xs text-ink3">0</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={() => toggleStatus(a)}
                            disabled={busy === a.id}
                            className={`rounded-md px-2.5 py-1 text-xs font-semibold transition disabled:opacity-50 ${
                              a.status === "live"
                                ? "border border-line text-ink2 hover:bg-surface-2"
                                : "text-white hover:brightness-105"
                            }`}
                            style={a.status === "live" ? undefined : { background: "var(--accent)" }}
                          >
                            {busy === a.id ? "…" : a.status === "live" ? "Tirar do ar" : "Publicar"}
                          </button>
                          <Link
                            to={`/projects/${a.id}/logs`}
                            className="rounded-md px-2 py-1 text-xs font-medium text-ink2 transition hover:text-accentv"
                          >
                            Logs
                          </Link>
                          <Link
                            to={`/projects/${a.id}/workflow`}
                            className="rounded-md px-2 py-1 text-xs font-medium text-ink2 transition hover:text-accentv"
                          >
                            Workflow
                          </Link>
                          <button
                            onClick={() => deleteApp(a)}
                            disabled={busy === a.id}
                            className="rounded-md px-2 py-1 text-xs font-medium text-err transition hover:underline disabled:opacity-50"
                          >
                            Excluir
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </main>
    </div>
  );
}

function StatCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "brand" | "accent" | "slate" | "red";
}) {
  const toneColor = {
    brand: "var(--brand)",
    accent: "var(--accent)",
    slate: "var(--text-2)",
    red: "var(--err)",
  }[tone];
  return (
    <div className="card p-4">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-ink3">{label}</div>
      <div className="mt-1 text-2xl font-extrabold" style={{ color: toneColor }}>{value}</div>
    </div>
  );
}
