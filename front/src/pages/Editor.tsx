import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
} from "reactflow";
import MonacoEditor from "@monaco-editor/react";
import { api } from "../lib/api";
import type {
  Edge as ApiEdge,
  Execution,
  Project,
  SourceFile,
  Stage,
  StageType,
} from "../lib/types";
import { Logo, StatusBadge, StageIcon, STAGE_META } from "../components/ui";
import { nodeTypes } from "../components/flowNodes";
import SmartChat from "../components/SmartChat";

const PALETTE: StageType[] = ["form", "script", "job", "hook"];

export default function Editor() {
  const { id } = useParams();
  const projectId = Number(id);
  const [project, setProject] = useState<Project | null>(null);
  const [stages, setStages] = useState<Stage[]>([]);
  const [files, setFiles] = useState<SourceFile[]>([]);
  const [openTabs, setOpenTabs] = useState<string[]>([]);
  const [activePath, setActivePath] = useState<string>("");
  const [editorValue, setEditorValue] = useState("");
  const [dirty, setDirty] = useState(false);
  const [previewStage, setPreviewStage] = useState<Stage | null>(null);
  const [saving, setSaving] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [footer, setFooter] = useState<"execucoes" | "tarefas">("execucoes");
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [publishing, setPublishing] = useState(false);

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  const loadGraph = useCallback(async () => {
    const [st, ed] = await Promise.all([
      api.get<Stage[]>(`/api/projects/${projectId}/stages`),
      api.get<ApiEdge[]>(`/api/projects/${projectId}/edges`),
    ]);
    setStages(st);
    setNodes(
      st.map((s) => ({
        id: String(s.id),
        type: "stage",
        position: { x: s.pos_x, y: s.pos_y },
        data: { label: s.name, type: s.type },
      }))
    );
    setEdges(
      ed.map((e) => ({
        id: String(e.id),
        source: String(e.source_stage_id),
        target: String(e.target_stage_id),
        label: e.variable_label,
        markerEnd: { type: MarkerType.ArrowClosed },
        style: { stroke: "#94a3b8" },
      }))
    );
  }, [projectId, setNodes, setEdges]);

  async function loadFiles() {
    setFiles(await api.get<SourceFile[]>(`/api/projects/${projectId}/files`));
  }
  async function loadExecutions() {
    const res = await api.get<{ items: Execution[] }>(
      `/api/projects/${projectId}/executions?page_size=10`
    );
    setExecutions(res.items);
  }

  useEffect(() => {
    api.get<Project>(`/api/projects/${projectId}`).then(setProject);
    loadGraph();
    loadFiles();
    loadExecutions();
  }, [projectId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        if (activePath) saveFile();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activePath, editorValue]);

  function openFile(path: string) {
    const f = files.find((x) => x.path === path);
    if (!f) return;
    setPreviewStage(null);
    setOpenTabs((t) => (t.includes(path) ? t : [...t, path]));
    setActivePath(path);
    setEditorValue(f.content);
    setDirty(false);
  }

  function onNodeClick(_evt: unknown, node: { id: string }) {
    const stage = stages.find((s) => String(s.id) === node.id);
    if (!stage) return;
    // script/agent abrem o código; form/hook/job abrem a tela de configuração
    const opensCode =
      (stage.type === "script" || stage.type === "agent") &&
      stage.entry_file &&
      files.some((f) => f.path === stage.entry_file);
    if (opensCode) {
      openFile(stage.entry_file);
    } else {
      setActivePath("");
      setPreviewStage(stage);
    }
  }

  async function saveFile() {
    if (!activePath) return;
    setSaving("saving");
    try {
      await api.put(`/api/projects/${projectId}/files`, {
        path: activePath,
        content: editorValue,
      });
      setDirty(false);
      await loadFiles();
      await loadGraph(); // refletir mudanças no workflow (status/problemas)
      setSaving("saved");
      setTimeout(() => setSaving("idle"), 1500);
    } catch (e: any) {
      setSaving("error");
      alert("Erro ao salvar: " + (e?.message || "tente novamente"));
    }
  }

  async function newSourceFile() {
    const name = prompt("Nome do arquivo (ex: novo.py):");
    if (!name) return;
    await api.put(`/api/projects/${projectId}/files`, { path: name, content: "" });
    await loadFiles();
    setOpenTabs((t) => (t.includes(name) ? t : [...t, name]));
    setActivePath(name);
    setEditorValue("");
    setDirty(false);
  }

  async function removeSourceFile(path: string) {
    if (!confirm(`Excluir ${path}?`)) return;
    await api.del(`/api/projects/${projectId}/files?path=${encodeURIComponent(path)}`);
    setOpenTabs((t) => t.filter((x) => x !== path));
    if (activePath === path) {
      setActivePath("");
      setEditorValue("");
    }
    loadFiles();
  }

  async function addStage(type: StageType) {
    const name = `${STAGE_META[type].label} ${stages.length + 1}`;
    await api.post(`/api/projects/${projectId}/stages`, {
      type,
      name,
      pos_x: 120 + stages.length * 40,
      pos_y: 80 + stages.length * 30,
    });
    await loadGraph();
    await loadFiles();
  }

  const onConnect = useCallback(
    async (c: Connection) => {
      setEdges((eds) => addEdge({ ...c, markerEnd: { type: MarkerType.ArrowClosed } }, eds));
      await api.post(`/api/projects/${projectId}/edges`, {
        source_stage_id: Number(c.source),
        target_stage_id: Number(c.target),
        variable_label: "var",
      });
      loadGraph();
    },
    [projectId, setEdges, loadGraph]
  );

  const onNodeDragStop = useCallback(
    (_: unknown, node: any) => {
      api.patch(`/api/projects/${projectId}/stages/${node.id}`, {
        pos_x: node.position.x,
        pos_y: node.position.y,
      });
    },
    [projectId]
  );

  async function publish() {
    setPublishing(true);
    try {
      await api.post(`/api/projects/${projectId}/publish`);
      const p = await api.get<Project>(`/api/projects/${projectId}`);
      setProject(p);
    } finally {
      setPublishing(false);
    }
  }

  const problems = useMemo(() => {
    const issues: string[] = [];
    const scripts = stages.filter((s) => s.type === "script");
    for (const s of scripts) {
      if (!files.find((f) => f.path === s.entry_file))
        issues.push(`Script "${s.name}" sem arquivo ${s.entry_file}`);
    }
    return issues;
  }, [stages, files]);

  return (
    <div className="flex h-full flex-col bg-slate-50">
      {/* Top bar */}
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-white px-4 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <Link to="/" className="shrink-0">
            <Logo />
          </Link>
          <span className="shrink-0 text-slate-300">/</span>
          <span className="truncate font-semibold text-brand-900">
            {project?.name}
          </span>
          {project && (
            <span className="shrink-0">
              <StatusBadge status={project.status} />
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <span
            className={`hidden text-xs md:inline ${
              problems.length ? "text-orange-600" : "text-emerald-600"
            }`}
          >
            {problems.length
              ? `${problems.length} problema(s)`
              : "Nenhum problema encontrado"}
          </span>
          <Link
            to={`/projects/${projectId}/assistente`}
            className="btn-outline py-1.5 text-sm"
            title="Modo guiado para usuário não-técnico"
          >
            Assistente
          </Link>
          <Link
            to={`/projects/${projectId}/builds`}
            className="btn-outline py-1.5 text-sm"
          >
            Versões
          </Link>
          <Link
            to={`/projects/${projectId}/workflow`}
            className="btn-outline py-1.5 text-sm"
          >
            Monitor
          </Link>
          {project && (
            <a
              href={`/app/${project.subdomain}`}
              target="_blank"
              rel="noreferrer"
              className="btn-accent py-1.5 text-sm"
            >
              Testar
            </a>
          )}
          <button
            onClick={publish}
            disabled={publishing}
            className="btn-primary whitespace-nowrap py-1.5 text-sm"
          >
            {publishing ? "Publicando..." : "Salvar e Publicar"}
          </button>
        </div>
      </header>

      {/* 3 panels */}
      <div className="flex min-h-0 flex-1 overflow-x-auto">
        <div className="flex w-[320px] min-w-[300px] shrink-0 flex-col border-r border-slate-200">
          <SmartChat projectId={projectId} onApplied={() => { loadFiles(); loadGraph(); }} />
        </div>

        {/* center: explorer + monaco */}
        <div className="flex min-w-[320px] flex-1 flex-col">
          <div className="flex min-h-0 flex-1">
            <div className="flex w-56 shrink-0 flex-col overflow-auto border-r border-slate-200 bg-white">
              <div className="flex items-center justify-between px-3 py-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                  Código Fonte
                </span>
                <button
                  onClick={newSourceFile}
                  title="Novo arquivo"
                  className="flex h-5 w-5 items-center justify-center rounded text-slate-400 hover:bg-brand-50 hover:text-brand-700"
                >
                  +
                </button>
              </div>
              <div className="space-y-0.5 px-2">
                {files
                  .filter((f) => !f.is_dir)
                  .map((f) => {
                    const active = activePath === f.path;
                    return (
                      <div
                        key={f.path}
                        onClick={() => openFile(f.path)}
                        className={`group flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm ${
                          active ? "bg-brand-50 text-brand-700" : "text-slate-600 hover:bg-slate-50"
                        }`}
                      >
                        <FileBadge path={f.path} />
                        <span className="flex-1 truncate">{f.path}</span>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            removeSourceFile(f.path);
                          }}
                          title="Excluir arquivo"
                          className="hidden h-4 w-4 shrink-0 items-center justify-center rounded text-slate-400 hover:text-red-600 group-hover:flex"
                        >
                          ×
                        </button>
                      </div>
                    );
                  })}
                {files.filter((f) => !f.is_dir).length === 0 && (
                  <div className="px-2 py-1 text-xs text-slate-400">Nenhum arquivo</div>
                )}
              </div>

              <div className="mt-3 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Projeto
              </div>
              <div className="space-y-0.5 px-2 pb-2">
                <ExplorerLink to={`/projects/${projectId}/files`} label="Arquivos" icon="📁" />
                <ExplorerLink to={`/projects/${projectId}/access`} label="Controle de Acesso" icon="🔒" />
                <ExplorerLink to={`/projects/${projectId}/settings/env`} label="Variáveis de Ambiente" icon="🔑" />
                <ExplorerLink to={`/projects/${projectId}/settings`} label="Configurações" icon="⚙️" />
              </div>
            </div>

            <div className="flex min-w-0 flex-1 flex-col">
              <div className="flex items-center gap-1 border-b border-slate-200 bg-slate-100 px-2 py-1">
                {openTabs.length === 0 && (
                  <span className="px-2 py-1 text-xs text-slate-400">
                    Selecione um arquivo
                  </span>
                )}
                {openTabs.map((t) => (
                  <button
                    key={t}
                    onClick={() => openFile(t)}
                    className={`flex items-center gap-1 rounded-t px-3 py-1 text-xs ${
                      activePath === t
                        ? "bg-white text-brand-900"
                        : "text-slate-500 hover:bg-white/60"
                    }`}
                  >
                    {t}
                    {activePath === t && dirty && (
                      <span className="text-orange-500">●</span>
                    )}
                  </button>
                ))}
                {activePath && (
                  <button
                    onClick={saveFile}
                    disabled={saving === "saving"}
                    className={`ml-auto rounded-lg px-2.5 py-1 text-xs font-medium ${
                      saving === "saved"
                        ? "bg-emerald-500 text-white"
                        : saving === "error"
                        ? "bg-red-500 text-white"
                        : "bg-accent-500 text-white hover:bg-accent-600"
                    }`}
                  >
                    {saving === "saving"
                      ? "Salvando..."
                      : saving === "saved"
                      ? "Salvo ✓"
                      : saving === "error"
                      ? "Erro ao salvar"
                      : "Salvar arquivo"}
                  </button>
                )}
              </div>
              <div className="min-h-0 flex-1">
                {previewStage ? (
                  <StagePreview
                    stage={previewStage}
                    projectId={projectId}
                    onOpenCode={openFile}
                    onSaved={loadGraph}
                  />
                ) : activePath ? (
                  <MonacoEditor
                    height="100%"
                    language={activePath.endsWith(".py") ? "python" : activePath.endsWith(".md") ? "markdown" : "plaintext"}
                    theme="vs-dark"
                    value={editorValue}
                    onChange={(v) => {
                      setEditorValue(v ?? "");
                      setDirty(true);
                    }}
                    options={{ fontSize: 13, minimap: { enabled: false } }}
                  />
                ) : (
                  <div className="flex h-full flex-col items-center justify-center gap-1 text-sm text-slate-400">
                    <span>Nenhum arquivo aberto</span>
                    <span className="text-xs">Clique em um nó do fluxo para pré-visualizar</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* right: canvas */}
        <div className="flex w-[40%] min-w-[340px] shrink-0 flex-col border-l border-slate-200">
          <div className="min-h-0 flex-1">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodeDragStop={onNodeDragStop}
              onNodeClick={onNodeClick}
              fitView
            >
              <Background variant={BackgroundVariant.Dots} gap={18} size={1.5} color="#cbd5e1" />
              <Controls />
            </ReactFlow>
          </div>
          <div className="flex flex-wrap items-center gap-1.5 border-t border-slate-200 bg-white px-3 py-2">
            <span className="text-xs text-slate-400">Adicionar:</span>
            {PALETTE.map((t) => (
              <button
                key={t}
                onClick={() => addStage(t)}
                className="flex flex-col items-center gap-0.5 rounded-lg px-2 py-1 text-[10px] text-slate-600 hover:bg-slate-50"
                style={{ color: STAGE_META[t].color }}
              >
                <StageIcon type={t} className="h-5 w-5" />
                {STAGE_META[t].label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* footer */}
      <div className="h-44 shrink-0 border-t border-slate-200 bg-white">
        <div className="flex gap-1 border-b border-slate-200 px-3 py-1.5">
          {[
            ["execucoes", "Execuções"],
            ["tarefas", "Tarefas"],
          ].map(([k, l]) => (
            <button
              key={k}
              onClick={() => setFooter(k as any)}
              className={`rounded px-3 py-1 text-xs font-medium ${
                footer === k ? "bg-brand-50 text-brand-700" : "text-slate-500"
              }`}
            >
              {l}
            </button>
          ))}
          <Link to={`/projects/${projectId}/logs`} className="ml-auto text-xs text-brand-500 hover:underline">
            Ver todos os logs →
          </Link>
        </div>
        <div className="h-[calc(100%-37px)] overflow-auto p-2">
          {footer === "execucoes" ? (
            executions.length === 0 ? (
              <div className="p-3 text-sm text-slate-400">Nenhuma execução ainda.</div>
            ) : (
              <table className="w-full text-left text-xs">
                <thead className="text-slate-400">
                  <tr>
                    <th className="px-2 py-1">Etapa</th>
                    <th className="px-2 py-1">Tipo</th>
                    <th className="px-2 py-1">Status</th>
                    <th className="px-2 py-1">ID</th>
                    <th className="px-2 py-1">Início</th>
                  </tr>
                </thead>
                <tbody>
                  {executions.map((e) => (
                    <tr key={e.id} className="border-t border-slate-100">
                      <td className="px-2 py-1">{e.stage_name}</td>
                      <td className="px-2 py-1">{e.stage_type}</td>
                      <td className="px-2 py-1">
                        <StatusBadge status={e.status} />
                      </td>
                      <td className="px-2 py-1 font-mono text-slate-400">
                        {e.id.slice(0, 8)}
                      </td>
                      <td className="px-2 py-1 text-slate-400">
                        {new Date(e.started_at).toLocaleString("pt-BR")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          ) : (
            <div className="p-3 text-sm text-slate-500">
              {problems.length === 0 ? (
                "Nenhuma tarefa pendente."
              ) : (
                <ul className="list-inside list-disc">
                  {problems.map((p) => (
                    <li key={p} className="text-orange-600">
                      {p}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function JobPreview({
  projectId,
  stage,
  onOpenCode,
  onSaved,
}: {
  projectId: number;
  stage: Stage;
  onOpenCode: (path: string) => void;
  onSaved: () => void;
}) {
  const cfg = stage.config || {};
  const sched = cfg.schedule || {};
  const [type, setType] = useState<string>(sched.type || "interval");
  const [every, setEvery] = useState<number>(sched.every || 1);
  const [unit, setUnit] = useState<string>(sched.unit || "hours");
  const [time, setTime] = useState<string>(sched.time || "08:00");
  const [enabled, setEnabled] = useState<boolean>(!!cfg.enabled);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(false);
  const [running, setRunning] = useState(false);
  const [runMsg, setRunMsg] = useState("");

  const summary =
    type === "manual"
      ? "Somente manual (sem agendamento)"
      : type === "interval"
      ? `A cada ${every} ${unitLabel(unit, every)}`
      : `Diariamente às ${time}`;

  async function save() {
    setSaving(true);
    try {
      const schedule =
        type === "interval"
          ? { type, every, unit }
          : type === "daily"
          ? { type, time }
          : { type: "manual" };
      await api.patch(`/api/projects/${projectId}/stages/${stage.id}`, {
        config: { ...cfg, enabled, schedule },
      });
      stage.config = { ...cfg, enabled, schedule };
      setSavedAt(true);
      setTimeout(() => setSavedAt(false), 1500);
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  async function runNow() {
    setRunning(true);
    setRunMsg("");
    try {
      const ex = await api.post<any>(`/api/projects/${projectId}/stages/${stage.id}/run`, {});
      setRunMsg(`Execução iniciada (${String(ex.id).slice(0, 8)}). Veja em Logs / Monitor.`);
    } catch (e: any) {
      setRunMsg("Erro: " + (e?.message || "falha ao iniciar"));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="max-w-lg space-y-4">
      <div className="card p-5">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-semibold text-brand-900">Agendamento</h3>
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <span className="text-slate-500">{enabled ? "Ativo" : "Pausado"}</span>
            <button
              type="button"
              onClick={() => setEnabled((v) => !v)}
              className={`relative h-5 w-9 rounded-full transition ${enabled ? "bg-accent-500" : "bg-slate-300"}`}
            >
              <span
                className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${enabled ? "left-[18px]" : "left-0.5"}`}
              />
            </button>
          </label>
        </div>

        <label className="mb-1 block text-sm font-medium text-slate-700">Frequência</label>
        <select className="input" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="manual">Somente manual</option>
          <option value="interval">A cada intervalo</option>
          <option value="daily">Diariamente em um horário</option>
        </select>

        {type === "interval" && (
          <div className="mt-3 flex items-center gap-2">
            <span className="text-sm text-slate-500">A cada</span>
            <input
              type="number"
              min={1}
              className="input w-20"
              value={every}
              onChange={(e) => setEvery(Math.max(1, Number(e.target.value)))}
            />
            <select className="input w-32" value={unit} onChange={(e) => setUnit(e.target.value)}>
              <option value="minutes">minuto(s)</option>
              <option value="hours">hora(s)</option>
              <option value="days">dia(s)</option>
            </select>
          </div>
        )}

        {type === "daily" && (
          <div className="mt-3 flex items-center gap-2">
            <span className="text-sm text-slate-500">Todos os dias às</span>
            <input type="time" className="input w-32" value={time} onChange={(e) => setTime(e.target.value)} />
          </div>
        )}

        <div className="mt-4 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">
          <span className="font-medium text-brand-900">Resumo:</span> {summary}
          {!enabled && type !== "manual" && (
            <span className="ml-1 text-amber-600">· pausado (ative para rodar automaticamente)</span>
          )}
        </div>

        <button onClick={save} disabled={saving} className="btn-primary mt-4 text-sm">
          {saving ? "Salvando…" : savedAt ? "Salvo ✓" : "Salvar configuração"}
        </button>
      </div>

      <div className="card flex items-center justify-between p-5">
        <div>
          <div className="text-sm font-medium text-brand-900">Script do Job</div>
          <div className="text-xs text-slate-400">{stage.entry_file || `${stage.key}.py`}</div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => stage.entry_file && onOpenCode(stage.entry_file)}
            className="btn-outline py-1.5 text-sm"
          >
            Ver código
          </button>
          <button onClick={runNow} disabled={running} className="btn-accent py-1.5 text-sm">
            {running ? "Iniciando…" : "Executar agora"}
          </button>
        </div>
      </div>
      {runMsg && <div className="text-sm text-slate-500">{runMsg}</div>}
    </div>
  );
}

function unitLabel(unit: string, n: number) {
  const map: Record<string, [string, string]> = {
    minutes: ["minuto", "minutos"],
    hours: ["hora", "horas"],
    days: ["dia", "dias"],
  };
  const [s, p] = map[unit] || ["", ""];
  return n === 1 ? s : p;
}

function HookPreview({ projectId, stage }: { projectId: number; stage: Stage }) {
  const [info, setInfo] = useState<any>(null);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    api
      .post<any>(`/api/projects/${projectId}/stages/${stage.id}/webhook`)
      .then(setInfo)
      .catch(() => {});
  }, [projectId, stage.id]);

  if (!info)
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-400">
        Gerando webhook…
      </div>
    );

  const url = `${location.origin}${info.path}`;
  const curl = `curl -X ${info.method} ${url} \\\n  -H "Content-Type: application/json" \\\n  -d '{"exemplo": 123}'`;

  async function testar() {
    setTesting(true);
    setResult(null);
    try {
      const r = await fetch(info.path, {
        method: info.method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ exemplo: 123, origem: "teste do editor" }),
      });
      setResult(await r.json());
    } catch (e: any) {
      setResult({ erro: e.message });
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="mb-1 flex items-center gap-2">
        <span className="font-medium text-brand-900">Webhook de entrada</span>
        <span className="badge bg-amber-100 text-amber-700">{info.method}</span>
      </div>
      <p className="text-sm text-slate-500">
        Dispara o fluxo quando recebe uma requisição HTTP. Use esta URL no sistema externo.
      </p>

      <div className="mt-4">
        <label className="text-xs font-medium uppercase tracking-wide text-slate-400">
          URL de produção
        </label>
        <div className="mt-1 flex items-center gap-2">
          <code className="flex-1 truncate rounded-lg bg-slate-900 px-3 py-2 font-mono text-xs text-emerald-200">
            {url}
          </code>
          <button
            onClick={() => {
              navigator.clipboard.writeText(url);
              setCopied(true);
              setTimeout(() => setCopied(false), 1200);
            }}
            className="btn-outline px-2.5 py-2 text-xs"
          >
            {copied ? "copiado" : "copiar"}
          </button>
        </div>
      </div>

      <div className="mt-3 text-sm">
        {info.target ? (
          <span className="text-slate-500">
            Ao receber, dispara:{" "}
            <span className="font-medium text-brand-900">{info.target.name}</span> ({info.target.type})
          </span>
        ) : (
          <span className="text-orange-600">
            Conecte este Hook a um Script no canvas para que o disparo execute algo.
          </span>
        )}
      </div>

      <div className="mt-3">
        <label className="text-xs font-medium uppercase tracking-wide text-slate-400">
          Exemplo (curl)
        </label>
        <pre className="mt-1 overflow-auto rounded-lg bg-slate-900 p-3 font-mono text-xs text-slate-100">
          {curl}
        </pre>
      </div>

      <button onClick={testar} disabled={testing} className="btn-accent mt-3 text-sm">
        {testing ? "Disparando…" : "Testar webhook"}
      </button>
      {result && (
        <div className="mt-2">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-400">
            Resposta
          </div>
          <pre className="mt-1 overflow-auto rounded-lg bg-slate-50 p-3 text-xs">
            {JSON.stringify(result, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

function StagePreview({
  stage,
  projectId,
  onOpenCode,
  onSaved,
}: {
  stage: Stage;
  projectId: number;
  onOpenCode: (path: string) => void;
  onSaved: () => void;
}) {
  const meta = STAGE_META[stage.type];
  const cfg = stage.config || {};
  const fields: any[] = cfg.fields || [];
  const isResult = cfg.mode === "result";

  return (
    <div className="h-full overflow-auto bg-slate-50 p-6">
      <div className="mb-4 flex items-center gap-2">
        <span
          className="flex h-7 w-7 items-center justify-center rounded-lg text-white"
          style={{ background: meta.color }}
        >
          <StageIcon type={stage.type} className="h-4 w-4" />
        </span>
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
            {meta.label} · pré-visualização
          </div>
          <div className="font-semibold text-brand-900">{stage.name}</div>
        </div>
      </div>

      {stage.type === "form" && !isResult && (
        <div className="mx-auto max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-bold text-brand-900">
            {cfg.title || stage.name}
          </h2>
          {cfg.description && (
            <p className="mt-1 text-sm text-slate-500">{cfg.description}</p>
          )}
          <div className="mt-4 space-y-3">
            {fields.length === 0 && (
              <p className="text-sm text-slate-400">Este formulário ainda não tem campos.</p>
            )}
            {fields.map((f: any) => (
              <div key={f.name}>
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  {f.label || f.name}
                </label>
                {f.type === "file" ? (
                  <div className="rounded-lg border border-dashed border-slate-300 px-3 py-2 text-sm text-slate-400">
                    Selecionar arquivo…
                  </div>
                ) : f.type === "select" ? (
                  <select className="input" disabled>
                    {(f.options || ["opção"]).map((o: string) => (
                      <option key={o}>{o}</option>
                    ))}
                  </select>
                ) : (
                  <input className="input" disabled placeholder={f.type || "texto"} />
                )}
              </div>
            ))}
            <button className="btn-primary w-full" disabled>
              {cfg.submit_label || "Enviar"}
            </button>
          </div>
        </div>
      )}

      {stage.type === "form" && isResult && (
        <div className="mx-auto max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-bold text-brand-900">{cfg.title || "Resultado"}</h2>
          <p className="mt-1 text-sm text-emerald-600">
            {cfg.description || "Tela de resultado exibida após o processamento."}
          </p>
          <div className="mt-4 rounded-lg bg-slate-50 p-4 text-sm text-slate-500">
            Resumo da execução (chave <code>{cfg.summary_key || "resumo"}</code>) + botão de
            download do arquivo (<code>{cfg.result_file_key || "arquivo_resultado"}</code>).
          </div>
          <button className="btn-accent mt-4 w-full" disabled>
            Baixar resultado
          </button>
        </div>
      )}

      {stage.type === "hook" && <HookPreview projectId={projectId} stage={stage} />}

      {stage.type === "job" && (
        <JobPreview
          projectId={projectId}
          stage={stage}
          onOpenCode={onOpenCode}
          onSaved={onSaved}
        />
      )}

      {["script", "agent"].includes(stage.type) && (
        <div className="rounded-xl border border-slate-200 bg-white p-5 text-sm">
          <div className="font-medium text-brand-900">
            {meta.label} sem arquivo de código ainda
          </div>
          <p className="mt-1 text-slate-500">
            Arquivo esperado: <code>{stage.entry_file || `${stage.key}.py`}</code>. Use o
            Smart Chat ou o botão "+" no explorador para criar o código.
          </p>
        </div>
      )}

      <details className="mt-4 text-xs text-slate-400">
        <summary className="cursor-pointer">configuração (JSON)</summary>
        <pre className="mt-1 overflow-auto rounded bg-white p-2">
          {JSON.stringify(cfg, null, 2)}
        </pre>
      </details>
    </div>
  );
}

function ExplorerLink({
  to,
  label,
  icon,
}: {
  to: string;
  label: string;
  icon?: string;
}) {
  return (
    <Link
      to={to}
      className="flex items-center gap-2 rounded px-2 py-1 text-sm text-slate-600 hover:bg-slate-50 hover:text-brand-700"
    >
      <span className="w-4 text-center text-xs">{icon}</span>
      <span className="truncate">{label}</span>
    </Link>
  );
}

const EXT_BADGE: Record<string, string> = {
  py: "bg-blue-100 text-blue-700",
  md: "bg-slate-200 text-slate-600",
  txt: "bg-slate-100 text-slate-500",
  json: "bg-amber-100 text-amber-700",
  csv: "bg-emerald-100 text-emerald-700",
};

function FileBadge({ path }: { path: string }) {
  const ext = (path.split(".").pop() || "").toLowerCase();
  const label = ext ? ext.slice(0, 3) : "·";
  const cls = EXT_BADGE[ext] || "bg-slate-100 text-slate-500";
  return (
    <span
      className={`flex h-4 w-6 shrink-0 items-center justify-center rounded text-[9px] font-bold uppercase ${cls}`}
    >
      {label}
    </span>
  );
}
