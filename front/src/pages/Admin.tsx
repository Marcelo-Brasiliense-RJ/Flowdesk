import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { AdminUser } from "../lib/types";
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
  ai_usage?: {
    tokens_total: number;
    top_projects: { project_id: number; project_name: string; tokens: number }[];
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
          <h1 className="text-xl font-bold text-ink">Acesso restrito</h1>
          <p className="mt-2 text-sm text-ink2">
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
          <h1 className="text-xl font-bold text-ink">Não foi possível carregar</h1>
          <p className="mt-2 text-sm text-ink2">{err}</p>
        </main>
      </div>
    );
  }

  if (!dash || !adm)
    return (
      <div className="min-h-full">
        <TopNav />
        <div className="flex items-center justify-center py-32 text-ink3">
          <Spinner className="h-8 w-8" />
        </div>
      </div>
    );

  const k = dash.kpis;
  const days = last7Days(dash.timeline);
  const sys = adm.system;

  return (
    <div className="min-h-full">
      <TopNav />
      <main className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-ink">Painel de controle</h1>
            <p className="text-sm text-ink2">
              Visão geral da plataforma. Atualiza a cada 15 segundos.
            </p>
          </div>
          <span className="text-xs text-ink3">
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
              <h2 className="font-bold text-ink">Execuções (7 dias)</h2>
              <div className="flex items-center gap-3 text-xs text-ink2">
                <Legend color="var(--accent)" label="sucesso" />
                <Legend color="var(--err)" label="erro" />
              </div>
            </div>
            <TimelineChart days={days} />
          </div>

          <div className="card flex flex-col p-5">
            <h2 className="mb-4 font-bold text-ink">Distribuição</h2>
            <Donut success={k.success} error={k.error} running={k.running} />
          </div>
        </div>

        {/* consumo de máquina + requisições */}
        <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="card p-5 lg:col-span-2">
            <h2 className="mb-4 font-bold text-ink">Consumo de máquina</h2>
            {sys.available ? (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <Gauge label="CPU" pct={sys.cpu_percent ?? 0} detail={`${Math.round(sys.cpu_percent ?? 0)}%`} />
                <Gauge label="Memória" pct={sys.ram_percent ?? 0} detail={`${sys.ram_used_gb} / ${sys.ram_total_gb} GB`} />
                <Gauge label="Disco" pct={sys.disk_percent ?? 0} detail={`${sys.disk_used_gb} / ${sys.disk_total_gb} GB`} />
              </div>
            ) : (
              <p className="text-sm text-ink3">
                Métricas de máquina indisponíveis (psutil não instalado no servidor).
              </p>
            )}
          </div>

          <div className="card p-5">
            <h2 className="mb-4 font-bold text-ink">Requisições</h2>
            <MiniStat label="Total desde o último reinício" value={adm.requests.total.toLocaleString("pt-BR")} />
            <MiniStat label="Última hora" value={adm.requests.last_hour.toLocaleString("pt-BR")} />
            <MiniStat label="Último minuto" value={adm.requests.last_minute.toLocaleString("pt-BR")} />
            <MiniStat label="Pedidos ao assistente (chat)" value={adm.chat.prompts.toLocaleString("pt-BR")} />
            {adm.ai_usage && (
              <MiniStat
                label="Uso de IA (tokens estimados)"
                value={adm.ai_usage.tokens_total.toLocaleString("pt-BR")}
              />
            )}
          </div>
        </div>

        {/* gestão de usuários */}
        <div className="mb-6">
          <UsersAdmin />
        </div>

        {/* listas */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* aplicações por execução */}
          <div className="card overflow-hidden">
            <h2 className="border-b border-line px-5 py-3 font-bold text-ink">
              Aplicações mais usadas
            </h2>
            <table className="w-full text-left text-sm">
              <thead className="bg-surface-2 text-xs uppercase text-ink3">
                <tr>
                  <th className="px-4 py-2">Aplicação</th>
                  <th className="px-4 py-2">Status</th>
                  <th className="px-4 py-2 text-right">Exec.</th>
                  <th className="px-4 py-2 text-right">Erros</th>
                </tr>
              </thead>
              <tbody>
                {dash.by_project.slice(0, 8).map((p) => (
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
                {dash.by_project.length === 0 && (
                  <tr><td colSpan={4} className="px-4 py-6 text-center text-ink3">Nenhuma aplicação.</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {/* pedidos / pesquisas no chat */}
          <div className="card overflow-hidden">
            <h2 className="border-b border-line px-5 py-3 font-bold text-ink">
              Últimos pedidos ao assistente
            </h2>
            <div className="divide-y divide-[color:var(--border)]">
              {adm.chat.recent_prompts.map((m) => (
                <Link
                  key={m.id}
                  to={`/projects/${m.project_id}/assistente`}
                  className="block px-5 py-3 transition hover:bg-surface-2"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-brandv">{m.project_name || "—"}</span>
                    <span className="text-xs text-ink3">
                      {m.created_at ? new Date(m.created_at).toLocaleString("pt-BR") : ""}
                    </span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-sm text-ink2">{m.content}</p>
                </Link>
              ))}
              {adm.chat.recent_prompts.length === 0 && (
                <div className="px-5 py-8 text-center text-sm text-ink3">
                  Nenhum pedido registrado ainda.
                </div>
              )}
            </div>
          </div>

          {/* erros recentes */}
          <div className="card overflow-hidden lg:col-span-2">
            <h2 className="border-b border-line px-5 py-3 font-bold text-ink">
              Erros recentes
            </h2>
            <div className="divide-y divide-[color:var(--border)]">
              {dash.recent_errors.map((e) => (
                <Link key={e.id} to={`/projects/${e.project_id}/logs`} className="block px-5 py-3 transition hover:bg-surface-2">
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
              {dash.recent_errors.length === 0 && (
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

/** Gestão de usuários: papéis administráveis pela interface (sem mexer em env). */
function UsersAdmin() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [msg, setMsg] = useState("");
  const [creating, setCreating] = useState(false);
  const [nEmail, setNEmail] = useState("");
  const [nName, setNName] = useState("");
  const [nPwd, setNPwd] = useState("");
  const [nRole, setNRole] = useState<"admin" | "dev" | "user">("user");

  async function load() {
    try {
      setUsers(await api.get<AdminUser[]>("/api/admin/users"));
    } catch {
      /* sem permissão ou backend antigo */
    }
  }
  useEffect(() => {
    load();
  }, []);

  function flash(t: string) {
    setMsg(t);
    setTimeout(() => setMsg(""), 5000);
  }

  async function createUser(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api.post("/api/admin/users", { email: nEmail, name: nName, password: nPwd, role: nRole });
      setCreating(false);
      setNEmail(""); setNName(""); setNPwd(""); setNRole("user");
      flash("Usuário criado.");
      load();
    } catch (err: any) {
      flash(err?.message || "Erro ao criar usuário.");
    }
  }

  async function setRole(u: AdminUser, role: string) {
    try {
      await api.patch(`/api/admin/users/${u.id}`, { role });
      flash(`Papel de ${u.email} atualizado para ${role}.`);
      load();
    } catch (err: any) {
      flash(err?.message || "Erro ao atualizar papel.");
    }
  }

  async function toggleActive(u: AdminUser) {
    try {
      await api.patch(`/api/admin/users/${u.id}`, { is_active: !u.is_active });
      flash(`${u.email} ${u.is_active ? "desativado" : "reativado"}.`);
      load();
    } catch (err: any) {
      flash(err?.message || "Erro ao atualizar usuário.");
    }
  }

  async function resetPassword(u: AdminUser) {
    const pwd = prompt(`Nova senha para ${u.email} (mínimo 8 caracteres):`);
    if (!pwd) return;
    try {
      await api.patch(`/api/admin/users/${u.id}`, { password: pwd });
      flash(`Senha de ${u.email} redefinida.`);
    } catch (err: any) {
      flash(err?.message || "Erro ao redefinir senha.");
    }
  }

  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between border-b border-line px-5 py-3">
        <h2 className="font-bold text-ink">Usuários e papéis</h2>
        <button onClick={() => setCreating((v) => !v)} className="btn-primary py-1.5 text-sm">
          {creating ? "Cancelar" : "+ Novo usuário"}
        </button>
      </div>
      {msg && (
        <div
          className="border-b border-line px-5 py-2 text-sm text-accentv"
          style={{ background: "var(--accent-soft)" }}
        >
          {msg}
        </div>
      )}
      {creating && (
        <form onSubmit={createUser} className="flex flex-wrap items-end gap-3 border-b border-line bg-surface-2 px-5 py-4">
          <div className="min-w-[220px] flex-1">
            <label className="mb-1 block text-xs font-medium text-ink2">E-mail</label>
            <input className="input" type="email" required value={nEmail} onChange={(e) => setNEmail(e.target.value)} />
          </div>
          <div className="min-w-[160px] flex-1">
            <label className="mb-1 block text-xs font-medium text-ink2">Nome</label>
            <input className="input" value={nName} onChange={(e) => setNName(e.target.value)} />
          </div>
          <div className="min-w-[160px]">
            <label className="mb-1 block text-xs font-medium text-ink2">Senha inicial</label>
            <input className="input" type="password" required minLength={8} value={nPwd} onChange={(e) => setNPwd(e.target.value)} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink2">Papel</label>
            <select className="input" value={nRole} onChange={(e) => setNRole(e.target.value as any)}>
              <option value="user">Usuário</option>
              <option value="dev">Dev</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <button className="btn-primary">Criar</button>
        </form>
      )}
      <table className="w-full text-left text-sm">
        <thead className="bg-surface-2 text-xs uppercase text-ink3">
          <tr>
            <th className="px-4 py-2">Usuário</th>
            <th className="px-4 py-2">Papel</th>
            <th className="px-4 py-2">Status</th>
            <th className="px-4 py-2 text-right">Ações</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} className="border-t border-line">
              <td className="px-4 py-2">
                <div className="font-semibold text-ink">{u.name || u.email}</div>
                <div className="text-xs text-ink3">{u.email}</div>
              </td>
              <td className="px-4 py-2">
                <select
                  className="input w-32 py-1 text-xs"
                  value={u.role}
                  onChange={(e) => setRole(u, e.target.value)}
                >
                  <option value="user">Usuário</option>
                  <option value="dev">Dev</option>
                  <option value="admin">Admin</option>
                </select>
              </td>
              <td className="px-4 py-2">
                <span className="badge" data-status={u.is_active ? "live" : "inactive"}>
                  {u.is_active ? "Ativo" : "Inativo"}
                </span>
              </td>
              <td className="px-4 py-2 text-right">
                <button onClick={() => resetPassword(u)} className="mr-2 text-xs text-brandv hover:underline">
                  Redefinir senha
                </button>
                <button onClick={() => toggleActive(u)} className="text-xs text-ink2 hover:underline">
                  {u.is_active ? "Desativar" : "Reativar"}
                </button>
              </td>
            </tr>
          ))}
          {users.length === 0 && (
            <tr>
              <td colSpan={4} className="px-4 py-8 text-center text-ink3">Carregando usuários…</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className="h-2 w-2 rounded-full" style={{ background: color }} /> {label}
    </span>
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

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="mb-3 flex items-center justify-between border-b border-line pb-2 last:mb-0 last:border-0 last:pb-0">
      <span className="text-sm text-ink2">{label}</span>
      <span className="text-lg font-bold text-ink">{value}</span>
    </div>
  );
}

function Gauge({ label, pct, detail }: { label: string; pct: number; detail: string }) {
  const p = Math.max(0, Math.min(100, pct));
  const tone = p >= 85 ? "var(--err)" : p >= 60 ? "var(--warn2)" : "var(--accent)";
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-sm">
        <span className="font-medium text-ink2">{label}</span>
        <span className="text-xs text-ink3">{detail}</span>
      </div>
      <div className="h-3 overflow-hidden rounded-full" style={{ background: "var(--border)" }}>
        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${p}%`, background: tone }} />
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
                className="w-full rounded-t"
                style={{ height: `${(d.error / max) * 100}%`, background: "var(--err)" }}
                title={`${d.error} erro(s)`}
              />
            )}
            <div
              className="w-full rounded-t"
              style={{ height: `${(d.success / max) * 100}%`, background: "var(--accent)" }}
              title={`${d.success} sucesso(s)`}
            />
          </div>
          <span className="text-[10px] text-ink3">{d.label}</span>
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
          <circle cx="70" cy="70" r={r} fill="none" stroke="var(--border)" strokeWidth="16" />
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
          <span className="text-2xl font-bold text-ink">{total}</span>
          <span className="text-[10px] uppercase tracking-wide text-ink3">execuções</span>
        </div>
      </div>
      <div className="w-full space-y-1.5">
        {segs.map((s) => (
          <div key={s.label} className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-2 text-ink2">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: s.color }} />
              {s.label}
            </span>
            <span className="font-medium text-ink">
              {s.v}
              <span className="ml-1 text-xs text-ink3">
                ({total ? Math.round((s.v / total) * 100) : 0}%)
              </span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
