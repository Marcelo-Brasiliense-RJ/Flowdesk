import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
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

interface BuildResult {
  explanation: string;
  script_file: string;
  stage_ids: { input?: number; script?: number; result?: number; trigger?: number };
  ai_enabled: boolean;
}

/**
 * Assistente (wizard) de criação para o usuário não-técnico.
 *
 * O frontend é dono das 4 etapas (previsibilidade); a IA entra só no Processamento.
 * Ao entrar na Revisão, o fluxo é montado no backend (POST /wizard/build) e o usuário
 * precisa rodar um teste com dados de exemplo (status `success`) antes de publicar.
 */
export default function Wizard() {
  const { id } = useParams();
  const projectId = Number(id);
  const [project, setProject] = useState<Project | null>(null);
  const [state, setState] = useState<WizardState>({});
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);

  const [building, setBuilding] = useState(false);
  const [build, setBuild] = useState<BuildResult | null>(null);
  const [buildError, setBuildError] = useState("");

  useEffect(() => {
    api.get<Project>(`/api/projects/${projectId}`).then((p) => {
      setProject(p);
      const ws = p.wizard_state || {};
      setState(ws);
      setStep(Math.min(ws.step ?? 0, STEPS.length - 1));
    });
  }, [projectId]);

  function patch(partial: Partial<WizardState>) {
    setState((s) => ({ ...s, ...partial }));
  }

  async function persist(next: number) {
    setSaving(true);
    try {
      await api.put(`/api/projects/${projectId}/wizard`, {
        state: { ...state, step: next },
        dirty: false,
      });
      setStep(next);
    } finally {
      setSaving(false);
    }
  }

  async function buildFlow() {
    setBuilding(true);
    setBuildError("");
    try {
      const res = await api.post<BuildResult>(
        `/api/projects/${projectId}/wizard/build`
      );
      setBuild(res);
    } catch (e: any) {
      setBuildError(e?.message || "Falha ao montar a automação.");
    } finally {
      setBuilding(false);
    }
  }

  async function handleContinue() {
    const next = step + 1;
    await persist(next);
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

      {/* trilha de progresso */}
      <div className="flex items-center gap-2 border-b border-slate-200 bg-white px-6 py-3">
        {STEPS.map((label, i) => (
          <div key={label} className="flex items-center gap-2">
            <div
              className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ${
                i === step
                  ? "bg-brand-600 text-white"
                  : i < step
                  ? "bg-emerald-500 text-white"
                  : "bg-slate-200 text-slate-500"
              }`}
            >
              {i < step ? "✓" : i + 1}
            </div>
            <span
              className={`text-sm ${
                i === step ? "font-medium text-brand-900" : "text-slate-400"
              }`}
            >
              {label}
            </span>
            {i < STEPS.length - 1 && <span className="mx-1 text-slate-300">·</span>}
          </div>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-8">
        <div className="mx-auto max-w-2xl">
          {step === 0 && <TriggerStep state={state} patch={patch} />}
          {step === 1 && <InputStep state={state} patch={patch} />}
          {step === 2 && <ProcessStep state={state} patch={patch} />}
          {step === 3 && <OutputStep state={state} patch={patch} />}
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
        </div>
      </div>

      <footer className="flex items-center justify-between border-t border-slate-200 bg-white px-6 py-3">
        <button
          onClick={() => step > 0 && setStep(step - 1)}
          disabled={step === 0}
          className="btn-outline py-1.5 text-sm disabled:opacity-40"
        >
          ← Voltar
        </button>
        <span className="text-xs text-slate-400">
          Etapa {step + 1} de {STEPS.length}
        </span>
        {step < STEPS.length - 1 ? (
          <button
            onClick={handleContinue}
            disabled={!canAdvance || saving}
            className="btn-primary py-1.5 text-sm disabled:opacity-40"
          >
            {saving ? "Salvando…" : step === 3 ? "Montar e revisar" : "Continuar"}
          </button>
        ) : (
          <span className="w-24" />
        )}
      </footer>
    </div>
  );
}

interface StepProps {
  state: WizardState;
  patch: (partial: Partial<WizardState>) => void;
}

function StepTitle({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="mb-5">
      <h1 className="text-xl font-bold text-brand-900">{title}</h1>
      <p className="mt-1 text-sm text-slate-500">{hint}</p>
    </div>
  );
}

function ChoiceCard({
  active,
  title,
  desc,
  onClick,
}: {
  active: boolean;
  title: string;
  desc: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full rounded-xl border p-4 text-left transition ${
        active
          ? "border-brand-500 bg-brand-50"
          : "border-slate-200 bg-white hover:border-brand-300"
      }`}
    >
      <div className="font-medium text-brand-900">{title}</div>
      <div className="mt-0.5 text-sm text-slate-500">{desc}</div>
    </button>
  );
}

function TriggerStep({ state, patch }: StepProps) {
  const kind = state.trigger?.kind;
  const set = (k: TriggerKind) => patch({ trigger: { ...state.trigger, kind: k } });
  return (
    <div>
      <StepTitle
        title="Como essa automação começa?"
        hint="Escolha o que dispara a execução."
      />
      <div className="space-y-3">
        <ChoiceCard
          active={kind === "manual"}
          title="Eu mesmo executo"
          desc="A pessoa abre a automação e roda na hora, preenchendo o que for preciso."
          onClick={() => set("manual")}
        />
        <ChoiceCard
          active={kind === "schedule"}
          title="Em um horário"
          desc="Roda sozinha de forma agendada, por exemplo a cada X horas ou todo dia."
          onClick={() => set("schedule")}
        />
        <ChoiceCard
          active={kind === "webhook"}
          title="Quando chega algo de fora"
          desc="Dispara ao receber uma requisição de outro sistema (webhook)."
          onClick={() => set("webhook")}
        />
      </div>
      {kind === "schedule" && (
        <div className="mt-4 flex items-center gap-2 rounded-lg bg-white p-3 text-sm">
          <span className="text-slate-500">A cada</span>
          <input
            type="number"
            min={1}
            value={state.trigger?.every ?? 1}
            onChange={(e) =>
              patch({
                trigger: {
                  kind: "schedule",
                  every: Math.max(1, Number(e.target.value)),
                  unit: state.trigger?.unit ?? "hours",
                },
              })
            }
            className="input w-20"
          />
          <select
            value={state.trigger?.unit ?? "hours"}
            onChange={(e) =>
              patch({
                trigger: {
                  kind: "schedule",
                  every: state.trigger?.every ?? 1,
                  unit: e.target.value as "hours" | "days",
                },
              })
            }
            className="input w-32"
          >
            <option value="hours">hora(s)</option>
            <option value="days">dia(s)</option>
          </select>
        </div>
      )}
    </div>
  );
}

function InputStep({ state, patch }: StepProps) {
  const kind = state.input?.kind;
  const fields = state.input?.fields ?? [];
  const set = (k: InputKind) => patch({ input: { ...state.input, kind: k } });

  function addField() {
    patch({
      input: { kind: "fields", fields: [...fields, { label: "", type: "text" }] },
    });
  }
  function updateField(i: number, partial: Partial<WizardField>) {
    const next = fields.map((f, idx) => (idx === i ? { ...f, ...partial } : f));
    patch({ input: { kind: "fields", fields: next } });
  }
  function removeField(i: number) {
    patch({ input: { kind: "fields", fields: fields.filter((_, idx) => idx !== i) } });
  }

  return (
    <div>
      <StepTitle
        title="O que essa automação recebe?"
        hint="Define a entrada de dados que será processada."
      />
      <div className="space-y-3">
        <ChoiceCard
          active={kind === "file"}
          title="Um arquivo"
          desc="Uma planilha, CSV ou PDF. Você poderá subir um exemplo na hora de testar."
          onClick={() => set("file")}
        />
        <ChoiceCard
          active={kind === "fields"}
          title="Alguns campos digitados"
          desc="A pessoa preenche campos simples antes de rodar."
          onClick={() => set("fields")}
        />
        <ChoiceCard
          active={kind === "none"}
          title="Nada"
          desc="A automação não precisa de entrada."
          onClick={() => set("none")}
        />
      </div>
      {kind === "fields" && (
        <div className="mt-4 space-y-2 rounded-lg bg-white p-3">
          {fields.length === 0 && (
            <p className="text-sm text-slate-400">Nenhum campo ainda.</p>
          )}
          {fields.map((f, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                className="input flex-1"
                placeholder="Rótulo do campo (ex: CNPJ)"
                value={f.label}
                onChange={(e) => updateField(i, { label: e.target.value })}
              />
              <select
                className="input w-32"
                value={f.type}
                onChange={(e) =>
                  updateField(i, { type: e.target.value as WizardField["type"] })
                }
              >
                <option value="text">texto</option>
                <option value="number">número</option>
                <option value="date">data</option>
                <option value="select">lista</option>
              </select>
              <button
                type="button"
                onClick={() => removeField(i)}
                className="px-2 text-slate-400 hover:text-red-600"
              >
                ×
              </button>
            </div>
          ))}
          <button type="button" onClick={addField} className="btn-outline py-1 text-xs">
            + Adicionar campo
          </button>
        </div>
      )}
    </div>
  );
}

function ProcessStep({ state, patch }: StepProps) {
  return (
    <div>
      <StepTitle
        title="O que fazer com isso?"
        hint="Descreva em português o que a automação deve fazer. A IA monta o passo a passo."
      />
      <textarea
        className="input min-h-[160px] resize-y"
        placeholder="Ex: remover linhas duplicadas pela coluna Valor; somar por CNPJ e gerar um resumo."
        value={state.process?.description ?? ""}
        onChange={(e) => patch({ process: { description: e.target.value } })}
      />
      <p className="mt-2 text-xs text-slate-400">
        Ao continuar, a IA vai montar a automação e mostrar uma explicação em
        português. Nada é publicado sem você testar antes.
      </p>
    </div>
  );
}

function OutputStep({ state, patch }: StepProps) {
  const kind = state.output?.kind;
  const set = (k: OutputKind) => patch({ output: { kind: k } });
  return (
    <div>
      <StepTitle
        title="O que você recebe de volta?"
        hint="Define o resultado entregue ao final."
      />
      <div className="space-y-3">
        <ChoiceCard
          active={kind === "download"}
          title="Arquivo para baixar"
          desc="Gera um arquivo (ex: Excel) com o resultado para download."
          onClick={() => set("download")}
        />
        <ChoiceCard
          active={kind === "summary"}
          title="Resumo na tela"
          desc="Mostra um resumo do que foi processado, sem arquivo."
          onClick={() => set("summary")}
        />
      </div>
    </div>
  );
}

/** Traduz erros técnicos comuns do Python para uma mensagem em português.
 * Cobre os casos frequentes; o resto cai num texto genérico + modo avançado. */
function translateError(stderr: string): string {
  const s = stderr || "";
  const key = s.match(/KeyError:\s*['"]?([^'"\n]+)/);
  if (key) return `A coluna ou campo "${key[1]}" não foi encontrado nos dados.`;
  if (/BadZipFile|not a zip file|openpyxl.*cannot/i.test(s))
    return "O arquivo enviado não parece ser um Excel (.xlsx) válido.";
  if (/EmptyDataError|No columns to parse|empty/i.test(s))
    return "O arquivo enviado parece estar vazio.";
  if (/FileNotFoundError|No such file/i.test(s))
    return "O arquivo de entrada não foi encontrado. Suba um exemplo e tente de novo.";
  if (/could not convert|invalid literal|ValueError/i.test(s))
    return "Algum dado veio em um formato inesperado (ex: texto onde se esperava número).";
  if (/ModuleNotFoundError|No module named/i.test(s))
    return "A automação depende de um pacote que ainda não está instalado.";
  return "A automação encontrou um erro ao processar. Tente ajustar a descrição na etapa Processamento.";
}

function ReviewStep({
  projectId,
  state,
  building,
  build,
  buildError,
  onRebuild,
}: {
  projectId: number;
  state: WizardState;
  building: boolean;
  build: BuildResult | null;
  buildError: string;
  onRebuild: () => void;
}) {
  const triggerText =
    state.trigger?.kind === "manual"
      ? "Você executa manualmente"
      : state.trigger?.kind === "schedule"
      ? `Agendada a cada ${state.trigger.every ?? 1} ${
          state.trigger.unit === "days" ? "dia(s)" : "hora(s)"
        }`
      : state.trigger?.kind === "webhook"
      ? "Disparada por um sistema externo (webhook)"
      : "—";
  const inputText =
    state.input?.kind === "file"
      ? "Recebe um arquivo"
      : state.input?.kind === "fields"
      ? `Recebe ${state.input.fields?.length ?? 0} campo(s) digitado(s)`
      : state.input?.kind === "none"
      ? "Não recebe entrada"
      : "—";
  const outputText =
    state.output?.kind === "download"
      ? "Gera um arquivo para baixar"
      : state.output?.kind === "summary"
      ? "Mostra um resumo na tela"
      : "—";

  return (
    <div>
      <StepTitle
        title="Revisão e teste"
        hint="Confira o que foi montado e rode um teste com dados de exemplo antes de publicar."
      />

      <div className="space-y-3">
        <ReviewRow label="Começa" value={triggerText} />
        <ReviewRow label="Recebe" value={inputText} />
        <ReviewRow label="Faz" value={state.process?.description?.trim() || "—"} />
        <ReviewRow label="Entrega" value={outputText} />
      </div>

      <div className="mt-6 rounded-xl border border-slate-200 bg-white p-5">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="font-semibold text-brand-900">O que a automação vai fazer</h3>
          <button
            onClick={onRebuild}
            disabled={building}
            className="text-xs text-slate-400 hover:text-brand-700 disabled:opacity-50"
          >
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
          <>
            <p className="whitespace-pre-wrap text-sm text-slate-600">
              {build.explanation}
            </p>
            {!build.ai_enabled && (
              <p className="mt-2 text-xs text-amber-600">
                IA em modo simulado: o código gerado é um exemplo. Configure a chave da
                IA para geração real.
              </p>
            )}
          </>
        ) : (
          <p className="text-sm text-slate-400">Ainda não montado.</p>
        )}
      </div>

      {build?.stage_ids?.script && (
        <TestPanel
          projectId={projectId}
          scriptStageId={build.stage_ids.script}
          state={state}
        />
      )}
    </div>
  );
}

function ReviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        {label}
      </div>
      <div className="mt-0.5 text-sm text-slate-700">{value}</div>
    </div>
  );
}

function TestPanel({
  projectId,
  scriptStageId,
  state,
}: {
  projectId: number;
  scriptStageId: number;
  state: WizardState;
}) {
  const [samplePath, setSamplePath] = useState<string>("");
  const [sampleName, setSampleName] = useState<string>("");
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
    const r = await api.postForm<{ name: string }>(
      `/api/projects/${projectId}/fs/upload`,
      fd
    );
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
      const started = await api.post<Execution>(
        `/api/projects/${projectId}/stages/${scriptStageId}/run`,
        buildPayload()
      );
      let last = started;
      for (let i = 0; i < 25; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        last = await api.get<Execution>(
          `/api/projects/${projectId}/executions/${started.id}`
        );
        if (last.status === "success" || last.status === "error") break;
      }
      setExec(last);
    } catch (e: any) {
      setExec({
        status: "error",
        stderr: e?.message || "Falha ao iniciar o teste.",
      } as Execution);
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
        Rode a automação de verdade antes de publicar. Publicar só fica disponível após
        um teste bem-sucedido.
      </p>

      {inputKind === "file" && (
        <div className="mt-3 flex items-center gap-2 text-sm">
          <label className="btn-outline cursor-pointer py-1.5 text-xs">
            {sampleName ? `Trocar arquivo (${sampleName})` : "Subir arquivo de exemplo"}
            <input
              type="file"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) uploadSample(f);
                e.target.value = "";
              }}
            />
          </label>
          {sampleName && <span className="text-emerald-600">✓ {sampleName}</span>}
        </div>
      )}

      {inputKind === "fields" && (
        <div className="mt-3 space-y-2">
          {fields.map((f, i) => (
            <div key={i} className="flex items-center gap-2 text-sm">
              <span className="w-40 shrink-0 text-slate-500">{f.label || `Campo ${i + 1}`}</span>
              <input
                className="input"
                value={fieldValues[f.label] ?? ""}
                onChange={(e) =>
                  setFieldValues((v) => ({ ...v, [f.label]: e.target.value }))
                }
              />
            </div>
          ))}
        </div>
      )}

      <button
        onClick={runTest}
        disabled={testing || needsSample}
        className="btn-accent mt-4 py-1.5 text-sm disabled:opacity-50"
        title={needsSample ? "Suba um arquivo de exemplo primeiro" : ""}
      >
        {testing ? "Testando…" : "Testar agora"}
      </button>

      {exec && (
        <div className="mt-4">
          {passed ? (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3">
              <div className="text-sm font-medium text-emerald-700">
                Teste concluído com sucesso
              </div>
              {summary && (
                <pre className="mt-2 overflow-auto rounded bg-white p-2 text-xs text-slate-600">
                  {JSON.stringify(summary, null, 2)}
                </pre>
              )}
              {resultFile && (
                <div className="mt-2 text-xs text-slate-500">
                  Arquivo gerado: {String(resultFile).split(/[\\/]/).pop()} (disponível
                  no app publicado e no modo avançado).
                </div>
              )}
            </div>
          ) : (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3">
              <div className="text-sm font-medium text-red-700">
                {translateError(exec.stderr || "")}
              </div>
              <p className="mt-1 text-xs text-slate-500">
                Ajuste a descrição na etapa Processamento e monte de novo, ou abra o modo
                avançado para ver os detalhes técnicos.
              </p>
            </div>
          )}
        </div>
      )}

      <div className="mt-5 flex items-center gap-3 border-t border-slate-100 pt-4">
        <button
          onClick={publish}
          disabled={!passed || publishing || published}
          className="btn-primary py-1.5 text-sm disabled:opacity-40"
          title={passed ? "" : "Rode um teste com sucesso antes de publicar"}
        >
          {published ? "Publicado ✓" : publishing ? "Publicando…" : "Publicar"}
        </button>
        {!passed && !published && (
          <span className="text-xs text-slate-400">
            Publicar libera após um teste bem-sucedido.
          </span>
        )}
        {published && (
          <span className="text-xs text-emerald-600">
            Automação no ar. Veja em Versões ou abra o app publicado.
          </span>
        )}
      </div>
    </div>
  );
}
