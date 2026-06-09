import { Handle, Position } from "reactflow";
import { STAGE_META, StageIcon } from "./ui";
import type { StageType } from "../lib/types";

export interface NodeData {
  label: string;
  type: StageType;
  selected?: boolean;
  dots?: { id: string; status: string }[];
  pending?: number;
  avg?: number;
  onDot?: (executionId: string) => void;
}

const DOT_COLOR: Record<string, string> = {
  success: "#10b981",
  running: "#f59e0b",
  error: "#ef4444",
  queued: "#cbd5e1",
};

function NodeShell({ data }: { data: NodeData }) {
  const meta = STAGE_META[data.type];
  return (
    <div
      className="min-w-[170px] rounded-xl border-2 bg-white px-3 py-2 shadow-sm"
      style={{ borderColor: meta.color }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: meta.color, width: 12, height: 12, border: "2px solid white" }}
      />
      <div className="flex items-center gap-2">
        <span
          className="flex h-7 w-7 items-center justify-center rounded-lg text-white"
          style={{ background: meta.color }}
        >
          <StageIcon type={data.type} className="h-4 w-4" />
        </span>
        <div className="leading-tight">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
            {meta.label}
          </div>
          <div className="text-sm font-medium text-brand-900">{data.label}</div>
        </div>
      </div>
      {data.dots && (
        <div className="mt-2 flex items-center gap-1.5">
          {data.dots.length === 0 && (
            <span className="text-[10px] text-slate-400">sem execuções</span>
          )}
          {data.dots.map((d) => (
            <button
              key={d.id}
              title={`${d.status} · ${d.id.slice(0, 8)}`}
              onClick={() => data.onDot?.(d.id)}
              className="h-3 w-3 rounded-full ring-1 ring-white"
              style={{ background: DOT_COLOR[d.status] || "#cbd5e1" }}
            />
          ))}
        </div>
      )}
      {data.type === "script" && data.pending !== undefined && (
        <div className="mt-2">
          <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full bg-accent-500 transition-all"
              style={{ width: data.pending > 0 ? "70%" : "0%" }}
            />
          </div>
          <div className="mt-1 text-[10px] text-slate-500">
            {data.pending} tarefa(s) pendente(s) ({data.avg ?? 0}m média)
          </div>
        </div>
      )}
      <Handle
        type="source"
        position={Position.Right}
        style={{ background: meta.color, width: 12, height: 12, border: "2px solid white" }}
      />
    </div>
  );
}

export const nodeTypes = { stage: NodeShell };
