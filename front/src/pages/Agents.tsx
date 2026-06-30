import { useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import TopNav from "../components/TopNav";
import { Spinner } from "../components/ui";

interface Agent {
  id: string;
  name: string;
  role: string;
  level: number;
  desc: string;
  tools: string[];
  temp: string;
  where?: string;
  model: string;
  prompt: string | null;
  x: number;
  y: number;
  c1: string;
  c2: string;
  builtin: boolean;
  kind?: string;
  editablePrompt?: boolean;
}
interface Edge {
  id: string;
  from: string;
  to: string;
}
interface AgentsData {
  agents: Agent[];
  edges: Edge[];
  model: string;
  model_default: string;
  model_catalog: { value: string; provider: string; note: string }[];
  ai_enabled: boolean;
  custom: boolean;
  applied: { assistant_prompt: boolean; shared_model: boolean; orchestration: boolean };
}

const CANVAS_W = 760;
const CANVAS_H = 520;
const radiusFor = (level: number) => (level === 1 ? 34 : level === 2 ? 28 : 24);
const grad = (a: { c1: string; c2: string }) => `linear-gradient(135deg, ${a.c1}, ${a.c2})`;

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

  const [agents, setAgents] = useState<Agent[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [meta, setMeta] = useState<Omit<AgentsData, "agents" | "edges"> | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [err, setErr] = useState("");
  const [sel, setSel] = useState<{ kind: "node" | "edge"; id: string } | null>({ kind: "node", id: "assistente" });
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedNote, setSavedNote] = useState(false);
  const [pendingFrom, setPendingFrom] = useState<string | null>(null);
  const [cursor, setCursor] = useState<{ x: number; y: number } | null>(null);
  const [seq, setSeq] = useState(1);

  const canvasRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ id: string; ox: number; oy: number } | null>(null);
  const connectRef = useRef<string | null>(null);
  const agentsRef = useRef<Agent[]>([]);
  agentsRef.current = agents;

  async function load() {
    try {
      const d = await api.get<AgentsData>("/api/ai/agents");
      setAgents(d.agents);
      setEdges(d.edges);
      const { agents: _a, edges: _e, ...rest } = d;
      setMeta(rest);
      setLoaded(true);
      setDirty(false);
    } catch (e: any) {
      setErr(e?.message || "Não foi possível carregar os agentes.");
    }
  }
  useEffect(() => {
    load();
  }, []);

  // drag (mover) + connect (ligar) via listeners globais
  useEffect(() => {
    function rectXY(e: MouseEvent) {
      const el = canvasRef.current;
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: e.clientX - r.left, y: e.clientY - r.top };
    }
    function onMove(e: MouseEvent) {
      const p = rectXY(e);
      if (!p) return;
      if (dragRef.current) {
        const { id, ox, oy } = dragRef.current;
        const x = Math.max(36, Math.min(CANVAS_W - 36, p.x - ox));
        const y = Math.max(40, Math.min(CANVAS_H - 50, p.y - oy));
        setAgents((as) => as.map((a) => (a.id === id ? { ...a, x, y } : a)));
      } else if (connectRef.current) {
        setCursor(p);
      }
    }
    function onUp(e: MouseEvent) {
      if (connectRef.current) {
        const p = rectXY(e);
        const from = connectRef.current;
        if (p) {
          const target = agentsRef.current.find(
            (a) => a.id !== from && Math.hypot(a.x - p.x, a.y - p.y) < radiusFor(a.level) + 14
          );
          if (target) addEdge(from, target.id);
        }
        connectRef.current = null;
        setPendingFrom(null);
        setCursor(null);
      }
      dragRef.current = null;
      document.body.style.userSelect = "";
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function startDrag(id: string, e: React.MouseEvent) {
    if (!isAdmin) {
      setSel({ kind: "node", id });
      return;
    }
    e.stopPropagation();
    const el = canvasRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const a = agents.find((x) => x.id === id);
    if (!a) return;
    dragRef.current = { id, ox: e.clientX - r.left - a.x, oy: e.clientY - r.top - a.y };
    document.body.style.userSelect = "none";
    setSel({ kind: "node", id });
  }
  function startConnect(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    connectRef.current = id;
    setPendingFrom(id);
  }
  function addEdge(from: string, to: string) {
    setEdges((es) => {
      if (from === to || es.some((x) => x.from === from && x.to === to)) return es;
      setDirty(true);
      const id = `e${Date.now()}`;
      setSel({ kind: "edge", id });
      return [...es, { id, from, to }];
    });
  }
  function removeEdge(id: string) {
    setEdges((es) => es.filter((e) => e.id !== id));
    setSel(null);
    setDirty(true);
  }
  function addAgent() {
    const id = `custom${seq}`;
    setSeq((s) => s + 1);
    const a: Agent = {
      id,
      name: `Novo agente ${seq}`,
      role: "Especialista",
      level: 3,
      desc: "Descreva o que este agente faz.",
      tools: [],
      temp: "0.2",
      model: meta?.model || "gpt-4o-mini",
      prompt: "Você é um novo agente. Defina aqui suas instruções.",
      x: 120 + (seq % 4) * 70,
      y: 110,
      c1: "#5b6b7e",
      c2: "#8597a8",
      builtin: false,
      editablePrompt: true,
    };
    setAgents((as) => [...as, a]);
    setSel({ kind: "node", id });
    setDirty(true);
  }
  function deleteAgent(id: string) {
    setAgents((as) => as.filter((a) => a.id !== id));
    setEdges((es) => es.filter((e) => e.from !== id && e.to !== id));
    setSel(null);
    setDirty(true);
  }
  function patchAgent(id: string, patch: Partial<Agent>) {
    setAgents((as) => as.map((a) => (a.id === id ? { ...a, ...patch } : a)));
    setDirty(true);
  }

  async function save() {
    if (!isAdmin) return;
    setSaving(true);
    try {
      await api.put("/api/ai/graph", { agents, edges });
      await load();
      setSavedNote(true);
      setTimeout(() => setSavedNote(false), 4000);
    } catch (e: any) {
      setErr(e?.message || "Falha ao salvar o grafo.");
    } finally {
      setSaving(false);
    }
  }
  async function resetGraph() {
    if (!isAdmin) return;
    setSaving(true);
    try {
      await api.del("/api/ai/graph");
      await load();
    } catch (e: any) {
      setErr(e?.message || "Falha ao restaurar.");
    } finally {
      setSaving(false);
    }
  }

  if (err && !loaded) {
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
  if (!loaded || !meta) {
    return (
      <div className="min-h-full">
        <TopNav />
        <div className="flex items-center justify-center py-32 text-ink3">
          <Spinner className="h-8 w-8" />
        </div>
      </div>
    );
  }

  const selAgent = sel?.kind === "node" ? agents.find((a) => a.id === sel.id) || null : null;
  const selEdge = sel?.kind === "edge" ? edges.find((e) => e.id === sel.id) || null : null;
  const byId = (id: string) => agents.find((a) => a.id === id);
  const nameOf = (id: string) => byId(id)?.name || id;

  return (
    <div className="min-h-full">
      <TopNav />
      <main className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-ink">Agentes</h1>
            <p className="mt-1 max-w-2xl text-sm text-ink2">
              Monte a equipe de agentes: arraste para posicionar, puxe a alça lateral para ligar
              dois agentes, e clique numa ligação ou agente para ajustar o prompt.
            </p>
          </div>
          {isAdmin && (
            <div className="flex shrink-0 items-center gap-2">
              <button onClick={addAgent} className="btn-primary py-2 text-sm">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" aria-hidden>
                  <path d="M12 5v14M5 12h14" />
                </svg>
                Adicionar agente
              </button>
              <button onClick={save} disabled={saving || !dirty} className="btn-accent py-2 text-sm disabled:opacity-40">
                {saving ? "Salvando…" : dirty ? "Salvar grafo" : savedNote ? "✓ salvo" : "Salvo"}
              </button>
              {meta.custom && (
                <button onClick={resetGraph} disabled={saving} className="btn-outline py-2 text-sm disabled:opacity-40" title="Restaurar os 6 agentes reais">
                  Restaurar
                </button>
              )}
            </div>
          )}
        </div>

        {/* Banner de integridade — o que é aplicado de verdade hoje (Fase 1) */}
        <div className="mb-5 rounded-xl border px-4 py-2.5 text-xs leading-relaxed" style={{ borderColor: "var(--warn2-soft)", background: "var(--warn2-soft)", color: "var(--warn2)" }}>
          Aplicado de verdade no pipeline atual: <strong>prompt do Assistente</strong> e{" "}
          <strong>modelo compartilhado</strong>. Agentes e ligações personalizados são salvos como
          configuração; a execução do grafo (orquestração multi-agente) vem numa próxima fase, atrás
          de uma flag — o pipeline atual continua rodando até lá.
          {!meta.ai_enabled && " IA em modo simulado (sem chave de API)."}
        </div>

        <div className="flex flex-col gap-5 lg:flex-row lg:items-start">
          {/* Quadro de agentes */}
          <div className="card min-w-0 flex-1 overflow-hidden">
            <div className="flex flex-wrap items-center gap-4 border-b border-line px-5 py-3" style={{ background: "var(--surface-glass)" }}>
              <span className="text-xs font-bold text-ink">Quadro de agentes</span>
              <span className="inline-flex items-center gap-1.5 text-xs text-ink3">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d="M5 9l-3 3 3 3M9 5l3-3 3 3M15 19l-3 3-3-3M19 9l3 3-3 3M2 12h20M12 2v20" />
                </svg>
                arraste para mover
              </span>
              <span className="inline-flex items-center gap-1.5 text-xs text-ink3">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: "var(--accent)", border: "2px solid var(--surface)", boxShadow: "0 0 0 1px var(--accent)" }} />
                puxe a alça para ligar
              </span>
            </div>
            <div className="overflow-auto p-4">
              <div ref={canvasRef} className="relative mx-auto" style={{ width: CANVAS_W, height: CANVAS_H }}>
                <div
                  className="pointer-events-none absolute inset-0"
                  style={{ backgroundImage: "radial-gradient(var(--border) 1px, transparent 1px)", backgroundSize: "24px 24px", opacity: 0.45 }}
                />
                <svg width={CANVAS_W} height={CANVAS_H} className="absolute inset-0">
                  <defs>
                    <marker id="ag-arrow" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto">
                      <path d="M0 0L9 4.5L0 9z" fill="var(--border-strong)" />
                    </marker>
                    <marker id="ag-arrow-sel" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto">
                      <path d="M0 0L9 4.5L0 9z" fill="var(--accent)" />
                    </marker>
                  </defs>
                  {edges.map((e) => {
                    const a = byId(e.from);
                    const b = byId(e.to);
                    if (!a || !b) return null;
                    const dx = b.x - a.x;
                    const dy = b.y - a.y;
                    const len = Math.hypot(dx, dy) || 1;
                    const ux = dx / len;
                    const uy = dy / len;
                    const x1 = a.x + ux * (radiusFor(a.level) + 2);
                    const y1 = a.y + uy * (radiusFor(a.level) + 2);
                    const x2 = b.x - ux * (radiusFor(b.level) + 8);
                    const y2 = b.y - uy * (radiusFor(b.level) + 8);
                    const selected = selEdge?.id === e.id;
                    return (
                      <g key={e.id}>
                        <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={selected ? "var(--accent)" : "var(--border-strong)"} strokeWidth={selected ? 2.4 : 1.8} markerEnd={`url(#ag-arrow${selected ? "-sel" : ""})`} strokeLinecap="round" />
                        <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="transparent" strokeWidth="16" style={{ cursor: "pointer" }} onClick={() => setSel({ kind: "edge", id: e.id })} />
                      </g>
                    );
                  })}
                  {pendingFrom && cursor && byId(pendingFrom) && (
                    <line x1={byId(pendingFrom)!.x} y1={byId(pendingFrom)!.y} x2={cursor.x} y2={cursor.y} stroke="var(--accent)" strokeWidth="2" strokeDasharray="5 5" strokeLinecap="round" />
                  )}
                </svg>

                {agents.map((a) => {
                  const r = radiusFor(a.level);
                  const selected = sel?.kind === "node" && sel.id === a.id;
                  return (
                    <div key={a.id} className="absolute" style={{ left: a.x, top: a.y, transform: "translate(-50%,-50%)", zIndex: 2 }}>
                      <div className="relative flex flex-col items-center" style={{ cursor: isAdmin ? "grab" : "pointer" }}>
                        <div className="relative" style={{ padding: selected ? 4 : 0, borderRadius: "50%", border: selected ? "2px solid var(--accent)" : "2px solid transparent" }}>
                          <div
                            onMouseDown={(e) => startDrag(a.id, e)}
                            className="flex items-center justify-center rounded-full text-white"
                            style={{ width: r * 2, height: r * 2, background: grad(a), boxShadow: selected ? "0 10px 24px -10px var(--accent-glow)" : "var(--shadow-sm)" }}
                          >
                            <AgentIcon size={Math.round(r * 0.95)} />
                          </div>
                          {isAdmin && (
                            <div
                              onMouseDown={(e) => startConnect(a.id, e)}
                              title="Arraste para ligar a outro agente"
                              className="absolute"
                              style={{ right: -7, top: "50%", transform: "translateY(-50%)", width: 15, height: 15, borderRadius: "50%", background: "var(--accent)", border: "2px solid var(--surface)", boxShadow: "0 1px 4px rgba(0,0,0,.3)", cursor: "crosshair" }}
                            />
                          )}
                        </div>
                        <button onClick={() => setSel({ kind: "node", id: a.id })} className="mt-1.5 text-center leading-tight" style={{ width: a.level === 1 ? 132 : 110 }}>
                          <span className="block font-semibold text-ink" style={{ fontSize: a.level === 1 ? 13 : 11.5 }}>
                            {a.name}
                          </span>
                          <span className="mt-0.5 block text-[10px] text-ink3">{a.role}</span>
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Painel lateral */}
          <aside className="card w-full shrink-0 overflow-hidden lg:w-[372px]">
            {selEdge ? (
              <EdgePanel
                from={nameOf(selEdge.from)}
                to={nameOf(selEdge.to)}
                fromGrad={grad(byId(selEdge.from) || { c1: "#155489", c2: "#18b1a8" })}
                toGrad={grad(byId(selEdge.to) || { c1: "#155489", c2: "#18b1a8" })}
                fromRole={byId(selEdge.from)?.role || ""}
                toRole={byId(selEdge.to)?.role || ""}
                isAdmin={isAdmin}
                onApply={(prompt) => {
                  patchAgent(selEdge.to, { prompt });
                  setSel({ kind: "node", id: selEdge.to });
                }}
                onRemove={() => removeEdge(selEdge.id)}
              />
            ) : selAgent ? (
              <NodePanel
                key={selAgent.id}
                agent={selAgent}
                isAdmin={isAdmin}
                catalog={meta.model_catalog}
                incoming={edges.filter((e) => e.to === selAgent.id).map((e) => nameOf(e.from))}
                outgoing={edges.filter((e) => e.from === selAgent.id).map((e) => nameOf(e.to))}
                onPatch={(p) => patchAgent(selAgent.id, p)}
                onDelete={() => deleteAgent(selAgent.id)}
              />
            ) : (
              <div className="p-8 text-center text-sm text-ink3">Selecione um agente ou uma ligação para editar.</div>
            )}
          </aside>
        </div>
      </main>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-2 text-[11px] font-bold uppercase tracking-wide text-ink3">{label}</div>
      {children}
    </div>
  );
}

function NodePanel({
  agent, isAdmin, catalog, incoming, outgoing, onPatch, onDelete,
}: {
  agent: Agent;
  isAdmin: boolean;
  catalog: { value: string; provider: string; note: string }[];
  incoming: string[];
  outgoing: string[];
  onPatch: (p: Partial<Agent>) => void;
  onDelete: () => void;
}) {
  const ro = !isAdmin;
  const promptEditable = isAdmin && (agent.editablePrompt ?? !agent.builtin);
  return (
    <>
      <div className="border-b border-line p-[18px]" style={{ background: "var(--surface-glass)" }}>
        <div className="flex items-center gap-3">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-white" style={{ background: grad(agent), boxShadow: "0 10px 22px -10px rgba(10,31,51,.5)" }}>
            <AgentIcon size={24} />
          </span>
          <div className="min-w-0 flex-1">
            <input
              value={agent.name}
              readOnly={ro}
              onChange={(e) => onPatch({ name: e.target.value })}
              className="w-full rounded-md border border-transparent bg-transparent px-1.5 py-0.5 text-base font-extrabold tracking-tight text-ink outline-none focus:border-line focus:bg-surface"
            />
            <input
              value={agent.role}
              readOnly={ro}
              onChange={(e) => onPatch({ role: e.target.value })}
              className="w-full rounded-md border border-transparent bg-transparent px-1.5 py-0.5 text-[12.5px] text-ink2 outline-none focus:border-line focus:bg-surface"
            />
          </div>
          {isAdmin && (
            <button onClick={onDelete} title="Excluir agente" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-line text-err" style={{ background: "var(--surface)" }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" />
              </svg>
            </button>
          )}
        </div>
        <div className="mt-3 flex flex-wrap gap-3.5">
          <Meta label="Recebe de" value={incoming.length ? incoming.join(", ") : "—"} />
          <Meta label="Envia para" value={outgoing.length ? outgoing.join(", ") : "—"} />
        </div>
      </div>

      <div className="flex max-h-[560px] flex-col gap-[18px] overflow-auto p-[18px]">
        <Field label="O que faz">
          <textarea
            value={agent.desc}
            readOnly={ro}
            onChange={(e) => onPatch({ desc: e.target.value })}
            rows={3}
            className="input resize-y text-[13px] leading-relaxed"
          />
          {agent.where && <p className="mt-1.5 font-mono text-[11px] text-ink3">{agent.where}</p>}
        </Field>

        {agent.tools.length > 0 && (
          <Field label="Comandos & ferramentas">
            <div className="flex flex-wrap gap-1.5">
              {agent.tools.map((t) => (
                <span key={t} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1 text-xs font-medium text-ink" style={{ background: "var(--surface-2)" }}>
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: "var(--accent)" }} />
                  {t}
                </span>
              ))}
            </div>
          </Field>
        )}

        <div className="flex gap-2.5">
          <div className="flex-1 rounded-xl border border-line p-3" style={{ background: "var(--surface-2)" }}>
            <div className="mb-1.5 text-[10.5px] font-bold uppercase tracking-wide text-ink3">Modelo</div>
            <select className="input py-1.5 font-mono text-xs" value={agent.model} disabled={ro} onChange={(e) => onPatch({ model: e.target.value })}>
              {!catalog.some((m) => m.value === agent.model) && <option value={agent.model}>{agent.model}</option>}
              {catalog.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.value} · {m.note}
                </option>
              ))}
            </select>
          </div>
          <div className="w-24 shrink-0 rounded-xl border border-line p-3" style={{ background: "var(--surface-2)" }}>
            <div className="text-[10.5px] font-bold uppercase tracking-wide text-ink3">Temp.</div>
            <input value={agent.temp} readOnly={ro} onChange={(e) => onPatch({ temp: e.target.value })} className="mt-1 w-full bg-transparent font-mono text-[13px] font-semibold text-ink outline-none" />
          </div>
        </div>

        <Field label="System prompt">
          {agent.prompt == null ? (
            <p className="rounded-xl border border-dashed px-3 py-3 text-xs leading-relaxed text-ink3" style={{ borderColor: "var(--border-strong)" }}>
              O prompt deste agente é construído dinamicamente no código (com dados do projeto). Edite
              criando um agente próprio ou ajustando o Assistente.
            </p>
          ) : (
            <textarea
              value={agent.prompt}
              readOnly={!promptEditable}
              onChange={(e) => onPatch({ prompt: e.target.value })}
              rows={9}
              className="input resize-y font-mono text-[12.5px] leading-relaxed"
              style={!promptEditable ? { background: "var(--surface-2)", color: "var(--text-2)" } : undefined}
            />
          )}
          {agent.id !== "assistente" && agent.prompt != null && (
            <p className="mt-1.5 text-[11px] text-ink3">
              Salvo como configuração. Será aplicado quando a orquestração multi-agente entrar (Fase 2).
            </p>
          )}
        </Field>
      </div>
    </>
  );
}

function EdgePanel({
  from, to, fromGrad, toGrad, fromRole, toRole, isAdmin, onApply, onRemove,
}: {
  from: string;
  to: string;
  fromGrad: string;
  toGrad: string;
  fromRole: string;
  toRole: string;
  isAdmin: boolean;
  onApply: (prompt: string) => void;
  onRemove: () => void;
}) {
  const note = `${to} passa a receber a saída de ${from}. Use esta ligação para que ${to.toLowerCase()} trabalhe a partir do que ${from.toLowerCase()} produziu, encadeando ${fromRole.toLowerCase()} → ${toRole.toLowerCase()}.`;
  const suggested = `Você é o ${to} (${toRole}).\n\nVocê recebe diretamente o resultado de ${from} (${fromRole}). Ao recebê-lo:\n- Trate a saída de ${from} como entrada confiável e não a recalcule.\n- Verifique se está completa antes de prosseguir; se faltar algo, peça a ${from}.\n- Faça apenas a sua parte e devolva um resultado claro, pronto para a próxima etapa.`;
  const [draft, setDraft] = useState(suggested);
  return (
    <>
      <div className="border-b border-line p-[18px]" style={{ background: "var(--surface-glass)" }}>
        <div className="mb-2.5 text-[11px] font-bold uppercase tracking-wide text-ink3">Ligação</div>
        <div className="flex items-center gap-2.5">
          <span className="rounded-lg px-2.5 py-1 text-xs font-bold text-white" style={{ background: fromGrad }}>{from}</span>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--text-3)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M5 12h14M13 6l6 6-6 6" />
          </svg>
          <span className="rounded-lg px-2.5 py-1 text-xs font-bold text-white" style={{ background: toGrad }}>{to}</span>
        </div>
      </div>
      <div className="flex max-h-[560px] flex-col gap-[18px] overflow-auto p-[18px]">
        <Field label="O que essa ligação faz">
          <p className="text-[13.5px] leading-relaxed text-ink2">{note}</p>
        </Field>
        <Field label={`System prompt sugerido para ${to}`}>
          <textarea
            value={draft}
            readOnly={!isAdmin}
            onChange={(e) => setDraft(e.target.value)}
            rows={10}
            className="input resize-y font-mono text-[12px] leading-relaxed"
            style={{ borderColor: "var(--accent)", background: "var(--accent-soft)" }}
          />
          {isAdmin && (
            <div className="mt-2.5 flex gap-2">
              <button onClick={() => onApply(draft)} className="btn-primary flex-1 py-2 text-sm">
                Aplicar a {to}
              </button>
              <button onClick={onRemove} title="Remover ligação" className="btn-outline py-2 text-err">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" />
                </svg>
              </button>
            </div>
          )}
        </Field>
      </div>
    </>
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
