import type { StageType } from "../lib/types";

export function Logo({ light = false }: { light?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <svg viewBox="0 0 64 64" className="h-7 w-7">
        <rect width="64" height="64" rx="14" fill={light ? "#ffffff" : "#0a1f33"} />
        <circle cx="20" cy="22" r="6" fill="#18b1a8" />
        <circle cx="44" cy="22" r="6" fill="#1f6fb2" />
        <circle cx="32" cy="44" r="6" fill="#2dd4c4" />
        <path
          d="M20 22 L44 22 M44 22 L32 44 M20 22 L32 44"
          stroke="#4a80c2"
          strokeWidth="3"
          fill="none"
          strokeLinecap="round"
        />
      </svg>
      <span
        className={`text-lg font-bold tracking-tight ${
          light ? "text-white" : "text-brand-900"
        }`}
      >
        Flow<span className="text-accent-500">Desk</span>
      </span>
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    live: "bg-emerald-100 text-emerald-700",
    draft: "bg-slate-100 text-slate-600",
    inactive: "bg-slate-100 text-slate-500",
    failed: "bg-orange-100 text-orange-700",
    success: "bg-emerald-100 text-emerald-700",
    running: "bg-amber-100 text-amber-700",
    error: "bg-red-100 text-red-700",
    queued: "bg-slate-100 text-slate-600",
  };
  const label: Record<string, string> = {
    live: "No ar",
    draft: "Rascunho",
    inactive: "Inativo",
    failed: "Falhou",
    success: "Sucesso",
    running: "Em andamento",
    error: "Erro",
    queued: "Na fila",
  };
  return (
    <span className={`badge ${map[status] || "bg-slate-100 text-slate-600"}`}>
      {label[status] || status}
    </span>
  );
}

const ICONS: Record<StageType, JSX.Element> = {
  form: (
    <path d="M4 4h16v16H4z M8 9h8 M8 13h8 M8 17h5" strokeWidth="1.7" fill="none" />
  ),
  script: <path d="M8 4l-4 8 4 8 M16 4l4 8-4 8" strokeWidth="1.7" fill="none" />,
  job: (
    <>
      <circle cx="12" cy="12" r="8" strokeWidth="1.7" fill="none" />
      <path d="M12 8v4l3 2" strokeWidth="1.7" fill="none" />
    </>
  ),
  hook: (
    <path
      d="M18 6a3 3 0 1 0-6 0v8a3 3 0 1 1-6 0"
      strokeWidth="1.7"
      fill="none"
    />
  ),
  agent: (
    <>
      <rect x="5" y="8" width="14" height="11" rx="2" strokeWidth="1.7" fill="none" />
      <path d="M12 8V4 M9 13h.01 M15 13h.01" strokeWidth="1.7" fill="none" />
    </>
  ),
};

export const STAGE_META: Record<StageType, { label: string; color: string }> = {
  form: { label: "Form", color: "#1f6fb2" },
  script: { label: "Script", color: "#18b1a8" },
  job: { label: "Job", color: "#8b5cf6" },
  hook: { label: "Hook", color: "#f59e0b" },
  agent: { label: "Agent", color: "#ec4899" },
};

export function StageIcon({
  type,
  className = "h-5 w-5",
}: {
  type: StageType;
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {ICONS[type]}
    </svg>
  );
}

export function Spinner({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.2" strokeWidth="4" />
      <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}
