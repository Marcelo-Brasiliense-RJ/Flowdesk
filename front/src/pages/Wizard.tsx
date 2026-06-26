import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { motion, AnimatePresence, useReducedMotion, type Variants } from "framer-motion";
import { api, getToken } from "../lib/api";
import { useAuth } from "../lib/auth";
import type {
  ClassificacaoReviewData,
  Execution,
  InputKind,
  OutputKind,
  Project,
  Stage,
  StageType,
  TriggerKind,
  WizardField,
  WizardState,
} from "../lib/types";
import { Logo, Spinner, StageIcon, STAGE_META } from "../components/ui";
import OcrReview from "../components/OcrReview";
import ProgressTimeline from "../components/ProgressTimeline";
import ClassificacaoReview from "../components/ClassificacaoReview";

const STEPS = ["Gatilho", "Entrada", "Processamento", "Resultado", "Revisão"];

/* ---------- ícones (SVG, nunca emoji) ---------- */
type StepIcon = (props: { className?: string }) => JSX.Element;

const svgProps = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

const TriggerIcon: StepIcon = ({ className }) => (
  <svg {...svgProps} className={className} aria-hidden>
    <path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z" />
  </svg>
);
const InputIcon: StepIcon = ({ className }) => (
  <svg {...svgProps} className={className} aria-hidden>
    <path d="M14 3v4a1 1 0 0 0 1 1h4" />
    <path d="M5 3h9l5 5v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" />
    <path d="M12 17v-6m0 0-2.5 2.5M12 11l2.5 2.5" />
  </svg>
);
const ProcessIcon: StepIcon = ({ className }) => (
  <svg {...svgProps} className={className} aria-hidden>
    <path d="M12 3l1.8 4.7L18.5 9l-4.7 1.8L12 15l-1.8-4.2L5.5 9l4.7-1.3L12 3z" />
    <path d="M19 14l.7 1.8L21.5 16l-1.8.7L19 18l-.7-1.3L16.5 16l1.8-.2L19 14z" />
  </svg>
);
const OutputIcon: StepIcon = ({ className }) => (
  <svg {...svgProps} className={className} aria-hidden>
    <path d="M12 3v11m0 0 4-4m-4 4-4-4" />
    <path d="M5 21h14" />
  </svg>
);
const ReviewIcon: StepIcon = ({ className }) => (
  <svg {...svgProps} className={className} aria-hidden>
    <circle cx="12" cy="12" r="9" />
    <path d="M8.5 12.5l2.5 2.5 4.5-5" />
  </svg>
);
const CheckIcon: StepIcon = ({ className }) => (
  <svg {...svgProps} className={className} aria-hidden>
    <path d="M5 13l4 4L19 7" />
  </svg>
);

const STEP_ICONS: StepIcon[] = [TriggerIcon, InputIcon, ProcessIcon, OutputIcon, ReviewIcon];

/* ---------- stepper vertical (desktop) ---------- */
/* ---------- progresso horizontal (layout do design) ---------- */
function StepProgress({ step, plan }: { step: number; plan: AnalyzePlan | null }) {
  // trilho preenchido: os círculos ficam centrados de 10% a 90% (vão 80%)
  const fillW = (Math.min(step, STEPS.length - 1) / (STEPS.length - 1)) * 80;
  return (
    <div className="card mb-6 p-5">
      <div className="mb-5 flex items-center justify-between">
        <span className="text-[11px] font-bold uppercase tracking-wide text-ink3">
          Montagem da automação
        </span>
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-accentv">
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ background: "var(--accent)", animation: "pulse 1.4s infinite" }}
          />
          {step >= STEPS.length - 1 ? "Pronta para testar" : "Em montagem"}
        </span>
      </div>
      <div className="relative flex items-start justify-between">
        {/* trilho base */}
        <div
          className="absolute left-[10%] right-[10%] top-[15px] h-[3px] rounded-full"
          style={{ background: "var(--border)" }}
        />
        {/* trilho preenchido */}
        <motion.div
          className="absolute left-[10%] top-[15px] h-[3px] rounded-full"
          style={{ background: "linear-gradient(90deg, var(--brand), var(--accent))" }}
          animate={{ width: `${fillW}%` }}
          transition={{ type: "spring", stiffness: 120, damping: 24 }}
        />
        {STEPS.map((label, i) => {
          const dimKey = (["trigger", "input", "process", "output"] as const)[i];
          const confident = i < 4 && (plan?.[dimKey] as DimPlan)?.confident;
          const done = i < step || (!!confident && i !== step);
          const current = i === step;
          return (
            <div
              key={label}
              className="relative z-10 flex flex-1 flex-col items-center gap-2.5"
            >
              <span
                className="flex h-8 w-8 items-center justify-center rounded-full border-2 text-[12.5px] font-bold transition"
                style={
                  done
                    ? { background: "var(--accent)", borderColor: "var(--accent)", color: "#fff" }
                    : current
                    ? {
                        background: "var(--surface)",
                        borderColor: "var(--accent)",
                        color: "var(--accent)",
                        boxShadow: "0 0 0 4px var(--accent-soft)",
                      }
                    : { background: "var(--surface-2)", borderColor: "var(--border)", color: "var(--text-3)" }
                }
              >
                {done ? <CheckIcon className="h-4 w-4" /> : i + 1}
              </span>
              <span
                className="text-center text-[12.5px] leading-tight"
                style={{
                  fontWeight: current ? 700 : 500,
                  color: current ? "var(--text)" : "var(--text-3)",
                }}
              >
                {label}
              </span>
            </div>
          );
        })}
      </div>
      <div
        className="mt-5 rounded-xl px-3.5 py-3 text-center text-[12.5px] leading-relaxed text-ink3"
        style={{ background: "var(--surface-2)" }}
      >
        Nada é publicado sem você testar antes. Você pode abrir o modo avançado a qualquer momento.
      </div>
    </div>
  );
}

interface DimPlan {
  kind?: string | null;
  description?: string | null;
  confident?: boolean;
  question?: string | null;
  fields?: WizardField[];
}
interface AnalyzePlan {
  summary?: string;
  trigger?: DimPlan;
  input?: DimPlan;
  process?: DimPlan;
  output?: DimPlan;
  ai_enabled?: boolean;
}
interface BuildResult {
  explanation: string;
  script_file: string;
  stage_ids: { input?: number; script?: number; result?: number; trigger?: number };
  ai_enabled: boolean;
}

/**
 * Reconstrói o rascunho do assistente a partir dos nós reais do projeto, para
 * quando o fluxo foi montado fora do wizard (Chat / modo avançado) e não há
 * `wizard_state`. Prefere o rascunho salvo quando existir.
 */
function deriveBuiltState(ws: WizardState, stages: Stage[]): WizardState {
  const inputForm = stages.find((s) => s.type === "form" && s.config?.mode === "input");
  const resultForm = stages.find((s) => s.type === "form" && s.config?.mode === "result");
  const scriptStage = stages.find((s) => s.type === "script" || s.type === "agent");
  const jobStage = stages.find((s) => s.type === "job");
  const hookStage = stages.find((s) => s.type === "hook");

  const fields = (inputForm?.config?.fields ?? []) as Array<{ label?: string; type?: string }>;
  const hasFile = fields.some((f) => f.type === "file");
  const inputKind: InputKind = !inputForm ? "none" : hasFile ? "file" : fields.length ? "fields" : "none";
  const triggerKind: TriggerKind = jobStage ? "schedule" : hookStage ? "webhook" : "manual";
  const outputKind: OutputKind = resultForm?.config?.result_file_key ? "download" : "summary";

  return {
    trigger: ws.trigger ?? { kind: triggerKind },
    input:
      ws.input ?? {
        kind: inputKind,
        fields:
          inputKind === "fields"
            ? fields.map((f) => ({
                label: f.label ?? "",
                type: (f.type ?? "text") as WizardField["type"],
              }))
            : [],
      },
    process: ws.process ?? { description: (scriptStage?.config?.description as string) || "" },
    output: ws.output ?? { kind: outputKind },
  };
}

/**
 * Assistente prompt-aware: o usuário descreve o que quer, a IA lê o pedido (e o
 * arquivo de exemplo), preenche o que já dá pra deduzir e só pergunta o que falta.
 * As 4 etapas viram confirmação/ajuste; se a IA entende tudo, pula para a Revisão.
 */
export default function Wizard() {
  const { id } = useParams();
  const projectId = Number(id);
  const { user } = useAuth();
  const canManage = !!(user?.is_admin || user?.is_dev);
  const [project, setProject] = useState<Project | null>(null);
  // step -1 = tela "Descreva"; 0..4 = trilha
  const [step, setStep] = useState(-1);
  const [state, setState] = useState<WizardState>({});
  const [plan, setPlan] = useState<AnalyzePlan | null>(null);

  const [prompt, setPrompt] = useState("");
  const [sampleFile, setSampleFile] = useState("");
  const [sampleName, setSampleName] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState("");

  const [building, setBuilding] = useState(false);
  const [build, setBuild] = useState<BuildResult | null>(null);
  const [buildError, setBuildError] = useState("");
  const [dismissedDirty, setDismissedDirty] = useState(false);

  const reduce = useReducedMotion();
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    Promise.all([
      api.get<Project>(`/api/projects/${projectId}`),
      api.get<Stage[]>(`/api/projects/${projectId}/stages`),
    ]).then(([p, stages]) => {
      setProject(p);
      const ws = (p.wizard_state || {}) as WizardState;
      const scriptStage = stages.find((s) => s.type === "script" || s.type === "agent");
      // o fluxo pode ter sido montado pelo assistente (_built) OU pelo Chat/modo
      // avançado (sem _built). Reconhecer pela presença real de nós evita reabrir
      // a tela inicial como se a automação não existisse.
      const alreadyBuilt = (ws as any)._built || !!scriptStage;
      if (!alreadyBuilt) return;
      const derived = deriveBuiltState(ws, stages);
      setState(derived);
      // fluxo criado pelo Chat: o "o que faz" vem do pedido original da conversa,
      // não de um texto genérico tipo "Criado pelo Chat"
      if (!derived.process?.description?.trim()) {
        api
          .get<{ role: string; content: string }[]>(`/api/projects/${projectId}/chat`)
          .then((msgs) => {
            const first = msgs.find((m) => m.role === "user")?.content || "";
            const pedido = first.split("[Arquivos anexados:")[0].trim();
            if (pedido) {
              setState((s) => ({ ...s, process: { description: pedido.slice(0, 240) } }));
            }
          })
          .catch(() => {});
      }
      const ids = ((ws as any)._stage_ids || {}) as BuildResult["stage_ids"];
      const inputForm = stages.find((s) => s.type === "form" && s.config?.mode === "input");
      const resultForm = stages.find((s) => s.type === "form" && s.config?.mode === "result");
      setBuild({
        // descrição persistida; se vazia, o card gera ou pede ao usuário
        explanation: ((ws as any)._explanation as string) || "",
        script_file: scriptStage?.entry_file || "",
        stage_ids: {
          input: ids.input ?? inputForm?.id,
          script: ids.script ?? scriptStage?.id,
          result: ids.result ?? resultForm?.id,
          trigger: ids.trigger,
        },
        ai_enabled: false,
      });
      setStep(4);
    });
  }, [projectId]);

  async function persist(next: WizardState, stepIdx: number) {
    setState(next);
    await api.put(`/api/projects/${projectId}/wizard`, {
      state: { ...next, step: stepIdx },
      dirty: false,
    });
  }

  async function uploadSample(file: File) {
    const fd = new FormData();
    fd.append("path", "uploads");
    fd.append("file", file);
    const r = await api.postForm<{ name: string }>(`/api/projects/${projectId}/fs/upload`, fd);
    setSampleFile(`uploads/${r.name}`);
    setSampleName(r.name);
    return `uploads/${r.name}`;
  }

  async function analyze() {
    if (!prompt.trim() && !sampleFile) return;
    setAnalyzing(true);
    setAnalyzeError("");
    try {
      const p = await api.post<AnalyzePlan>(`/api/projects/${projectId}/wizard/analyze`, {
        prompt: prompt.trim(),
        sample_file: sampleFile || null,
      });
      setPlan(p);
      const next: WizardState = {
        trigger: { kind: (p.trigger?.kind as TriggerKind) || "manual" },
        input: {
          kind: (p.input?.kind as InputKind) || "file",
          fields: p.input?.fields || [],
          sample_file: sampleFile || undefined,
        },
        process: { description: p.process?.description || prompt.trim() },
        output: { kind: (p.output?.kind as OutputKind) || "download" },
      };
      const dims: [keyof AnalyzePlan, number][] = [
        ["trigger", 0], ["input", 1], ["process", 2], ["output", 3],
      ];
      const gap = dims.find(([k]) => !(p[k] as DimPlan)?.confident);
      const target = gap ? gap[1] : 4;
      await persist(next, target);
      setStep(target);
      if (target === 4) buildFlow();
    } catch (e: any) {
      setAnalyzeError(e?.message || "Não consegui analisar o pedido. Tente de novo.");
    } finally {
      setAnalyzing(false);
    }
  }

  function patch(partial: Partial<WizardState>) {
    setState((s) => ({ ...s, ...partial }));
  }

  async function buildFlow() {
    setBuilding(true);
    setBuildError("");
    try {
      const res = await api.post<BuildResult>(`/api/projects/${projectId}/wizard/build`);
      setBuild(res);
    } catch (e: any) {
      setBuildError(e?.message || "Falha ao montar a automação.");
    } finally {
      setBuilding(false);
    }
  }

  async function handleContinue() {
    const next = step + 1;
    await persist(state, next);
    setStep(next);
    if (next === 4) buildFlow();
  }

  if (!project)
    return (
      <div className="flex h-full items-center justify-center text-accentv">
        <Spinner className="h-8 w-8" />
      </div>
    );

  const canAdvance =
    (step === 0 && !!state.trigger?.kind) ||
    (step === 1 && !!state.input?.kind) ||
    (step === 2 && !!state.process?.description?.trim()) ||
    (step === 3 && !!state.output?.kind);

  const renderStep = () => {
    switch (step) {
      case 0:
        return <TriggerStep state={state} patch={patch} plan={plan?.trigger} />;
      case 1:
        return <InputStep state={state} patch={patch} plan={plan?.input} />;
      case 2:
        return <ProcessStep state={state} patch={patch} plan={plan?.process} />;
      case 3:
        return <OutputStep state={state} patch={patch} plan={plan?.output} />;
      case 4:
        return (
          <ReviewStep
            projectId={projectId}
            projectName={project.name}
            projectDescription={project.description}
            state={state}
            building={building}
            build={build}
            buildError={buildError}
            onRebuild={buildFlow}
          />
        );
      default:
        return null;
    }
  };

  return (
    <div className="flex h-full flex-col" style={{ background: "var(--bg)" }}>
      <header className="glass flex items-center justify-between border-b border-line px-4 py-2">
        <div className="flex items-center gap-2">
          <Link to="/" className="shrink-0">
            <Logo />
          </Link>
          <span className="text-ink3">/</span>
          <span className="font-semibold text-ink">{project.name}</span>
          <span className="badge" style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>Assistente</span>
        </div>
        {canManage && (
          <Link
            to={`/projects/${projectId}/editor`}
            className="text-xs text-ink3 transition hover:text-accentv"
            title="Editar o código e o fluxo diretamente"
          >
            Modo avançado →
          </Link>
        )}
      </header>

      {project.wizard_dirty && !dismissedDirty && (
        <div
          className="flex flex-wrap items-center gap-3 border-b px-6 py-2.5 text-sm"
          style={{ borderColor: "var(--warn2-soft)", background: "var(--warn2-soft)" }}
        >
          <span style={{ color: "var(--warn2)" }}>
            Esta automação foi ajustada manualmente no modo avançado. Editar pelo
            assistente pode sobrescrever esses ajustes.
          </span>
          <button onClick={() => setDismissedDirty(true)} className="btn-outline py-1 text-xs">
            Continuar mesmo assim
          </button>
          {canManage && (
            <Link
              to={`/projects/${projectId}/editor`}
              className="text-xs font-medium hover:underline"
              style={{ color: "var(--warn2)" }}
            >
              Abrir no modo avançado
            </Link>
          )}
        </div>
      )}

      {step === -1 ? (
        <div className="min-h-0 flex-1 overflow-auto p-8">
          <div className="mx-auto max-w-2xl">
            <DescribeStep
              prompt={prompt}
              setPrompt={setPrompt}
              sampleName={sampleName}
              onUpload={uploadSample}
              onAnalyze={analyze}
              analyzing={analyzing}
              error={analyzeError}
              taRef={taRef}
            />
          </div>
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-auto p-6 lg:p-10" style={{ background: "var(--bg)" }}>
          <div className={`mx-auto ${step === 4 ? "max-w-5xl" : "max-w-3xl"}`}>
            <StepProgress step={step} plan={plan} />
            <AnimatePresence mode="wait">
              <motion.div
                key={step}
                initial={reduce ? false : { opacity: 0, x: 24 }}
                animate={{ opacity: 1, x: 0 }}
                exit={reduce ? undefined : { opacity: 0, x: -24 }}
                transition={{ type: "spring", stiffness: 320, damping: 30 }}
              >
                {renderStep()}
              </motion.div>
            </AnimatePresence>
            <div className="mt-8 flex items-center justify-between">
              <button
                onClick={() => setStep(step - 1)}
                disabled={step === 0}
                className="btn-outline py-1.5 text-sm disabled:opacity-40"
              >
                ← Voltar
              </button>
              <span className="text-xs text-ink3">Etapa {step + 1} de {STEPS.length}</span>
              {step < STEPS.length - 1 ? (
                <button
                  onClick={handleContinue}
                  disabled={!canAdvance}
                  className="btn-primary py-1.5 text-sm disabled:opacity-40"
                >
                  {step === 3 ? "Montar e revisar" : "Continuar"}
                </button>
              ) : (
                <span className="w-24" />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------- Tela 1: Descreva ---------- */

const heroVariants: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.07, delayChildren: 0.04 } },
};
const heroItem: Variants = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 320, damping: 26 } },
};

function DescribeStep({
  prompt, setPrompt, sampleName, onUpload, onAnalyze, analyzing, error, taRef,
}: {
  prompt: string;
  setPrompt: (v: string) => void;
  sampleName: string;
  onUpload: (f: File) => Promise<string>;
  onAnalyze: () => void;
  analyzing: boolean;
  error: string;
  taRef: React.RefObject<HTMLTextAreaElement>;
}) {
  return (
    <motion.div variants={heroVariants} initial="hidden" animate="show" className="pt-4">
      <motion.h1 variants={heroItem} className="text-center text-2xl font-bold text-ink">
        O que você quer automatizar?
      </motion.h1>
      <motion.p variants={heroItem} className="mx-auto mt-2 max-w-lg text-center text-sm text-ink2">
        Descreva em português, com o máximo de detalhe, e anexe um exemplo. Eu leio o seu
        pedido e só pergunto o que realmente faltar.
      </motion.p>

      <motion.div
        variants={heroItem}
        className="card mt-6 p-4"
      >
        <textarea
          ref={taRef}
          autoFocus
          rows={4}
          className="input resize-none border-0 text-base focus:ring-0"
          placeholder="Ex: tenho uma planilha de vendas com as colunas produto e valor; quero o total geral e o total por produto, gerando uma planilha de saída."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) onAnalyze();
          }}
        />
        <div className="mt-3 flex items-center justify-between">
          <label className="btn-outline cursor-pointer py-1.5 text-sm">
            📎 {sampleName ? sampleName : "Anexar exemplo"}
            <input
              type="file"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) onUpload(f);
                e.target.value = "";
              }}
            />
          </label>
          <motion.button
            onClick={onAnalyze}
            disabled={analyzing || (!prompt.trim() && !sampleName)}
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.96 }}
            className="btn-primary disabled:opacity-40"
          >
            {analyzing ? "Analisando…" : "Analisar pedido →"}
          </motion.button>
        </div>
      </motion.div>

      <AnimatePresence>
        {analyzing && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="mt-4 flex items-center justify-center gap-2 text-sm text-ink2"
          >
            <Spinner className="h-4 w-4" /> Lendo seu pedido e montando as etapas…
          </motion.div>
        )}
      </AnimatePresence>
      {error && <p className="mt-3 text-center text-sm text-err">{error}</p>}
      <motion.p variants={heroItem} className="mt-3 text-center text-xs text-ink3">
        Dica: Ctrl/Cmd + Enter para analisar.
      </motion.p>
    </motion.div>
  );
}

/* ---------- Componentes de etapa ---------- */

interface StepProps {
  state: WizardState;
  patch: (partial: Partial<WizardState>) => void;
  plan?: DimPlan;
}

function StepTitle({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="mb-4">
      <h1 className="text-xl font-bold text-ink">{title}</h1>
      <p className="mt-1 text-sm text-ink2">{hint}</p>
    </div>
  );
}

function ConfidentBanner({ text }: { text: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      className="mb-4 flex items-start gap-2 rounded-lg border px-3 py-2 text-sm"
      style={{ borderColor: "var(--ok-soft)", background: "var(--ok-soft)", color: "var(--ok)" }}
    >
      <span className="mt-0.5 font-semibold">Entendi do seu pedido:</span>
      <span>{text}. Pode ajustar abaixo se quiser.</span>
    </motion.div>
  );
}

function QuestionBanner({ text }: { text: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      className="mb-4 rounded-lg border px-3 py-2 text-sm font-medium"
      style={{ borderColor: "var(--accent-soft)", background: "var(--accent-soft)", color: "var(--accent)" }}
    >
      {text}
    </motion.div>
  );
}

function ChoiceCard({
  active, title, desc, onClick,
}: {
  active: boolean;
  title: string;
  desc: string;
  onClick: () => void;
}) {
  return (
    <motion.button
      type="button"
      onClick={onClick}
      whileHover={{ scale: 1.01 }}
      whileTap={{ scale: 0.99 }}
      className="w-full rounded-xl border p-4 text-left transition"
      style={
        active
          ? { borderColor: "var(--accent)", background: "var(--accent-soft)" }
          : { borderColor: "var(--border)", background: "var(--surface)" }
      }
    >
      <div className="font-medium text-ink">{title}</div>
      <div className="mt-0.5 text-sm text-ink2">{desc}</div>
    </motion.button>
  );
}

function TriggerStep({ state, patch, plan }: StepProps) {
  const kind = state.trigger?.kind;
  const set = (k: TriggerKind) => patch({ trigger: { ...state.trigger, kind: k } });
  return (
    <div>
      <StepTitle title="Como essa automação começa?" hint="Escolha o que dispara a execução." />
      {plan?.confident ? (
        <ConfidentBanner text={triggerText(kind)} />
      ) : plan?.question ? (
        <QuestionBanner text={plan.question} />
      ) : null}
      <div className="space-y-3">
        <ChoiceCard active={kind === "manual"} title="Eu mesmo executo"
          desc="A pessoa abre a automação e roda na hora, preenchendo o que for preciso."
          onClick={() => set("manual")} />
        <ChoiceCard active={kind === "schedule"} title="Em um horário"
          desc="Roda sozinha de forma agendada, por exemplo a cada X horas ou todo dia."
          onClick={() => set("schedule")} />
        <ChoiceCard active={kind === "webhook"} title="Quando chega algo de fora"
          desc="Dispara ao receber uma requisição de outro sistema (webhook)."
          onClick={() => set("webhook")} />
      </div>
      {kind === "schedule" && (
        <div className="mt-4 flex items-center gap-2 rounded-lg bg-surface p-3 text-sm">
          <span className="text-ink2">A cada</span>
          <input type="number" min={1} value={state.trigger?.every ?? 1}
            onChange={(e) => patch({ trigger: { kind: "schedule", every: Math.max(1, Number(e.target.value)), unit: state.trigger?.unit ?? "hours" } })}
            className="input w-20" />
          <select value={state.trigger?.unit ?? "hours"}
            onChange={(e) => patch({ trigger: { kind: "schedule", every: state.trigger?.every ?? 1, unit: e.target.value as "hours" | "days" } })}
            className="input w-32">
            <option value="hours">hora(s)</option>
            <option value="days">dia(s)</option>
          </select>
        </div>
      )}
    </div>
  );
}

function InputStep({ state, patch, plan }: StepProps) {
  const kind = state.input?.kind;
  const fields = state.input?.fields ?? [];
  const set = (k: InputKind) => patch({ input: { ...state.input, kind: k } });
  function addField() {
    patch({ input: { kind: "fields", fields: [...fields, { label: "", type: "text" }] } });
  }
  function updateField(i: number, partial: Partial<WizardField>) {
    patch({ input: { kind: "fields", fields: fields.map((f, idx) => (idx === i ? { ...f, ...partial } : f)) } });
  }
  function removeField(i: number) {
    patch({ input: { kind: "fields", fields: fields.filter((_, idx) => idx !== i) } });
  }
  return (
    <div>
      <StepTitle title="O que essa automação recebe?" hint="Define a entrada de dados que será processada." />
      {plan?.confident ? (
        <ConfidentBanner text={inputText(kind, fields.length)} />
      ) : plan?.question ? (
        <QuestionBanner text={plan.question} />
      ) : null}
      <div className="space-y-3">
        <ChoiceCard active={kind === "file"} title="Um arquivo"
          desc="Uma planilha, CSV ou PDF. Você poderá subir um exemplo na hora de testar."
          onClick={() => set("file")} />
        <ChoiceCard active={kind === "fields"} title="Alguns campos digitados"
          desc="A pessoa preenche campos simples antes de rodar." onClick={() => set("fields")} />
        <ChoiceCard active={kind === "none"} title="Nada" desc="A automação não precisa de entrada."
          onClick={() => set("none")} />
      </div>
      {kind === "fields" && (
        <div className="mt-4 space-y-2 rounded-lg bg-surface p-3">
          {fields.length === 0 && <p className="text-sm text-ink3">Nenhum campo ainda.</p>}
          {fields.map((f, i) => (
            <div key={i} className="flex items-center gap-2">
              <input className="input flex-1" placeholder="Rótulo do campo (ex: CNPJ)"
                value={f.label} onChange={(e) => updateField(i, { label: e.target.value })} />
              <select className="input w-32" value={f.type}
                onChange={(e) => updateField(i, { type: e.target.value as WizardField["type"] })}>
                <option value="text">texto</option>
                <option value="number">número</option>
                <option value="date">data</option>
                <option value="select">lista</option>
              </select>
              <button type="button" onClick={() => removeField(i)} className="px-2 text-ink3 hover:text-err">×</button>
            </div>
          ))}
          <button type="button" onClick={addField} className="btn-outline py-1 text-xs">+ Adicionar campo</button>
        </div>
      )}
    </div>
  );
}

function ProcessStep({ state, patch, plan }: StepProps) {
  return (
    <div>
      <StepTitle title="O que fazer com isso?" hint="Descreva o que a automação deve fazer. A IA monta o passo a passo." />
      {plan?.confident ? (
        <ConfidentBanner text="o que você descreveu no pedido" />
      ) : plan?.question ? (
        <QuestionBanner text={plan.question} />
      ) : null}
      <textarea
        className="input min-h-[160px] resize-y"
        placeholder="Ex: remover linhas duplicadas pela coluna Valor; somar por CNPJ e gerar um resumo."
        value={state.process?.description ?? ""}
        onChange={(e) => patch({ process: { description: e.target.value } })}
      />
      <p className="mt-2 text-xs text-ink3">
        Ao continuar, a IA monta a automação e mostra uma explicação. Nada é publicado sem você testar antes.
      </p>
    </div>
  );
}

function OutputStep({ state, patch, plan }: StepProps) {
  const kind = state.output?.kind;
  const set = (k: OutputKind) => patch({ output: { kind: k } });
  return (
    <div>
      <StepTitle title="O que você recebe de volta?" hint="Define o resultado entregue ao final." />
      {plan?.confident ? (
        <ConfidentBanner text={outputText(kind)} />
      ) : plan?.question ? (
        <QuestionBanner text={plan.question} />
      ) : null}
      <div className="space-y-3">
        <ChoiceCard active={kind === "download"} title="Arquivo para baixar"
          desc="Gera um arquivo (ex: Excel) com o resultado para download." onClick={() => set("download")} />
        <ChoiceCard active={kind === "summary"} title="Resumo na tela"
          desc="Mostra um resumo do que foi processado, sem arquivo." onClick={() => set("summary")} />
      </div>
    </div>
  );
}

/* ---------- textos legíveis ---------- */
function triggerText(kind?: TriggerKind) {
  return kind === "schedule" ? "ela roda agendada (em um horário)"
    : kind === "webhook" ? "ela dispara quando chega algo de fora (webhook)"
    : "você executa manualmente";
}
function inputText(kind?: InputKind, n = 0) {
  return kind === "file" ? "ela recebe um arquivo (planilha, PDF ou imagem)"
    : kind === "fields" ? `ela recebe ${n} campo(s) digitado(s)`
    : "ela não recebe entrada";
}
function outputText(kind?: OutputKind) {
  return kind === "download" ? "gera um arquivo para baixar" : "mostra um resumo na tela";
}

/* ---------- Revisão e teste ---------- */

function translateError(stderr: string): string {
  const s = stderr || "";
  const key = s.match(/KeyError:\s*['"]?([^'"\n]+)/);
  if (key) return `A coluna ou campo "${key[1]}" não foi encontrado nos dados.`;
  if (/BadZipFile|not a zip file|openpyxl.*cannot/i.test(s)) return "O arquivo enviado não parece ser um Excel (.xlsx) válido.";
  if (/EmptyDataError|No columns to parse|empty/i.test(s)) return "O arquivo enviado parece estar vazio.";
  if (/FileNotFoundError|No such file/i.test(s)) return "O arquivo de entrada não foi encontrado. Suba um exemplo e tente de novo.";
  if (/could not convert|invalid literal|ValueError/i.test(s)) return "Algum dado veio em um formato inesperado (ex: texto onde se esperava número).";
  if (/ModuleNotFoundError|No module named/i.test(s)) return "A automação depende de um pacote que ainda não está instalado.";
  return "A automação encontrou um erro ao processar. Tente ajustar a descrição na etapa Processamento.";
}

function ReviewStep({
  projectId, projectName, projectDescription, state, building, build, buildError, onRebuild,
}: {
  projectId: number;
  projectName: string;
  projectDescription: string;
  state: WizardState;
  building: boolean;
  build: BuildResult | null;
  buildError: string;
  onRebuild: () => void;
}) {
  // estado de execução do teste, espelhado no fluxo (qual nó está rodando / erro)
  const [flow, setFlow] = useState<{
    active: string | null;
    status: "idle" | "running" | "success" | "error";
  }>({ active: null, status: "idle" });

  // o "Faz" pode vir vazio em fluxos criados fora do assistente: usa a descrição
  // ou o próprio nome do projeto como melhor resumo disponível.
  const descUtil =
    projectDescription?.trim() === "Criado pelo Chat" ? "" : projectDescription?.trim();
  const faz =
    state.process?.description?.trim() ||
    descUtil ||
    projectName?.trim() ||
    "—";
  // etapas do fluxo com explicação amigável por nó
  const inKind = state.input?.kind;
  const flowSteps: FlowStep[] = [];
  if (inKind === "file" || inKind === "fields") {
    flowSteps.push({
      key: "input",
      type: "form",
      name: "Entrada",
      desc:
        inKind === "file"
          ? "Você envia um arquivo (ex: uma planilha) para a automação."
          : `Você preenche ${state.input?.fields?.length ?? 0} campo(s) antes de rodar.`,
    });
  }
  flowSteps.push({
    key: "script",
    type: "script",
    name: "Processamento",
    desc: "Os dados são processados automaticamente por um código que aplica a regra definida.",
    edge: flowSteps.length ? "entrada" : undefined,
  });
  flowSteps.push({
    key: "result",
    type: "form",
    name: "Resultado",
    desc:
      state.output?.kind === "summary"
        ? "Você vê um resumo do que foi processado, direto na tela."
        : "Você baixa o arquivo gerado com o resultado.",
    edge: "resultado",
  });

  return (
    <div>
      <StepTitle
        title="Revisão e teste"
        hint="Rode um teste com dados de exemplo antes de publicar. Abaixo, veja o passo a passo do que a automação faz."
      />

      {/* Visão consolidada: teste domina (2/3), contexto como suporte (1/3) */}
      <div className="grid gap-6 lg:grid-cols-3 lg:items-start">
        {/* AÇÃO PRINCIPAL: teste, com o fluxo logo abaixo */}
        <div className="space-y-6 lg:col-span-2">
          {build?.stage_ids?.script ? (
            <TestPanel
              projectId={projectId}
              scriptStageId={build.stage_ids.script}
              state={state}
              onFlow={(active, status) => setFlow({ active, status })}
            />
          ) : (
            <div
              className="card flex items-center gap-2 p-5 text-sm text-ink3 shadow-token"
              style={{ borderColor: "var(--accent)" }}
            >
              <Spinner className="h-4 w-4" /> Preparando o teste…
            </div>
          )}

          {/* fluxo da automação: passo a passo visual e animado, logo abaixo do teste */}
          <div className="card p-5">
            <div className="mb-4 text-[11px] font-semibold uppercase tracking-wider text-ink3">
              Fluxo da automação
            </div>
            <AutomationFlow steps={flowSteps} activeKey={flow.active} status={flow.status} />
          </div>
        </div>

        {/* COMPLEMENTOS (suporte): contexto da automação, na mesma tela */}
        <aside className="space-y-3 lg:col-span-1">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-ink3">
            Sobre esta automação
          </div>
          {/* o que esta automação faz */}
          <div className="rounded-xl border border-line bg-surface-2 p-4">
            <div className="mb-1.5 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-ink">O que esta automação faz</h3>
              <button onClick={onRebuild} disabled={building}
                className="text-xs text-ink3 hover:text-accentv disabled:opacity-50">
                {building ? "Montando…" : "Montar de novo"}
              </button>
            </div>
            {building ? (
              <div className="flex items-center gap-2 text-sm text-ink3">
                <Spinner className="h-4 w-4" /> Montando a automação…
              </div>
            ) : buildError ? (
              <p className="text-sm text-err">{buildError}</p>
            ) : (
              <AutomationDescription projectId={projectId} initial={build?.explanation || ""} />
            )}
          </div>

          {/* resumo em palavras */}
          <div className="rounded-xl border border-line bg-surface-2 p-4">
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-ink3">
              Resumo em palavras
            </div>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-3">
              <Word term="Começa" desc={capitalize(triggerText(state.trigger?.kind))} />
              <Word term="Recebe" desc={capitalize(inputText(state.input?.kind, state.input?.fields?.length ?? 0))} />
              <Word term="Faz" desc={faz} />
              <Word term="Entrega" desc={capitalize(outputText(state.output?.kind))} />
            </dl>
          </div>
        </aside>
      </div>
    </div>
  );
}

function capitalize(s: string) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

/* ---------- fluxo da automação (passo a passo visual e animado) ---------- */
interface FlowStep {
  key: string;
  type: StageType;
  name: string;
  desc: string;
  edge?: string;
}

const flowContainerV: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.14, delayChildren: 0.05 } },
};
const flowItemV: Variants = {
  hidden: { opacity: 0, y: 16, scale: 0.96 },
  show: { opacity: 1, y: 0, scale: 1, transition: { type: "spring", stiffness: 300, damping: 22 } },
};

type FlowExecStatus = "idle" | "running" | "success" | "error";

function AutomationFlow({
  steps,
  activeKey = null,
  status = "idle",
}: {
  steps: FlowStep[];
  activeKey?: string | null;
  status?: FlowExecStatus;
}) {
  const reduce = useReducedMotion();
  const activeIdx = activeKey ? steps.findIndex((s) => s.key === activeKey) : -1;

  function stepState(idx: number): "idle" | "running" | "done" | "error" {
    if (status === "idle" || activeIdx < 0) return "idle";
    if (status === "error") return idx === activeIdx ? "error" : idx < activeIdx ? "done" : "idle";
    if (status === "success") return "done";
    return idx < activeIdx ? "done" : idx === activeIdx ? "running" : "idle";
  }

  return (
    <motion.div
      variants={reduce ? undefined : flowContainerV}
      initial={reduce ? false : "hidden"}
      animate="show"
      className="flex flex-col gap-2 lg:flex-row lg:items-stretch lg:gap-0"
    >
      {steps.map((s, i) => {
        const meta = STAGE_META[s.type];
        const st = stepState(i);
        const ring =
          st === "done"
            ? "ring-2 ring-emerald-300"
            : st === "error"
            ? "ring-2 ring-red-300"
            : "";
        return (
          <div key={s.key} className="flex flex-col lg:min-w-0 lg:flex-1 lg:flex-row lg:items-stretch">
            {i > 0 && <FlowArrow label={s.edge} active={st === "running" || st === "done" || st === "error"} />}
            <motion.div
              variants={reduce ? undefined : flowItemV}
              className={`relative flex w-full flex-col gap-2 rounded-xl border-2 bg-surface p-3 shadow-token-sm lg:min-w-0 lg:flex-1 ${ring}`}
              style={{ borderColor: meta.color }}
            >
              {st === "running" && (
                <motion.span
                  className="pointer-events-none absolute inset-0 rounded-xl ring-4 ring-accent-400/70"
                  animate={reduce ? undefined : { opacity: [0.35, 1, 0.35] }}
                  transition={{ repeat: Infinity, duration: 1.2 }}
                  aria-hidden
                />
              )}
              {st !== "idle" && (
                <span
                  className={`absolute -right-2 -top-2 z-10 flex h-5 w-5 items-center justify-center rounded-full text-white shadow ${
                    st === "done" ? "bg-emerald-500" : st === "error" ? "bg-red-500" : "bg-accent-500"
                  }`}
                  title={st === "done" ? "Concluído" : st === "error" ? "Erro nesta etapa" : "Executando…"}
                >
                  {st === "done" ? (
                    <CheckIcon className="h-3 w-3" />
                  ) : st === "error" ? (
                    <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" aria-hidden>
                      <path d="M6 6l12 12M18 6L6 18" />
                    </svg>
                  ) : (
                    <Spinner className="h-3 w-3" />
                  )}
                </span>
              )}
              <div className="flex items-center gap-2">
                <span
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-white"
                  style={{ background: meta.color }}
                >
                  <StageIcon type={s.type} className="h-4 w-4" />
                </span>
                <div className="leading-tight">
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-ink3">
                    {meta.label}
                  </div>
                  <div className="text-sm font-medium text-ink">{s.name}</div>
                </div>
              </div>
              <p className="text-xs leading-relaxed text-ink2">{s.desc}</p>
            </motion.div>
          </div>
        );
      })}
    </motion.div>
  );
}

function FlowArrow({ label, active = false }: { label?: string; active?: boolean }) {
  return (
    <div className="flex shrink-0 items-center justify-center gap-1 py-1 lg:flex-col lg:px-3 lg:py-0">
      {label && (
        <span className={`whitespace-nowrap text-[10px] font-medium ${active ? "text-accentv" : "text-ink3"}`}>
          {label}
        </span>
      )}
      <svg
        viewBox="0 0 24 24"
        className={`h-4 w-6 rotate-90 lg:rotate-0 ${active ? "text-accentv" : "text-ink3"}`}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
      >
        <path d="M3 12h15" strokeDasharray="2 3" />
        <path d="M14 6l6 6-6 6" />
      </svg>
    </div>
  );
}

function Word({ term, desc, className = "" }: { term: string; desc: string; className?: string }) {
  return (
    <div className={className}>
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-ink3">{term}</dt>
      <dd className="mt-0.5 whitespace-pre-wrap text-sm leading-relaxed text-ink2">{desc}</dd>
    </div>
  );
}

/* ---------- descrição "o que esta automação faz" (sempre presente) ---------- */
function AutomationDescription({ projectId, initial }: { projectId: number; initial: string }) {
  const [text, setText] = useState(initial.trim());
  const [draft, setDraft] = useState("");
  const [mode, setMode] = useState<"view" | "edit" | "generating" | "ask">(
    initial.trim() ? "view" : "generating"
  );
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (initial.trim()) return; // já há descrição persistida
    let active = true;
    api
      .post<{ description: string }>(`/api/projects/${projectId}/wizard/describe`)
      .then((r) => {
        if (!active) return;
        if (r.description?.trim()) {
          setText(r.description.trim());
          setMode("view");
        } else {
          setMode("ask"); // sem dados para gerar: o usuário precisa descrever
        }
      })
      .catch(() => active && setMode("ask"));
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function save() {
    const value = draft.trim();
    if (!value) return;
    setSaving(true);
    try {
      await api.put(`/api/projects/${projectId}/wizard/explanation`, { text: value });
      setText(value);
      setMode("view");
    } finally {
      setSaving(false);
    }
  }

  if (mode === "generating") {
    return (
      <div className="flex items-center gap-2 text-sm text-ink3">
        <Spinner className="h-4 w-4" /> Gerando a descrição da automação…
      </div>
    );
  }

  if (mode === "view") {
    return (
      <div>
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink2">{text}</p>
        <button
          onClick={() => {
            setDraft(text);
            setMode("edit");
          }}
          className="mt-2 text-xs font-medium text-accentv hover:brightness-110"
        >
          Editar descrição
        </button>
      </div>
    );
  }

  return (
    <div>
      {mode === "ask" && (
        <p className="mb-2 text-sm" style={{ color: "var(--warn2)" }}>
          Não consegui descrever esta automação automaticamente. Descreva, em uma ou duas
          frases, o que ela faz.
        </p>
      )}
      <textarea
        autoFocus
        rows={3}
        className="input resize-y text-sm"
        placeholder="Ex: recebe uma planilha de vendas, soma os valores por produto e gera uma planilha com os totais."
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
      />
      <div className="mt-2 flex items-center gap-2">
        <button
          onClick={save}
          disabled={saving || !draft.trim()}
          className="btn-primary py-1.5 text-sm disabled:opacity-40"
        >
          {saving ? "Salvando…" : "Salvar descrição"}
        </button>
        {mode === "edit" && (
          <button onClick={() => setMode("view")} className="btn-ghost py-1.5 text-sm">
            Cancelar
          </button>
        )}
      </div>
    </div>
  );
}

function TestPanel({
  projectId, scriptStageId, state, onFlow,
}: {
  projectId: number;
  scriptStageId: number;
  state: WizardState;
  onFlow?: (active: string | null, status: "idle" | "running" | "success" | "error") => void;
}) {
  const [samplePath, setSamplePath] = useState(state.input?.sample_file ?? "");
  const [sampleName, setSampleName] = useState(state.input?.sample_file?.split("/").pop() ?? "");
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [testing, setTesting] = useState(false);
  const [exec, setExec] = useState<Execution | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [published, setPublished] = useState(false);
  const [correctedText, setCorrectedText] = useState("");

  const inputKind = state.input?.kind ?? "none";
  const fields = state.input?.fields ?? [];
  const passed = exec?.status === "success";

  // conveniência: se já existe um arquivo em uploads/, pré-seleciona o mais
  // recente em vez de obrigar a pessoa a subir de novo o que acabou de enviar.
  useEffect(() => {
    if (inputKind !== "file" || samplePath) return;
    api
      .get<{ entries: { name: string; path: string; is_dir: boolean; modified_at: string }[] }>(
        `/api/projects/${projectId}/fs?path=uploads`
      )
      .then((r) => {
        const arquivos = (r.entries || []).filter((e) => !e.is_dir);
        if (!arquivos.length) return;
        const ultimo = [...arquivos].sort((a, b) =>
          (b.modified_at || "").localeCompare(a.modified_at || "")
        )[0];
        setSamplePath(ultimo.path);
        setSampleName(ultimo.name);
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inputKind, projectId]);

  async function uploadSample(file: File) {
    const fd = new FormData();
    fd.append("path", "uploads");
    fd.append("file", file);
    const r = await api.postForm<{ name: string }>(`/api/projects/${projectId}/fs/upload`, fd);
    setSamplePath(`uploads/${r.name}`);
    setSampleName(r.name);
  }
  function buildPayload(): Record<string, unknown> {
    const texto = correctedText.trim();
    const extra = texto ? { _texto_corrigido: texto } : {};
    if (inputKind === "file") return samplePath ? { arquivo: samplePath, ...extra } : { ...extra };
    if (inputKind === "fields") return { ...fieldValues, ...extra };
    return { ...extra };
  }
  async function runTest(extra?: Record<string, unknown> | string): Promise<Execution> {
    // compatibilidade: string = texto corrigido do OCR; objeto = payload extra
    const extraPayload: Record<string, unknown> =
      typeof extra === "string" ? { _texto_corrigido: extra } : (extra ?? {});
    if (typeof extra === "string") setCorrectedText(extra);
    setTesting(true);
    setExec(null);
    setReviewed(false);
    // anima a entrada do fluxo e depois o processamento (etapa que de fato executa)
    onFlow?.("input", "running");
    try {
      await new Promise((r) => setTimeout(r, 450));
      onFlow?.("script", "running");
      const started = await api.post<Execution>(`/api/projects/${projectId}/stages/${scriptStageId}/run`, { ...buildPayload(), ...extraPayload });
      let last = started;
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        last = await api.get<Execution>(`/api/projects/${projectId}/executions/${started.id}`);
        setExec(last); // atualiza a linha do tempo ao vivo
        if (last.status === "success" || last.status === "error") break;
      }
      setExec(last);
      onFlow?.(last.status === "success" ? "result" : "script", last.status === "success" ? "success" : "error");
      return last;
    } catch (e: any) {
      const errExec = { status: "error", stderr: e?.message || "Falha ao iniciar o teste." } as Execution;
      setExec(errExec);
      onFlow?.("script", "error");
      return errExec;
    } finally {
      setTesting(false);
    }
  }
  async function publish() {
    setPublishing(true);
    try {
      await api.post(`/api/projects/${projectId}/publish`);
      setPublished(true);
    } finally {
      setPublishing(false);
    }
  }

  const needsSample = inputKind === "file" && !samplePath;
  const finished = exec?.status === "success" || exec?.status === "error";
  const summary = exec?.output_data?.resumo;
  const resultFile = exec?.output_data?.arquivo_resultado as string | undefined;
  const review = exec?.output_data?._ocr_review;
  const classifReview = exec?.output_data?._classificacao_review as
    | ClassificacaoReviewData
    | undefined;
  const [reviewed, setReviewed] = useState(false);
  const [dlError, setDlError] = useState("");
  const [sugestoesIa, setSugestoesIa] = useState<
    Record<string, { conta_codigo: string; confianca: number }>
  >({});
  const blockedByReview = !!review?.needs_review && !reviewed;
  // sucesso "vazio": rodou sem erro mas não extraiu nada (ex: 0 lançamentos).
  // não é um teste de verdade bem-sucedido, então avisamos em vez de comemorar.
  // (pass 1 de revisão de classificação não gera arquivo e não conta como vazio)
  const looksEmpty =
    !classifReview &&
    !!summary &&
    typeof summary === "object" &&
    Object.values(summary).length > 0 &&
    Object.values(summary).every(
      (v) => v === 0 || v === "" || v == null || (Array.isArray(v) && v.length === 0)
    );

  // grupos sem regra ganham sugestão da IA (payload mínimo: padrão + contas)
  useEffect(() => {
    if (!classifReview || exec?.status !== "success") return;
    const semRegra = classifReview.grupos.filter((g) => !g.conta);
    if (semRegra.length === 0) {
      setSugestoesIa({});
      return;
    }
    api
      .post<{ sugestoes: { padrao: string; conta_codigo: string; confianca: number }[] }>(
        `/api/projects/${projectId}/classificar-grupos`,
        {
          grupos: semRegra.map((g) => ({ padrao: g.padrao, tipo: g.tipo })),
          contas: classifReview.contas.map((c) => ({ codigo: c.codigo, nome: c.nome })),
        }
      )
      .then((r) => {
        setSugestoesIa(
          Object.fromEntries(
            r.sugestoes.filter((s) => s.conta_codigo).map((s) => [s.padrao, s])
          )
        );
      })
      .catch(() => setSugestoesIa({}));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classifReview ? exec?.id : null, exec?.status]);

  async function downloadResult(path: string) {
    setDlError("");
    try {
      const res = await fetch(
        `/api/projects/${projectId}/fs/download?path=${encodeURIComponent(path)}`,
        { headers: { Authorization: `Bearer ${getToken()}` } }
      );
      if (!res.ok) {
        setDlError("Não foi possível baixar o arquivo. Rode o teste novamente.");
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = path.split(/[\\/]/).pop() || "resultado";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setDlError("Falha de conexão ao baixar o arquivo.");
    }
  }

  return (
    <div className="card overflow-hidden border-2 shadow-token" style={{ borderColor: "var(--accent)" }}>
      <div className="flex items-center gap-3 border-b border-line px-5 py-3.5" style={{ background: "var(--accent-soft)" }}>
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-white shadow-token-sm" style={{ background: "var(--accent)" }}>
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M6 4l14 8-14 8V4z" />
          </svg>
        </span>
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wider text-accentv">Próximo passo</div>
          <h3 className="text-base font-bold text-ink">Testar com dados de exemplo</h3>
        </div>
      </div>
      <div className="p-5">
      <p className="text-sm text-ink2">
        Rode a automação de verdade antes de publicar. Publicar só fica disponível após um teste bem-sucedido.
      </p>

      {inputKind === "file" && (
        <div className="mt-3 flex items-center gap-2 text-sm">
          <label className="btn-outline cursor-pointer py-1.5 text-xs">
            {sampleName ? `Trocar arquivo (${sampleName})` : "Subir arquivo de exemplo"}
            <input type="file" className="hidden" onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) uploadSample(f);
              e.target.value = "";
            }} />
          </label>
          {sampleName && <span className="text-ok">✓ {sampleName}</span>}
        </div>
      )}
      {inputKind === "fields" && (
        <div className="mt-3 space-y-2">
          {fields.map((f, i) => (
            <div key={i} className="flex items-center gap-2 text-sm">
              <span className="w-40 shrink-0 text-ink2">{f.label || `Campo ${i + 1}`}</span>
              <input className="input" value={fieldValues[f.label] ?? ""}
                onChange={(e) => setFieldValues((v) => ({ ...v, [f.label]: e.target.value }))} />
            </div>
          ))}
        </div>
      )}

      <motion.button onClick={() => runTest()} disabled={testing || needsSample}
        whileTap={{ scale: 0.97 }}
        className="btn-accent mt-4 w-full justify-center py-2.5 text-sm font-semibold shadow-sm disabled:opacity-50 sm:w-auto sm:px-6"
        title={needsSample ? "Suba um arquivo de exemplo primeiro" : ""}>
        {testing ? (
          <>
            <Spinner className="h-4 w-4" /> Testando…
          </>
        ) : (
          <>
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M6 4l14 8-14 8V4z" />
            </svg>
            Testar agora
          </>
        )}
      </motion.button>

      <ProgressTimeline events={exec?.progress ?? []} running={testing} />

      <AnimatePresence>
        {exec && finished && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-4">
            {passed ? (
              <div
                className="rounded-lg border p-3"
                style={
                  looksEmpty
                    ? { borderColor: "var(--warn2-soft)", background: "var(--warn2-soft)" }
                    : { borderColor: "var(--ok-soft)", background: "var(--ok-soft)" }
                }
              >
                <div className="text-sm font-medium" style={{ color: looksEmpty ? "var(--warn2)" : "var(--ok)" }}>
                  {classifReview
                    ? "Extrato lido. Agora revise a classificação abaixo."
                    : looksEmpty
                      ? "O teste rodou, mas o resultado veio vazio"
                      : "Teste concluído com sucesso"}
                </div>
                {looksEmpty && (
                  <p className="mt-1 text-xs" style={{ color: "var(--warn2)" }}>
                    A automação executou sem erro, porém não extraiu nenhum dado do arquivo. Baixe o
                    resultado para conferir e, se estiver vazio mesmo, ajuste a etapa de Processamento
                    (ou abra o modo avançado para ver os detalhes).
                  </p>
                )}
                {summary && (
                  <pre className="mt-2 overflow-auto rounded bg-surface p-2 text-xs text-ink2">
                    {JSON.stringify(summary, null, 2)}
                  </pre>
                )}
                {resultFile && (
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <button
                      onClick={() => downloadResult(resultFile)}
                      className="btn-accent inline-flex items-center gap-1.5 py-1.5 text-xs"
                    >
                      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                        <polyline points="7 10 12 15 17 10" />
                        <line x1="12" y1="15" x2="12" y2="3" />
                      </svg>
                      Baixar resultado ({String(resultFile).split(/[\\/]/).pop()})
                    </button>
                    {dlError && <span className="text-xs text-err">{dlError}</span>}
                  </div>
                )}
              </div>
            ) : (
              <div className="rounded-lg border p-3" style={{ borderColor: "var(--err-soft)", background: "var(--err-soft)" }}>
                <div className="text-sm font-medium text-err">{translateError(exec.stderr || "")}</div>
                <RepairPanel
                  projectId={projectId}
                  scriptStageId={scriptStageId}
                  executionId={exec.id}
                  onRetest={runTest}
                />
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {passed && review && (
        <div className="mt-4">
          <OcrReview
            review={review}
            confirmed={reviewed}
            onConfirm={() => setReviewed(true)}
            onReprocess={(t) => runTest(t)}
          />
        </div>
      )}

      {passed && classifReview && (
        <div className="mt-4">
          <ClassificacaoReview
            key={`${exec?.id}-${Object.keys(sugestoesIa).length}`}
            data={classifReview}
            sugestoesIa={sugestoesIa}
            busy={testing}
            onConfirm={async ({ mapa, contaBanco, periodo, novasRegras }) => {
              if (novasRegras.length) {
                await api
                  .post(`/api/projects/${projectId}/regras-classificacao`, novasRegras)
                  .catch(() => {});
              }
              await runTest({
                _classificacao_confirmada: mapa,
                _conta_banco: contaBanco,
                _periodo: periodo,
              });
            }}
          />
        </div>
      )}

      <div className="mt-5 flex items-center gap-3 border-t border-line pt-4">
        <motion.button onClick={publish} disabled={!passed || looksEmpty || !!classifReview || publishing || published || blockedByReview}
          whileTap={{ scale: 0.97 }}
          className="btn-primary py-1.5 text-sm disabled:opacity-40"
          title={blockedByReview ? "Confirme a revisão do OCR antes de publicar" : classifReview ? "Confirme a classificação e gere a planilha antes de publicar" : looksEmpty ? "O teste não extraiu dados; ajuste antes de publicar" : passed ? "" : "Rode um teste com sucesso antes de publicar"}>
          {published ? "Publicado ✓" : publishing ? "Publicando…" : "Publicar"}
        </motion.button>
        {blockedByReview && (
          <span className="text-xs" style={{ color: "var(--warn2)" }}>Confirme a revisão do OCR para publicar.</span>
        )}
        {passed && !!classifReview && !published && (
          <span className="text-xs" style={{ color: "var(--warn2)" }}>Confirme a classificação acima para concluir o teste.</span>
        )}
        {passed && looksEmpty && !published && (
          <span className="text-xs" style={{ color: "var(--warn2)" }}>O teste não extraiu dados. Ajuste o Processamento antes de publicar.</span>
        )}
        {!passed && !published && (
          <span className="text-xs text-ink3">Publicar libera após um teste bem-sucedido.</span>
        )}
        {published && (
          <span className="text-xs text-ok">Automação no ar. Veja em Versões ou abra o app publicado.</span>
        )}
      </div>
      </div>
    </div>
  );
}

/* ---------- auto-reparo colaborativo (dentro da caixa de erro do teste) ---------- */
interface RepairProposal {
  diagnosis: string;
  change_summary: string;
  fixed_code: string;
  has_changes: boolean;
}

function RepairPanel({
  projectId,
  scriptStageId,
  executionId,
  onRetest,
}: {
  projectId: number;
  scriptStageId: number;
  executionId: string;
  onRetest: () => Promise<Execution>;
}) {
  const [phase, setPhase] = useState<"idle" | "proposing" | "proposed" | "applying" | "exhausted">("idle");
  const [proposal, setProposal] = useState<RepairProposal | null>(null);
  const [hint, setHint] = useState("");
  const [showCode, setShowCode] = useState(false);
  const [attempts, setAttempts] = useState(0);
  const [error, setError] = useState("");
  const MAX = 3;

  async function propose() {
    setError("");
    setPhase("proposing");
    try {
      const p = await api.post<RepairProposal>(
        `/api/projects/${projectId}/stages/${scriptStageId}/repair/propose`,
        { execution_id: executionId, hint: hint.trim() || null }
      );
      setProposal(p);
      setPhase("proposed");
    } catch (e: any) {
      setError(e?.message || "Falha ao consultar a IA.");
      setPhase("idle");
    }
  }

  async function apply() {
    if (!proposal?.fixed_code) return;
    setError("");
    setPhase("applying");
    try {
      await api.post(`/api/projects/${projectId}/stages/${scriptStageId}/repair/apply`, {
        code: proposal.fixed_code,
      });
      const last = await onRetest();
      const n = attempts + 1;
      setAttempts(n);
      setProposal(null);
      setHint("");
      setShowCode(false);
      if (last.status === "success") setPhase("idle");
      else setPhase(n >= MAX ? "exhausted" : "idle");
    } catch (e: any) {
      setError(e?.message || "Falha ao aplicar a correção.");
      setPhase("proposed");
    }
  }

  if (phase === "exhausted") {
    return (
      <p className="mt-2 text-xs text-ink2">
        Tentei reparar algumas vezes sem sucesso. Ajuste a descrição na etapa Processamento e monte
        de novo, ou abra o modo avançado para ver os detalhes técnicos.
      </p>
    );
  }

  if (phase === "proposing") {
    return (
      <div className="mt-3 flex items-center gap-2 text-sm text-ink2">
        <Spinner className="h-4 w-4" /> A IA está analisando o erro e preparando uma correção…
      </div>
    );
  }

  if (phase === "applying") {
    return (
      <div className="mt-3 flex items-center gap-2 text-sm text-ink2">
        <Spinner className="h-4 w-4" /> Aplicando a correção e testando de novo…
      </div>
    );
  }

  if (phase === "proposed" && proposal) {
    if (!proposal.has_changes) {
      return (
        <div className="mt-3 space-y-2">
          <p className="text-sm text-ink2">
            {proposal.diagnosis || "Não consegui identificar uma correção automática."}
          </p>
          <p className="text-xs text-ink3">
            Tente ajustar a descrição na etapa Processamento, ou abra o modo avançado.
          </p>
          <button onClick={() => setPhase("idle")} className="btn-ghost py-1 text-xs">
            Fechar
          </button>
        </div>
      );
    }
    return (
      <div className="mt-3 space-y-2.5 rounded-lg border border-line bg-surface p-3">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-ink3">O que aconteceu</div>
          <p className="text-sm text-ink2">{proposal.diagnosis}</p>
        </div>
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-ink3">Como vou resolver</div>
          <p className="text-sm text-ink2">{proposal.change_summary}</p>
        </div>
        <button
          onClick={() => setShowCode((v) => !v)}
          className="text-xs font-medium text-accentv hover:brightness-110"
        >
          {showCode ? "Ocultar alteração no código" : "Ver alteração no código"}
        </button>
        {showCode && (
          <pre className="max-h-56 overflow-auto rounded-lg bg-brand-900 p-3 text-xs leading-relaxed text-slate-100">
            {proposal.fixed_code}
          </pre>
        )}
        <div>
          <label className="text-xs text-ink3">Quer dar uma dica? (opcional)</label>
          <input
            className="input mt-1 text-sm"
            placeholder="Ex: a coluna se chama 'Vlr Total'."
            value={hint}
            onChange={(e) => setHint(e.target.value)}
          />
        </div>
        {error && <p className="text-xs text-err">{error}</p>}
        <div className="flex items-center gap-2 pt-0.5">
          <button onClick={apply} className="btn-accent py-1.5 text-sm">
            Aplicar e testar
          </button>
          <button
            onClick={() => {
              setPhase("idle");
              setProposal(null);
            }}
            className="btn-ghost py-1.5 text-sm"
          >
            Cancelar
          </button>
        </div>
      </div>
    );
  }

  // idle
  return (
    <div className="mt-3 space-y-2">
      <button onClick={propose} className="btn-primary py-1.5 text-sm">
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M12 3l1.8 4.7L18.5 9l-4.7 1.8L12 15l-1.8-4.2L5.5 9l4.7-1.3L12 3z" />
        </svg>
        Reparar com IA
      </button>
      {attempts > 0 && (
        <div>
          <label className="text-xs text-ink3">Dica para a próxima tentativa (opcional)</label>
          <input
            className="input mt-1 text-sm"
            placeholder="Ex: a coluna se chama 'Vlr Total'."
            value={hint}
            onChange={(e) => setHint(e.target.value)}
          />
        </div>
      )}
      {error && <p className="text-xs text-err">{error}</p>}
      <p className="text-xs text-ink3">
        Ou ajuste a descrição na etapa Processamento, ou abra o modo avançado.
      </p>
    </div>
  );
}
