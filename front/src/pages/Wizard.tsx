import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { motion, AnimatePresence, useReducedMotion, type Variants } from "framer-motion";
import { api } from "../lib/api";
import type {
  Execution,
  InputKind,
  OutputKind,
  Project,
  TriggerKind,
  WizardField,
  WizardState,
} from "../lib/types";
import { Logo, Spinner } from "../components/ui";

const STEPS = ["Gatilho", "Entrada", "Processamento", "Resultado", "Revisão"];

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
 * Assistente prompt-aware: o usuário descreve o que quer, a IA lê o pedido (e o
 * arquivo de exemplo), preenche o que já dá pra deduzir e só pergunta o que falta.
 * As 4 etapas viram confirmação/ajuste; se a IA entende tudo, pula para a Revisão.
 */
export default function Wizard() {
  const { id } = useParams();
  const projectId = Number(id);
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
    api.get<Project>(`/api/projects/${projectId}`).then((p) => {
      setProject(p);
      const ws = p.wizard_state || {};
      if ((ws as any)._built) {
        setState(ws);
        setStep(4);
      }
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
      <div className="flex h-full items-center justify-center text-brand-700">
        <Spinner className="h-8 w-8" />
      </div>
    );

  const canAdvance =
    (step === 0 && !!state.trigger?.kind) ||
    (step === 1 && !!state.input?.kind) ||
    (step === 2 && !!state.process?.description?.trim()) ||
    (step === 3 && !!state.output?.kind);

  return (
    <div className="flex h-full flex-col bg-slate-50">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-2">
        <div className="flex items-center gap-2">
          <Link to="/" className="shrink-0">
            <Logo />
          </Link>
          <span className="text-slate-300">/</span>
          <span className="font-semibold text-brand-900">{project.name}</span>
          <span className="badge bg-brand-50 text-brand-600">Assistente</span>
        </div>
        <Link
          to={`/projects/${projectId}/editor`}
          className="text-xs text-slate-400 hover:text-brand-700"
          title="Editar o código e o fluxo diretamente"
        >
          Modo avançado →
        </Link>
      </header>

      {project.wizard_dirty && !dismissedDirty && (
        <div className="flex flex-wrap items-center gap-3 border-b border-amber-200 bg-amber-50 px-6 py-2.5 text-sm">
          <span className="text-amber-800">
            Esta automação foi ajustada manualmente no modo avançado. Editar pelo
            assistente pode sobrescrever esses ajustes.
          </span>
          <button onClick={() => setDismissedDirty(true)} className="btn-outline py-1 text-xs">
            Continuar mesmo assim
          </button>
          <Link
            to={`/projects/${projectId}/editor`}
            className="text-xs font-medium text-amber-700 hover:underline"
          >
            Abrir no modo avançado
          </Link>
        </div>
      )}

      {step >= 0 && (
        <div className="flex items-center gap-2 border-b border-slate-200 bg-white px-6 py-3">
          {STEPS.map((label, i) => {
            const dimKey = (["trigger", "input", "process", "output"] as const)[i];
            const confident = i < 4 && (plan?.[dimKey] as DimPlan)?.confident;
            const done = i < step || (confident && i !== step);
            return (
              <div key={label} className="flex items-center gap-2">
                <div
                  className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ${
                    i === step
                      ? "bg-brand-600 text-white"
                      : done
                      ? "bg-emerald-500 text-white"
                      : "bg-slate-200 text-slate-500"
                  }`}
                >
                  {done ? "✓" : i + 1}
                </div>
                <span className={`text-sm ${i === step ? "font-medium text-brand-900" : "text-slate-400"}`}>
                  {label}
                </span>
                {i < STEPS.length - 1 && <span className="mx-1 text-slate-300">·</span>}
              </div>
            );
          })}
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-auto p-8">
        <div className="mx-auto max-w-2xl">
          <AnimatePresence mode="wait">
            <motion.div
              key={step}
              initial={reduce ? false : { opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              exit={reduce ? undefined : { opacity: 0, x: -24 }}
              transition={{ type: "spring", stiffness: 320, damping: 30 }}
            >
              {step === -1 && (
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
              )}
              {step === 0 && <TriggerStep state={state} patch={patch} plan={plan?.trigger} />}
              {step === 1 && <InputStep state={state} patch={patch} plan={plan?.input} />}
              {step === 2 && <ProcessStep state={state} patch={patch} plan={plan?.process} />}
              {step === 3 && <OutputStep state={state} patch={patch} plan={plan?.output} />}
              {step === 4 && (
                <ReviewStep
                  projectId={projectId}
                  state={state}
                  building={building}
                  build={build}
                  buildError={buildError}
                  onRebuild={buildFlow}
                />
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>

      {step >= 0 && (
        <footer className="flex items-center justify-between border-t border-slate-200 bg-white px-6 py-3">
          <button
            onClick={() => setStep(step - 1)}
            disabled={step === 0}
            className="btn-outline py-1.5 text-sm disabled:opacity-40"
          >
            ← Voltar
          </button>
          <span className="text-xs text-slate-400">Etapa {step + 1} de {STEPS.length}</span>
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
        </footer>
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
      <motion.h1 variants={heroItem} className="text-center text-2xl font-bold text-brand-900">
        O que você quer automatizar?
      </motion.h1>
      <motion.p variants={heroItem} className="mx-auto mt-2 max-w-lg text-center text-sm text-slate-500">
        Descreva em português, com o máximo de detalhe, e anexe um exemplo. Eu leio o seu
        pedido e só pergunto o que realmente faltar.
      </motion.p>

      <motion.div
        variants={heroItem}
        className="mt-6 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
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
            className="mt-4 flex items-center justify-center gap-2 text-sm text-slate-500"
          >
            <Spinner className="h-4 w-4" /> Lendo seu pedido e montando as etapas…
          </motion.div>
        )}
      </AnimatePresence>
      {error && <p className="mt-3 text-center text-sm text-red-600">{error}</p>}
      <motion.p variants={heroItem} className="mt-3 text-center text-xs text-slate-400">
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
      <h1 className="text-xl font-bold text-brand-900">{title}</h1>
      <p className="mt-1 text-sm text-slate-500">{hint}</p>
    </div>
  );
}

function ConfidentBanner({ text }: { text: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      className="mb-4 flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800"
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
      className="mb-4 rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-sm font-medium text-brand-800"
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
      className={`w-full rounded-xl border p-4 text-left transition ${
        active ? "border-brand-500 bg-brand-50" : "border-slate-200 bg-white hover:border-brand-300"
      }`}
    >
      <div className="font-medium text-brand-900">{title}</div>
      <div className="mt-0.5 text-sm text-slate-500">{desc}</div>
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
        <div className="mt-4 flex items-center gap-2 rounded-lg bg-white p-3 text-sm">
          <span className="text-slate-500">A cada</span>
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
        <div className="mt-4 space-y-2 rounded-lg bg-white p-3">
          {fields.length === 0 && <p className="text-sm text-slate-400">Nenhum campo ainda.</p>}
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
              <button type="button" onClick={() => removeField(i)} className="px-2 text-slate-400 hover:text-red-600">×</button>
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
      <p className="mt-2 text-xs text-slate-400">
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
  return kind === "file" ? "ela recebe um arquivo (planilha)"
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
  projectId, state, building, build, buildError, onRebuild,
}: {
  projectId: number;
  state: WizardState;
  building: boolean;
  build: BuildResult | null;
  buildError: string;
  onRebuild: () => void;
}) {
  return (
    <div>
      <StepTitle title="Revisão e teste" hint="Confira o que foi montado e rode um teste com dados de exemplo antes de publicar." />
      <div className="space-y-3">
        <ReviewRow label="Começa" value={capitalize(triggerText(state.trigger?.kind))} />
        <ReviewRow label="Recebe" value={capitalize(inputText(state.input?.kind, state.input?.fields?.length ?? 0))} />
        <ReviewRow label="Faz" value={state.process?.description?.trim() || "—"} />
        <ReviewRow label="Entrega" value={capitalize(outputText(state.output?.kind))} />
      </div>

      <div className="mt-6 rounded-xl border border-slate-200 bg-white p-5">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="font-semibold text-brand-900">O que a automação vai fazer</h3>
          <button onClick={onRebuild} disabled={building}
            className="text-xs text-slate-400 hover:text-brand-700 disabled:opacity-50">
            {building ? "Montando…" : "Montar de novo"}
          </button>
        </div>
        {building ? (
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Spinner className="h-4 w-4" /> Montando a automação…
          </div>
        ) : buildError ? (
          <p className="text-sm text-red-600">{buildError}</p>
        ) : build ? (
          <p className="whitespace-pre-wrap text-sm text-slate-600">{build.explanation}</p>
        ) : (
          <p className="text-sm text-slate-400">Ainda não montado.</p>
        )}
      </div>

      {build?.stage_ids?.script && (
        <TestPanel projectId={projectId} scriptStageId={build.stage_ids.script} state={state} />
      )}
    </div>
  );
}

function ReviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-0.5 text-sm text-slate-700">{value}</div>
    </div>
  );
}

function capitalize(s: string) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

function TestPanel({
  projectId, scriptStageId, state,
}: {
  projectId: number;
  scriptStageId: number;
  state: WizardState;
}) {
  const [samplePath, setSamplePath] = useState(state.input?.sample_file ?? "");
  const [sampleName, setSampleName] = useState(state.input?.sample_file?.split("/").pop() ?? "");
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [testing, setTesting] = useState(false);
  const [exec, setExec] = useState<Execution | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [published, setPublished] = useState(false);

  const inputKind = state.input?.kind ?? "none";
  const fields = state.input?.fields ?? [];
  const passed = exec?.status === "success";

  async function uploadSample(file: File) {
    const fd = new FormData();
    fd.append("path", "uploads");
    fd.append("file", file);
    const r = await api.postForm<{ name: string }>(`/api/projects/${projectId}/fs/upload`, fd);
    setSamplePath(`uploads/${r.name}`);
    setSampleName(r.name);
  }
  function buildPayload(): Record<string, unknown> {
    if (inputKind === "file") return samplePath ? { arquivo: samplePath } : {};
    if (inputKind === "fields") return { ...fieldValues };
    return {};
  }
  async function runTest() {
    setTesting(true);
    setExec(null);
    try {
      const started = await api.post<Execution>(`/api/projects/${projectId}/stages/${scriptStageId}/run`, buildPayload());
      let last = started;
      for (let i = 0; i < 25; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        last = await api.get<Execution>(`/api/projects/${projectId}/executions/${started.id}`);
        if (last.status === "success" || last.status === "error") break;
      }
      setExec(last);
    } catch (e: any) {
      setExec({ status: "error", stderr: e?.message || "Falha ao iniciar o teste." } as Execution);
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
  const summary = exec?.output_data?.resumo;
  const resultFile = exec?.output_data?.arquivo_resultado as string | undefined;

  return (
    <div className="mt-6 rounded-xl border border-slate-200 bg-white p-5">
      <h3 className="font-semibold text-brand-900">Testar com dados de exemplo</h3>
      <p className="mt-1 text-sm text-slate-500">
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
          {sampleName && <span className="text-emerald-600">✓ {sampleName}</span>}
        </div>
      )}
      {inputKind === "fields" && (
        <div className="mt-3 space-y-2">
          {fields.map((f, i) => (
            <div key={i} className="flex items-center gap-2 text-sm">
              <span className="w-40 shrink-0 text-slate-500">{f.label || `Campo ${i + 1}`}</span>
              <input className="input" value={fieldValues[f.label] ?? ""}
                onChange={(e) => setFieldValues((v) => ({ ...v, [f.label]: e.target.value }))} />
            </div>
          ))}
        </div>
      )}

      <motion.button onClick={runTest} disabled={testing || needsSample}
        whileTap={{ scale: 0.97 }}
        className="btn-accent mt-4 py-1.5 text-sm disabled:opacity-50"
        title={needsSample ? "Suba um arquivo de exemplo primeiro" : ""}>
        {testing ? "Testando…" : "Testar agora"}
      </motion.button>

      <AnimatePresence>
        {exec && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-4">
            {passed ? (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3">
                <div className="text-sm font-medium text-emerald-700">Teste concluído com sucesso</div>
                {summary && (
                  <pre className="mt-2 overflow-auto rounded bg-white p-2 text-xs text-slate-600">
                    {JSON.stringify(summary, null, 2)}
                  </pre>
                )}
                {resultFile && (
                  <div className="mt-2 text-xs text-slate-500">
                    Arquivo gerado: {String(resultFile).split(/[\\/]/).pop()} (disponível no app publicado e no modo avançado).
                  </div>
                )}
              </div>
            ) : (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3">
                <div className="text-sm font-medium text-red-700">{translateError(exec.stderr || "")}</div>
                <p className="mt-1 text-xs text-slate-500">
                  Ajuste a descrição na etapa Processamento e monte de novo, ou abra o modo avançado para ver os detalhes técnicos.
                </p>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <div className="mt-5 flex items-center gap-3 border-t border-slate-100 pt-4">
        <motion.button onClick={publish} disabled={!passed || publishing || published}
          whileTap={{ scale: 0.97 }}
          className="btn-primary py-1.5 text-sm disabled:opacity-40"
          title={passed ? "" : "Rode um teste com sucesso antes de publicar"}>
          {published ? "Publicado ✓" : publishing ? "Publicando…" : "Publicar"}
        </motion.button>
        {!passed && !published && (
          <span className="text-xs text-slate-400">Publicar libera após um teste bem-sucedido.</span>
        )}
        {published && (
          <span className="text-xs text-emerald-600">Automação no ar. Veja em Versões ou abra o app publicado.</span>
        )}
      </div>
    </div>
  );
}
