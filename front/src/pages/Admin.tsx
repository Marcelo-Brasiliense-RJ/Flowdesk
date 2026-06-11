import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Spinner, StatusBadge } from "../components/ui";
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

interface AdminData {
  users: { total: number; active: number; active_emails: string[] };
  chat: {
    messages: number;
    prompts: number;
    recent_prompts: { id: number; project_id: number; project_name: string; content: string; created_at: string | null }[];
  };
  system: {
    available: boolean;
    cpu_percent?: number;
    ram_percent?: number; ram_used_gb?: number; ram_total_gb?: number;
    disk_percent?: number; disk_used_gb?: number; disk_total_gb?: number;
  };
  requests: {
    total: number; last_hour: number; last_minute: number;
    by_method: Record<string, number>; uptime_seconds: number;
  };
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

function fmtUptime(s: number): string {
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.round(s / 60)} min`;
  const h = Math.floor(s / 3600);
  const m = Math.round((s % 3600) / 60);
  return m ? `${h}h ${m}min` : `${h}h`;
}

export default function Admin() {
  const { user } = useAuth();
  const isAdmin = !!user?.is_admin;
  const [dash, setDash] = useState<DashData | null>(null);
  const [adm, setAdm] = useState<AdminData | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    try {
      const [d, a] = await Promise.all([
        api.get<DashData>("/api/dashboard"),
        api.get<AdminData>("/api/admin/overview"),
      ]);
      setDash(d);
      setAdm(a);
    } catch (e: any) {
      setErr(e?.message || "Erro ao carregar.");
    }
  }

  useEffect(() => {
    if (!isAdmin) return;
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin]);

  if (!isAdmin) {
    return (
      <div className="min-h-full">
        <TopNav />
        <main className="mx-auto max-w-3xl px-6 py-20 text-center">
          <h1 className="text-xl font-bold text-brand-900">Acesso restrito</h1>
          <p className="mt-2 text-sm text-slate-500">
            O painel de controle é exclusivo para administradores.
          </p>
        </main>
      </div>
    );
  }

  if (err) {
    return (
      <div className="min-h-full">
        <TopNav />
        <main className="mx-auto max-w-3xl px-6 py-20 text-center">
          <h1 className="text-xl font-bold text-brand-900">Não foi possível carregar</h1>
          <p className="mt-2 text-sm text-slate-500">{err}</p>
        </main>
      </div>
    );
  }

  if (!dash || !adm)
    return (
      <div className="min-h-full">
        <TopNav />
        <div className="flex items-center justify-center py-32 text-brand-600">
          <Spinner className="h-8 w-8" />
        </div>
      </div>
    );

  const k = dash.kpis;
  const days = last7Days(dash.timeline);
  const sys = adm.system;

  return (
    <div className="min-h-full bg-slate-50">
      <TopNav />
      <main className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-brand-900">Painel de controle</h1>
            <p className="text-sm text-slate-500">
              Visão geral da plataforma. Atualiza a cada 15 segundos.
            </p>
          </div>
          <span className="text-xs text-slate-400">
            Sistema no ar há {fmtUptime(adm.requests.uptime_seconds)}
          </span>
        </div>

        {/* KPIs principais */}
        <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <KpiHero label="Taxa de sucesso" value={`${k.success_rate}%`} sub={`${k.success} de ${k.success + k.error} execuções`} />
          <Kpi label="Aplicações" value={k.projects} sub={`${k.live} no ar · ${k.draft} rascunho`} />
          <Kpi label="Execuções" value={k.executions} sub={`${k.running} em andamento`} />
          <Kpi label="Usuários ativos" value={adm.users.active} sub={`de ${adm.users.total} cadastrados`} />
        </div>

        {/* gráficos */}
        <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="card p-5 lg:col-span-2">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-semibold text-brand-900">Execuções (7 dias)</h2>
              <div className="flex items-center gap-3 text-xs text-slate-500">
                <Legend color="bg-accent-500" label="sucesso" />
                <Legend color="bg-red-500" label="erro" />
              </div>
            </div>
            <TimelineChart days={days} />
          </div>

          <div className="card flex flex-col p-5">
            <h2 className="mb-4 font-semibold text-brand-900">Distribuição</h2>
            <Donut success={k.success} error={k.error} running={k.running} />
          </div>
        </div>

        {/* consumo de máquina + requisições */}
        <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="card p-5 lg:col-span-2">
            <h2 className="mb-4 font-semibold text-brand-900">Consumo de máquina</h2>
            {sys.available ? (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <Gauge label="CPU" pct={sys.cpu_percent ?? 0} detail={`${Math.round(sys.cpu_percent ?? 0)}%`} />
                <Gauge label="Memória" pct={sys.ram_percent ?? 0} detail={`${sys.ram_used_gb} / ${sys.ram_total_gb} GB`} />
                <Gauge label="Disco" pct={sys.disk_percent ?? 0} detail={`${sys.disk_used_gb} / ${sys.disk_total_gb} GB`} />
              </div>
            ) : (
              <p className="text-sm text-slate-400">
                Métricas de máquina indisponíveis (psutil não instalado no servidor).
              </p>
            )}
          </div>

          <div className="card p-5">
            <h2 className="mb-4 font-semibold text-brand-900">Requisições</h2>
            <MiniStat label="Total desde o último reinício" value={adm.requests.total.toLocaleString("pt-BR")} />
            <MiniStat label="Última hora" value={adm.requests.last_hour.toLocaleString("pt-BR")} />
            <MiniStat label="Último minuto" value={adm.requests.last_minute.toLocaleString("pt-BR")} />
            <MiniStat label="Pedidos ao assistente (chat)" value={adm.chat.prompts.toLocaleString("pt-BR")} />
          </div>
        </div>

        {/* listas */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* aplicações por execução */}
          <div className="card overflow-hidden">
            <h2 className="border-b border-slate-100 px-5 py-3 font-semibold text-brand-900">
              Aplicações mais usadas
            </h2>
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-400">
                <tr>
                  <th className="px-4 py-2">Aplicação</th>
                  <th className="px-4 py-2">Status</th>
                  <th className="px-4 py-2 text-right">Exec.</th>
                  <th className="px-4 py-2 text-right">Erros</th>
                </tr>
              </thead>
              <tbody>
                {dash.by_project.slice(0, 8).map((p) => (
                  <tr key={p.id} className="border-t border-slate-100 hover:bg-slate-50">
                    <td className="px-4 py-2">
                      <Link to={`/projects/${p.id}/logs`} className="font-medium text-brand-700 hover:underline">
                        {p.name}
                      </Link>
                    </td>
                    <td className="px-4 py-2"><StatusBadge status={p.status} /></td>
                    <td className="px-4 py-2 text-right text-slate-600">{p.executions}</td>
                    <td className={`px-4 py-2 text-right font-medium ${p.errors ? "text-red-600" : "text-slate-400"}`}>
                      {p.errors}
                    </td>
                  </tr>
                ))}
                {dash.by_project.length === 0 && (
                  <tr><td colSpan={4} className="px-4 py-6 text-center text-slate-400">Nenhuma aplicação.</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {/* pedidos / pesquisas no chat */}
          <div className="card overflow-hidden">
            <h2 className="border-b border-slate-100 px-5 py-3 font-semibold text-brand-900">
              Últimos pedidos ao assistente
            </h2>
            <div className="divide-y divide-slate-100">
              {adm.chat.recent_prompts.map((m) => (
                <Link
                  key={m.id}
                  to={`/projects/${m.project_id}/assistente`}
                  className="block px-5 py-3 hover:bg-brand-50/40"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-brand-700">{m.project_name || "—"}</span>
                    <span className="text-xs text-slate-400">
                      {m.created_at ? new Date(m.created_at).toLocaleString("pt-BR") : ""}
                    </span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-sm text-slate-600">{m.content}</p>
                </Link>
              ))}
              {adm.chat.recent_prompts.length === 0 && (
                <div className="px-5 py-8 text-center text-sm text-slate-400">
                  Nenhum pedido registrado ainda.
                </div>
              )}
            </div>
          </div>

          {/* erros recentes */}
          <div className="card overflow-hidden lg:col-span-2">
            <h2 className="border-b border-slate-100 px-5 py-3 font-semibold text-brand-900">
              Erros recentes
            </h2>
            <div className="divide-y divide-slate-100">
              {dash.recent_errors.map((e) => (
                <Link key={e.id} to={`/projects/${e.project_id}/logs`} className="block px-5 py-3 hover:bg-red-50/50">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-brand-900">
                      {e.project_name} · {e.stage_name}
                    </span>
                    <span className="text-xs text-slate-400">
                      {new Date(e.started_at).toLocaleString("pt-BR")}
                    </span>
                  </div>
                  <pre className="mt-1 truncate text-xs text-red-600">{e.stderr || "erro"}</pre>
                </Link>
              ))}
              {dash.recent_errors.length === 0 && (
                <div className="px-5 py-8 text-center text-sm text-slate-400">
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

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={`h-2 w-2 rounded-full ${color}`} /> {label}
    </span>
  );
}

function KpiHero({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-xl bg-gradient-to-br from-brand-800 to-brand-600 p-5 text-white shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-brand-100/80">{label}</div>
      <div className="mt-1 text-3xl font-bold">{value}</div>
      <div className="mt-1 text-xs text-brand-100/80">{sub}</div>
    </div>
  );
}

function Kpi({ label, value, sub }: { label: string; value: number | string; sub: string }) {
  return (
    <div className="card p-5">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-1 text-3xl font-bold text-brand-900">{value}</div>
      <div className="mt-1 text-xs text-slate-500">{sub}</div>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="mb-3 flex items-center justify-between border-b border-slate-100 pb-2 last:mb-0 last:border-0 last:pb-0">
      <span className="text-sm text-slate-500">{label}</span>
      <span className="text-lg font-bold text-brand-900">{value}</span>
    </div>
  );
}

function Gauge({ label, pct, detail }: { label: string; pct: number; detail: string }) {
  const p = Math.max(0, Math.min(100, pct));
  const tone = p >= 85 ? "bg-red-500" : p >= 60 ? "bg-amber-400" : "bg-accent-500";
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-sm">
        <span className="font-medium text-slate-600">{label}</span>
        <span className="text-xs text-slate-400">{detail}</span>
      </div>
      <div className="h-3 overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full ${tone} transition-all duration-500`} style={{ width: `${p}%` }} />
      </div>
    </div>
  );
}

function TimelineChart({ days }: { days: { label: string; success: number; error: number; total: number }[] }) {
  const max = Math.max(1, ...days.map((d) => d.total));
  return (
    <div className="flex h-40 items-end gap-3">
      {days.map((d, i) => (
        <div key={i} className="flex flex-1 flex-col items-center gap-1">
          <div className="flex h-32 w-full max-w-[44px] flex-col justify-end gap-0.5">
            {d.error > 0 && (
              <div
                className="w-full rounded-t bg-red-400"
                style={{ height: `${(d.error / max) * 100}%` }}
                title={`${d.error} erro(s)`}
              />
            )}
            <div
              className="w-full rounded-t bg-accent-500"
              style={{ height: `${(d.success / max) * 100}%` }}
              title={`${d.success} sucesso(s)`}
            />
          </div>
          <span className="text-[10px] text-slate-400">{d.label}</span>
        </div>
      ))}
    </div>
  );
}

function Donut({ success, error, running }: { success: number; error: number; running: number }) {
  const total = success + error + running;
  const r = 52;
  const c = 2 * Math.PI * r;
  const segs = [
    { v: success, color: "#18b1a8", label: "Sucesso" },
    { v: error, color: "#ef4444", label: "Erro" },
    { v: running, color: "#fbbf24", label: "Em andamento" },
  ];
  let offset = 0;
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4">
      <div className="relative h-36 w-36">
        <svg viewBox="0 0 140 140" className="h-full w-full -rotate-90">
          <circle cx="70" cy="70" r={r} fill="none" stroke="#f1f5f9" strokeWidth="16" />
          {total > 0 &&
            segs.map((s, i) => {
              const len = (s.v / total) * c;
              const dash = `${len} ${c - len}`;
              const el = (
                <circle
                  key={i}
                  cx="70"
                  cy="70"
                  r={r}
                  fill="none"
                  stroke={s.color}
                  strokeWidth="16"
                  strokeDasharray={dash}
                  strokeDashoffset={-offset}
                />
              );
              offset += len;
              return el;
            })}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-bold text-brand-900">{total}</span>
          <span className="text-[10px] uppercase tracking-wide text-slate-400">execuções</span>
        </div>
      </div>
      <div className="w-full space-y-1.5">
        {segs.map((s) => (
          <div key={s.label} className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-2 text-slate-600">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: s.color }} />
              {s.label}
            </span>
            <span className="font-medium text-brand-900">
              {s.v}
              <span className="ml-1 text-xs text-slate-400">
                ({total ? Math.round((s.v / total) * 100) : 0}%)
              </span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
