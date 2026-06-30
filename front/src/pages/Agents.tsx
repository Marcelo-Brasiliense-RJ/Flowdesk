import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import TopNav from "../components/TopNav";
import { Spinner } from "../components/ui";

interface Agent {
  id: string;
  name: string;
  role: string;
  level: number;
  parent: string | null;
  temp: string;
  tools: string[];
  desc: string;
  where: string;
  model: string;
  editable: boolean;
  prompt: string | null;
  prompt_overridden: boolean;
}

interface AgentsData {
  agents: Agent[];
  edges: { from: string; to: string }[];
  model: string;
  model_default: string;
  model_catalog: { value: string; provider: string; note: string }[];
  ai_enabled: boolean;
}

/* Paleta por agente (apenas visual — o backend não define cores). */
const GRAD: Record<string, [string, string]> = {
  assistente: ["#155489", "#18b1a8"],
  construtor: ["#0f8f88", "#2dd4c4"],
  descritor: ["#1f6fb2", "#4a80c2"],
  reparador: ["#7c3aed", "#a78bfa"],
  classificador: ["#c98a00", "#e0b15a"],
  nomeador: ["#155489", "#4a80c2"],
};
const grad = (id: string) => {
  const [a, b] = GRAD[id] || ["#155489", "#18b1a8"];
  return `linear-gradient(135deg, ${a}, ${b})`;
};

const CANVAS_W = 760;
const CANVAS_H = 420;

function AgentIcon({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="4" y="8.5" width="16" height="10.5" rx="3.2" />
      <path d="M12 8.5V5" />
      <circle cx="12" cy="4" r="1.3" fill="currentColor" stroke="none" />
      <circle cx="9.2" cy="13.4" r="1.25" fill="currentColor" stroke="none" />
      <circle cx="14.8" cy="13.4" r="1.25" fill="currentColor" stroke="none" />
      <path d="M2.5 13v2.4M21.5 13v2.4" />
    </svg>
  );
}

export default function Agents() {
  const { user } = useAuth();
  const isAdmin = !!user?.is_admin;
  const [data, setData] = useState<AgentsData | null>(null);
  const [err, setErr] = useState("");
  const [sel, setSel] = useState("assistente");
  const [draft, setDraft] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setData(await api.get<AgentsData>("/api/ai/agents"));
    } catch (e: any) {
      setErr(e?.message || "Não foi possível carregar os agentes.");
    }
  }
  useEffect(() => {
    load();
  }, []);

  const agent = data?.agents.find((a) => a.id === sel) || null;

  // ao trocar de agente, sincroniza o rascunho do prompt
  useEffect(() => {
    setDraft(agent?.prompt ?? "");
    setDirty(false);
    setSaved(false);
  }, [sel, agent?.prompt]);

  // posições do grafo: orquestrador no topo, especialistas em linha abaixo
  const pos = useMemo(() => {
    const map: Record<string, { x: number; y: number; r: number }> = {};
    if (!data) return map;
    const top = data.agents.filter((a) => a.level === 1);
    const rest = data.agents.filter((a) => a.level !== 1);
    top.forEach((a) => (map[a.id] = { x: CANVAS_W / 2, y: 66, r: 34 }));
    const n = rest.length;
    const left = 90;
    const right = CANVAS_W - 90;
    rest.forEach((a, i) => {
      const x = n === 1 ? CANVAS_W / 2 : left + ((right - left) * i) / (n - 1);
      map[a.id] = { x, y: 312, r: 28 };
    });
    return map;
  }, [data]);

  async function saveModel(model: string) {
    if (!isAdmin) return;
    setBusy(true);
    try {
      await api.put("/api/ai/model", { model });
      await load();
    } catch (e: any) {
      setErr(e?.message || "Falha ao salvar o modelo.");
    } finally {
      setBusy(false);
    }
  }

  async function savePrompt() {
    if (!agent?.editable || !isAdmin) return;
    setBusy(true);
    try {
      await api.put(`/api/ai/agents/${agent.id}/prompt`, { prompt: draft });
      await load();
      setDirty(false);
      setSaved(true);
      setTimeout(() => setSaved(false), 4000);
    } catch (e: any) {
      setErr(e?.message || "Falha ao salvar o prompt.");
    } finally {
      setBusy(false);
    }
  }

  async function resetPrompt() {
    if (!agent?.editable || !isAdmin) return;
    setBusy(true);
    try {
      await api.del(`/api/ai/agents/${agent.id}/prompt`);
      await load();
      setDirty(false);
      setSaved(false);
    } catch (e: any) {
      setErr(e?.message || "Falha ao restaurar o prompt.");
    } finally {
      setBusy(false);
    }
  }

  if (err && !data) {
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
  if (!data || !agent) {
    return (
      <div className="min-h-full">
        <TopNav />
        <div className="flex items-center justify-center py-32 text-ink3">
          <Spinner className="h-8 w-8" />
        </div>
      </div>
    );
  }

  const incoming = data.edges.filter((e) => e.to === agent.id).map((e) => byName(data, e.from));
  const outgoing = data.edges.filter((e) => e.from === agent.id).map((e) => byName(data, e.to));

  return (
    <div className="min-h-full">
      <TopNav />
      <main className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-5">
          <h1 className="text-2xl font-extrabold tracking-tight text-ink">Agentes</h1>
          <p className="mt-1 text-sm text-ink2">
            As funções de IA que realmente existem no FlowDesk. O Assistente conduz a
            conversa e aciona as funções especializadas. Clique num agente para ver o que
            ele faz e ajustar o que for editável.
          </p>
          {!data.ai_enabled && (
            <p className="mt-2 inline-flex rounded-lg px-3 py-1.5 text-xs" style={{ background: "var(--warn2-soft)", color: "var(--warn2)" }}>
              IA em modo simulado (sem chave de API configurada). A configuração abaixo é salva e será aplicada quando a IA estiver ativa.
            </p>
          )}
        </div>

        <div className="flex flex-col gap-5 lg:flex-row lg:items-start">
          {/* Grafo dos agentes reais */}
          <div className="card min-w-0 flex-1 overflow-hidden">
            <div className="flex flex-wrap items-center gap-4 border-b border-line px-5 py-3" style={{ background: "var(--surface-glass)" }}>
              <span className="text-xs font-bold text-ink">Organograma</span>
              <Legend grad={grad("assistente")} label="Orquestrador" />
              <Legend grad="linear-gradient(135deg,#1f6fb2,#4a80c2)" label="Especialistas" />
            </div>
            <div className="overflow-auto p-4">
              <div className="relative mx-auto" style={{ width: CANVAS_W, height: CANVAS_H }}>
                <div
                  className="pointer-events-none absolute inset-0"
                  style={{
                    backgroundImage: "radial-gradient(var(--border) 1px, transparent 1px)",
                    backgroundSize: "24px 24px",
                    opacity: 0.45,
                  }}
                />
                <svg width={CANVAS_W} height={CANVAS_H} className="pointer-events-none absolute inset-0">
                  <defs>
                    <marker id="ag-arrow" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto">
                      <path d="M0 0L9 4.5L0 9z" fill="var(--border-strong)" />
                    </marker>
                  </defs>
                  {data.edges.map((e) => {
                    const a = pos[e.from];
                    const b = pos[e.to];
                    if (!a || !b) return null;
                    return (
                      <line
                        key={`${e.from}-${e.to}`}
                        x1={a.x}
                        y1={a.y + a.r}
                        x2={b.x}
                        y2={b.y - b.r - 4}
                        stroke="var(--border-strong)"
                        strokeWidth="1.8"
                        markerEnd="url(#ag-arrow)"
                        strokeLinecap="round"
                      />
                    );
                  })}
                </svg>
                {data.agents.map((a) => {
                  const p = pos[a.id];
                  if (!p) return null;
                  const selected = a.id === sel;
                  return (
                    <button
                      key={a.id}
                      onClick={() => setSel(a.id)}
                      className="absolute flex flex-col items-center gap-2 transition"
                      style={{ left: p.x, top: p.y, transform: "translate(-50%,-50%)", zIndex: 2 }}
                    >
                      <span
                        className="rounded-full transition"
                        style={{
                          padding: selected ? 4 : 0,
                          border: selected ? "2px solid var(--accent)" : "2px solid transparent",
                        }}
                      >
                        <span
                          className="flex items-center justify-center rounded-full text-white"
                          style={{
                            width: p.r * 2,
                            height: p.r * 2,
                            background: grad(a.id),
                            boxShadow: selected ? "0 10px 24px -10px var(--accent-glow)" : "var(--shadow-sm)",
                          }}
                        >
                          <AgentIcon size={Math.round(p.r * 0.95)} />
                        </span>
                      </span>
                      <span className="text-center leading-tight" style={{ width: a.level === 1 ? 132 : 110 }}>
                        <span className="block font-semibold text-ink" style={{ fontSize: a.level === 1 ? 13 : 11.5 }}>
                          {a.name}
                        </span>
                        <span className="mt-0.5 block text-[10px] text-ink3">{a.role}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Painel de detalhe */}
          <aside className="card w-full shrink-0 overflow-hidden lg:w-[372px]">
            <div className="border-b border-line p-[18px]" style={{ background: "var(--surface-glass)" }}>
              <div className="flex items-center gap-3">
                <span
                  className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-white"
                  style={{ background: grad(agent.id), boxShadow: "0 10px 22px -10px rgba(10,31,51,.5)" }}
                >
                  <AgentIcon size={24} />
                </span>
                <div className="min-w-0">
                  <div className="text-base font-extrabold tracking-tight text-ink">{agent.name}</div>
                  <div className="text-[12.5px] text-ink2">{agent.role}</div>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-3.5">
                <Meta label="Recebe de" value={incoming.length ? incoming.join(", ") : "—"} />
                <Meta label="Envia para" value={outgoing.length ? outgoing.join(", ") : "—"} />
              </div>
            </div>

            <div className="flex max-h-[560px] flex-col gap-[18px] overflow-auto p-[18px]">
              <Section title="O que faz">
                <p className="text-[13.5px] leading-relaxed text-ink2">{agent.desc}</p>
                <p className="mt-2 font-mono text-[11px] text-ink3">{agent.where}</p>
              </Section>

              {agent.tools.length > 0 && (
                <Section title="Comandos & ferramentas">
                  <div className="flex flex-wrap gap-1.5">
                    {agent.tools.map((t) => (
                      <span key={t} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1 text-xs font-medium text-ink" style={{ background: "var(--surface-2)" }}>
                        <span className="h-1.5 w-1.5 rounded-full" style={{ background: "var(--accent)" }} />
                        {t}
                      </span>
                    ))}
                  </div>
                </Section>
              )}

              <div className="flex gap-2.5">
                <div className="flex-1 rounded-xl border border-line p-3" style={{ background: "var(--surface-2)" }}>
                  <div className="mb-1.5 text-[10.5px] font-bold uppercase tracking-wide text-ink3">Modelo (compartilhado)</div>
                  <select
                    className="input py-1.5 font-mono text-xs"
                    value={agent.model}
                    disabled={!isAdmin || busy}
                    onChange={(e) => saveModel(e.target.value)}
                  >
                    {!data.model_catalog.some((m) => m.value === agent.model) && (
                      <option value={agent.model}>{agent.model}</option>
                    )}
                    {data.model_catalog.map((m) => (
                      <option key={m.value} value={m.value}>
                        {m.value} · {m.note}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="w-24 shrink-0 rounded-xl border border-line p-3" style={{ background: "var(--surface-2)" }}>
                  <div className="text-[10.5px] font-bold uppercase tracking-wide text-ink3">Temp.</div>
                  <div className="mt-1 font-mono text-[13px] font-semibold text-ink">{agent.temp}</div>
                </div>
              </div>

              <div>
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="text-[11px] font-bold uppercase tracking-wide text-ink3">System prompt</span>
                  {agent.editable ? (
                    dirty ? (
                      <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold" style={{ color: "var(--warn2)" }}>
                        <span className="h-1.5 w-1.5 rounded-full" style={{ background: "var(--warn2)" }} />
                        alterado
                      </span>
                    ) : saved ? (
                      <span className="text-[11px] font-semibold text-accentv">✓ salvo</span>
                    ) : agent.prompt_overridden ? (
                      <span className="text-[11px] font-medium text-ink3">override ativo</span>
                    ) : null
                  ) : (
                    <span className="text-[11px] font-medium text-ink3">definido no código</span>
                  )}
                </div>

                {agent.prompt == null ? (
                  <p className="rounded-xl border border-dashed px-3 py-3 text-xs leading-relaxed text-ink3" style={{ borderColor: "var(--border-strong)" }}>
                    O prompt deste agente é construído dinamicamente no código (com dados do
                    projeto) e não é editável por aqui.
                  </p>
                ) : (
                  <>
                    <textarea
                      value={draft}
                      readOnly={!agent.editable || !isAdmin}
                      onChange={(e) => {
                        setDraft(e.target.value);
                        setDirty(true);
                        setSaved(false);
                      }}
                      rows={10}
                      className="input resize-y font-mono text-[12.5px] leading-relaxed"
                      style={!agent.editable ? { background: "var(--surface-2)", color: "var(--text-2)" } : undefined}
                    />
                    {agent.editable && isAdmin && (
                      <div className="mt-2.5 flex gap-2">
                        <button onClick={savePrompt} disabled={busy || !dirty} className="btn-primary flex-1 py-2 text-sm disabled:opacity-40">
                          {busy ? "Salvando…" : "Salvar prompt"}
                        </button>
                        <button onClick={resetPrompt} disabled={busy || !agent.prompt_overridden} className="btn-outline py-2 text-sm disabled:opacity-40">
                          Restaurar
                        </button>
                      </div>
                    )}
                    {agent.editable && !isAdmin && (
                      <p className="mt-2 text-xs text-ink3">Apenas administradores podem editar o prompt e o modelo.</p>
                    )}
                  </>
                )}
              </div>
            </div>
          </aside>
        </div>
      </main>
    </div>
  );
}

function byName(data: AgentsData, id: string | null) {
  return data.agents.find((a) => a.id === id)?.name || id || "—";
}

function Legend({ grad, label }: { grad: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-ink2">
      <span className="h-2.5 w-2.5 rounded-full" style={{ background: grad }} />
      {label}
    </span>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex flex-col gap-0.5">
      <span className="text-[9.5px] font-bold uppercase tracking-wide text-ink3">{label}</span>
      <span className="text-xs text-ink">{value}</span>
    </span>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-2 text-[11px] font-bold uppercase tracking-wide text-ink3">{title}</div>
      {children}
    </div>
  );
}
