import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../lib/api";
import type {
  InputKind,
  OutputKind,
  Project,
  TriggerKind,
  WizardField,
  WizardState,
} from "../lib/types";
import { Logo, Spinner } from "../components/ui";

const STEPS = ["Gatilho", "Entrada", "Processamento", "Resultado", "Revisão"];

/**
 * Assistente (wizard) de criação para o usuário não-técnico.
 *
 * Esta é a casca navegável: captura a intenção nas 4 etapas e persiste em
 * project.wizard_state. A geração de código, a montagem dos nós (Stage/Edge) e o
 * teste obrigatório antes de publicar são incrementos seguintes. O frontend é dono
 * da estrutura das etapas (previsibilidade); a IA entra só na etapa Processamento.
 */
export default function Wizard() {
  const { id } = useParams();
  const projectId = Number(id);
  const [project, setProject] = useState<Project | null>(null);
  const [state, setState] = useState<WizardState>({});
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);

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
      const toSave: WizardState = { ...state, step: next };
      await api.put(`/api/projects/${projectId}/wizard`, {
        state: toSave,
        dirty: false,
      });
      setStep(next);
    } finally {
      setSaving(false);
    }
  }

  function goBack() {
    if (step > 0) setStep(step - 1);
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
    (step === 3 && !!state.output?.kind) ||
    step === 4;

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
          {step === 4 && <ReviewStep state={state} />}
        </div>
      </div>

      <footer className="flex items-center justify-between border-t border-slate-200 bg-white px-6 py-3">
        <button
          onClick={goBack}
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
            onClick={() => persist(step + 1)}
            disabled={!canAdvance || saving}
            className="btn-primary py-1.5 text-sm disabled:opacity-40"
          >
            {saving ? "Salvando…" : "Continuar"}
          </button>
        ) : (
          <button
            disabled
            className="btn-primary py-1.5 text-sm disabled:opacity-40"
            title="O teste obrigatório e a publicação chegam no próximo incremento"
          >
            Testar e publicar (em breve)
          </button>
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
        No próximo incremento, ao continuar, a IA vai gerar a automação e mostrar uma
        explicação em português antes de qualquer publicação.
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

function ReviewStep({ state }: { state: WizardState }) {
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
        title="Revisão"
        hint="Confira o que você montou. O teste obrigatório com dados de exemplo chega no próximo incremento."
      />
      <div className="space-y-3">
        <ReviewRow label="Começa" value={triggerText} />
        <ReviewRow label="Recebe" value={inputText} />
        <ReviewRow
          label="Faz"
          value={state.process?.description?.trim() || "—"}
        />
        <ReviewRow label="Entrega" value={outputText} />
      </div>
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
