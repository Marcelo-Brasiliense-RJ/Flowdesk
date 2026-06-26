import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { StatusBadge, Spinner } from "../components/ui";
import TopNav from "../components/TopNav";

interface DashData {
  kpis: {
    projects: number; live: number; draft: number; executions: number;
    success: number; error: number; running: number; success_rate: number; avg_seconds: number;
  };
  timeline: { date: string; success: number; error: number; total: number }[];
  by_project: { id: number; name: string; status: string; executions: number; errors: number; last_run: string | null }[];
  recent_errors: { id: string; project_id: number; project_name: string; stage_name: string; started_at: string; stderr: string }[];
  recent_executions: { id: string; project_name: string; stage_name: string; stage_type: string; status: string; started_at: string }[];
}

function last7Days(timeline: DashData["timeline"]) {
  const byDate = Object.fromEntries(timeline.map((t) => [t.date, t]));
  const days: { date: string; label: string; success: number; error: number; total: number }[] = [];
  const now = new Date();
  for (let i = 6; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(now.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    const t = byDate[key] || { success: 0, error: 0, total: 0 };
    days.push({
      date: key,
      label: d.toLocaleDateString("pt-BR", { weekday: "short" }).replace(".", ""),
      success: t.success,
      error: t.error,
      total: t.total,
    });
  }
  return days;
}

export default function Dashboard() {
  const [data, setData] = useState<DashData | null>(null);

  useEffect(() => {
    api.get<DashData>("/api/dashboard").then(setData);
  }, []);

  if (!data)
    return (
      <div className="min-h-full">
        <TopNav />
        <div className="flex items-center justify-center py-32 text-ink3">
          <Spinner className="h-8 w-8" />
        </div>
      </div>
    );

  const k = data.kpis;
  const days = last7Days(data.timeline);
  const maxDay = Math.max(1, ...days.map((d) => d.total));

  return (
    <div className="min-h-full">
      <TopNav />
      <main className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-extrabold tracking-tight text-ink">Dashboard</h1>
          <p className="text-sm text-ink2">
            Visão operacional de todas as automações da organização
          </p>
        </div>

        {/* KPI hero */}
        <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <KpiHero
            label="Taxa de sucesso"
            value={`${k.success_rate}%`}
            sub={`${k.success} de ${k.success + k.error} execuções`}
          />
          <Kpi label="Projetos" value={k.projects} sub={`${k.live} no ar · ${k.draft} rascunho`} />
          <Kpi label="Execuções" value={k.executions} sub={`${k.running} em andamento`} />
          <Kpi label="Tempo médio" value={`${k.avg_seconds}s`} sub="por execução finalizada" />
        </div>

        <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
          {/* timeline chart */}
          <div className="card p-5 lg:col-span-2">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-bold text-ink">Execuções (7 dias)</h2>
              <div className="flex items-center gap-3 text-xs text-ink2">
                <span className="flex items-center gap-1">
                  <span className="h-2 w-2 rounded-full" style={{ background: "var(--accent)" }} /> sucesso
                </span>
                <span className="flex items-center gap-1">
                  <span className="h-2 w-2 rounded-full" style={{ background: "var(--err)" }} /> erro
                </span>
              </div>
            </div>
            <div className="flex h-40 items-end gap-3">
              {days.map((d) => (
                <div key={d.date} className="flex flex-1 flex-col items-center gap-1">
                  <div className="flex h-32 w-full max-w-[40px] flex-col justify-end gap-0.5">
                    {d.error > 0 && (
                      <div
                        className="w-full rounded-t"
                        style={{ height: `${(d.error / maxDay) * 100}%`, background: "var(--err)" }}
                        title={`${d.error} erro(s)`}
                      />
                    )}
                    <div
                      className="w-full rounded-t"
                      style={{ height: `${(d.success / maxDay) * 100}%`, background: "var(--accent)" }}
                      title={`${d.success} sucesso(s)`}
                    />
                  </div>
                  <span className="text-[10px] text-ink3">{d.label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* status distribution */}
          <div className="card p-5">
            <h2 className="mb-4 font-bold text-ink">Distribuição</h2>
            <StatRow color="var(--accent)" label="Sucesso" value={k.success} total={k.executions} />
            <StatRow color="var(--err)" label="Erro" value={k.error} total={k.executions} />
            <StatRow color="var(--warn2)" label="Em andamento" value={k.running} total={k.executions} />
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* per-project health */}
          <div className="card overflow-hidden">
            <h2 className="border-b border-line px-5 py-3 font-bold text-ink">
              Saúde por projeto
            </h2>
            <table className="w-full text-left text-sm">
              <thead className="bg-surface-2 text-xs uppercase text-ink3">
                <tr>
                  <th className="px-4 py-2">Projeto</th>
                  <th className="px-4 py-2">Status</th>
                  <th className="px-4 py-2 text-right">Exec.</th>
                  <th className="px-4 py-2 text-right">Erros</th>
                </tr>
              </thead>
              <tbody>
                {data.by_project.map((p) => (
                  <tr key={p.id} className="border-t border-line hover:bg-surface-2">
                    <td className="px-4 py-2">
                      <Link to={`/projects/${p.id}/logs`} className="font-medium text-brandv hover:underline">
                        {p.name}
                      </Link>
                    </td>
                    <td className="px-4 py-2"><StatusBadge status={p.status} /></td>
                    <td className="px-4 py-2 text-right text-ink2">{p.executions}</td>
                    <td className={`px-4 py-2 text-right font-medium ${p.errors ? "text-err" : "text-ink3"}`}>
                      {p.errors}
                    </td>
                  </tr>
                ))}
                {data.by_project.length === 0 && (
                  <tr><td colSpan={4} className="px-4 py-6 text-center text-ink3">Nenhum projeto.</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {/* recent errors */}
          <div className="card overflow-hidden">
            <h2 className="border-b border-line px-5 py-3 font-bold text-ink">
              Erros recentes
            </h2>
            <div className="divide-y divide-[color:var(--border)]">
              {data.recent_errors.map((e) => (
                <Link
                  key={e.id}
                  to={`/projects/${e.project_id}/logs`}
                  className="block px-5 py-3 transition hover:bg-surface-2"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-ink">
                      {e.project_name} · {e.stage_name}
                    </span>
                    <span className="text-xs text-ink3">
                      {new Date(e.started_at).toLocaleString("pt-BR")}
                    </span>
                  </div>
                  <pre className="mt-1 truncate font-mono text-xs text-err">{e.stderr || "erro"}</pre>
                </Link>
              ))}
              {data.recent_errors.length === 0 && (
                <div className="px-5 py-8 text-center text-sm text-ink3">
                  Nenhum erro recente. Tudo rodando bem.
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

function KpiHero({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div
      className="rounded-2xl p-5 text-white"
      style={{ background: "var(--kpi-grad)", boxShadow: "var(--shadow)" }}
    >
      <div className="text-xs font-semibold uppercase tracking-wide text-white/75">{label}</div>
      <div className="mt-1 text-3xl font-extrabold">{value}</div>
      <div className="mt-1 text-xs text-white/75">{sub}</div>
    </div>
  );
}

function Kpi({ label, value, sub }: { label: string; value: number | string; sub: string }) {
  return (
    <div className="card p-5">
      <div className="text-xs font-semibold uppercase tracking-wide text-ink3">{label}</div>
      <div className="mt-1 text-3xl font-extrabold text-ink">{value}</div>
      <div className="mt-1 text-xs text-ink2">{sub}</div>
    </div>
  );
}

function StatRow({ color, label, value, total }: { color: string; label: string; value: number; total: number }) {
  const pct = total ? Math.round((value / total) * 100) : 0;
  return (
    <div className="mb-3 last:mb-0">
      <div className="mb-1 flex items-center justify-between text-sm">
        <span className="text-ink2">{label}</span>
        <span className="font-semibold text-ink">{value} <span className="text-xs text-ink3">({pct}%)</span></span>
      </div>
      <div className="h-2 overflow-hidden rounded-full" style={{ background: "var(--border)" }}>
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}
