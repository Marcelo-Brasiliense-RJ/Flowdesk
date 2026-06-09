import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  useEdgesState,
  useNodesState,
} from "reactflow";
import { api, getToken } from "../lib/api";
import type { Edge as ApiEdge, Stage } from "../lib/types";
import { nodeTypes } from "../components/flowNodes";
import ProjectLayout, { useProject } from "../components/ProjectLayout";

interface RecentResp {
  stages: Record<number, { id: string; status: string }[]>;
  pending: number;
  avg_seconds: number;
}

export default function WorkflowMonitor() {
  const { id, project } = useProject();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedExec, setSelectedExec] = useState<string | null>(null);
  const [stages, setStages] = useState<Stage[]>([]);

  const refresh = useCallback(async () => {
    const [st, ed, recent] = await Promise.all([
      api.get<Stage[]>(`/api/projects/${id}/stages`),
      api.get<ApiEdge[]>(`/api/projects/${id}/edges`),
      api.get<RecentResp>(`/api/projects/${id}/executions/by-stage/recent`),
    ]);
    setStages(st);
    setNodes(
      st.map((s) => ({
        id: String(s.id),
        type: "stage",
        position: { x: s.pos_x, y: s.pos_y },
        draggable: false,
        data: {
          label: s.name,
          type: s.type,
          dots: recent.stages[s.id] || [],
          pending: s.type === "script" ? recent.pending : undefined,
          avg: Math.round((recent.avg_seconds / 60) * 10) / 10,
          onDot: (execId: string) => setSelectedExec(execId),
        },
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
  }, [id, setNodes, setEdges]);

  useEffect(() => {
    refresh();
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(
      `${proto}://${location.host}/ws/projects/${id}?token=${getToken() ?? ""}`
    );
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "execution") refresh();
    };
    return () => ws.close();
  }, [id, refresh]);

  return (
    <ProjectLayout project={project}>
      <div className="relative h-full">
        <div className="absolute left-0 right-0 top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-white/90 px-4 py-2 backdrop-blur">
          <div>
            <h1 className="font-semibold text-brand-900">Monitor do Workflow</h1>
            <p className="text-xs text-slate-500">
              Atualiza em tempo real via WebSocket
            </p>
          </div>
          <Link to={`/projects/${id}/editor`} className="btn-primary py-1.5 text-sm">
            Editar projeto
          </Link>
        </div>
        <div className="h-full pt-14">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            fitView
          >
            <Background variant={BackgroundVariant.Dots} gap={18} size={1.5} color="#cbd5e1" />
            <Controls />
          </ReactFlow>
        </div>

        {selectedExec && (
          <ExecutionDrawer
            projectId={id}
            executionId={selectedExec}
            onClose={() => setSelectedExec(null)}
          />
        )}
      </div>
    </ProjectLayout>
  );
}

function ExecutionDrawer({
  projectId,
  executionId,
  onClose,
}: {
  projectId: number;
  executionId: string;
  onClose: () => void;
}) {
  const [exec, setExec] = useState<any>(null);
  useEffect(() => {
    api
      .get(`/api/projects/${projectId}/executions/${executionId}`)
      .then(setExec);
  }, [projectId, executionId]);
  return (
    <div className="absolute bottom-0 right-0 top-14 z-20 w-[460px] overflow-auto border-l border-slate-200 bg-white shadow-xl">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-2">
        <span className="font-mono text-xs text-slate-500">{executionId}</span>
        <button onClick={onClose} className="btn-ghost px-2 py-1">
          ✕
        </button>
      </div>
      {exec && (
        <div className="space-y-3 p-4 text-sm">
          <div>
            <span className="text-slate-400">Etapa:</span> {exec.stage_name} (
            {exec.stage_type})
          </div>
          <div>
            <span className="text-slate-400">Status:</span> {exec.status}
          </div>
          <div>
            <div className="mb-1 text-xs font-semibold uppercase text-slate-400">
              stdout
            </div>
            <pre className="max-h-48 overflow-auto rounded bg-slate-900 p-2 text-xs text-emerald-200">
              {exec.stdout || "(vazio)"}
            </pre>
          </div>
          {exec.stderr && (
            <div>
              <div className="mb-1 text-xs font-semibold uppercase text-red-400">
                stderr
              </div>
              <pre className="max-h-48 overflow-auto rounded bg-slate-900 p-2 text-xs text-red-300">
                {exec.stderr}
              </pre>
            </div>
          )}
          <div>
            <div className="mb-1 text-xs font-semibold uppercase text-slate-400">
              output
            </div>
            <pre className="overflow-auto rounded bg-slate-50 p-2 text-xs">
              {JSON.stringify(exec.output_data, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
