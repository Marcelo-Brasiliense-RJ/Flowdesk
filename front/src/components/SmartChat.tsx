import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import { api, getToken } from "../lib/api";
import { useDialog } from "./Dialog";
import { ReportCard, type ExecutionReport } from "../pages/reportCard";
import type { ChatMessage, PendingAction, Stage } from "../lib/types";

export default function SmartChat({
  projectId,
  onApplied,
  autoStart,
  initialInput,
  centered = false,
}: {
  projectId: number;
  onApplied: () => void;
  autoStart?: { content: string; files: File[] };
  /** Texto inicial no campo de mensagem (não envia automaticamente). */
  initialInput?: string;
  /** Quando true, centraliza mensagens e input numa coluna de leitura (tela cheia). */
  centered?: boolean;
}) {
  const dlg = useDialog();
  const nav = useNavigate();
  const [built, setBuilt] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState<PendingAction[]>([]);
  const [streaming, setStreaming] = useState("");
  const [input, setInput] = useState(initialInput ?? "");
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<Fase | null>(null);
  const [ctx, setCtx] = useState({ percent: 0, ai_enabled: false });
  const [attached, setAttached] = useState<File[]>([]);
  const [envDrafts, setEnvDrafts] = useState<Record<number, string>>({});
  const bottomRef = useRef<HTMLDivElement>(null);
  const autoStartedFor = useRef<number | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const [reportExecId, setReportExecId] = useState<string | null>(null);
  const seededReportFor = useRef<string | null>(null);

  useEffect(() => {
    const rep = searchParams.get("report");
    if (rep && seededReportFor.current !== rep) {
      seededReportFor.current = rep;
      setReportExecId(rep);
      api
        .post(`/api/projects/${projectId}/chat/report`, { execution_id: rep })
        .then(() => load())
        .catch(() => {});
      // limpa o param da URL para não refixar em reloads
      searchParams.delete("report");
      setSearchParams(searchParams, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, projectId]);

  async function load() {
    setMessages(await api.get<ChatMessage[]>(`/api/projects/${projectId}/chat`));
    setPending(
      await api.get<PendingAction[]>(`/api/projects/${projectId}/pending-actions`)
    );
    setCtx(await api.get(`/api/projects/${projectId}/chat/context`));
    // a automação está "montada" quando já existe um nó de script no fluxo
    try {
      const stages = await api.get<Stage[]>(`/api/projects/${projectId}/stages`);
      setBuilt(stages.some((s) => s.type === "script" || s.type === "agent"));
    } catch {
      /* ignore */
    }
  }
  useEffect(() => {
    // reset state when switching projects so no stale conversation leaks in
    setMessages([]);
    setPending([]);
    setStreaming("");
    load();
  }, [projectId]);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "auto", block: "nearest" });
  }, [messages, streaming]);
  useEffect(() => {
    // fire the initial message exactly once per project (StrictMode-safe)
    if (autoStart && autoStartedFor.current !== projectId) {
      autoStartedFor.current = projectId;
      send(autoStart.content, undefined, autoStart.files);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoStart, projectId]);

  async function send(
    textOverride?: string,
    attachmentsOverride?: string[],
    filesOverride?: File[]
  ) {
    if (reportExecId) {
      const desc = (textOverride ?? input).trim();
      if (!desc || busy) return;
      setInput("");
      setBusy(true);
      setPhase("thinking");
      try {
        setMessages((m) => [...m, { id: Date.now(), role: "user", content: desc, meta: {}, tokens: 0, created_at: "" }]);
        await api.post(`/api/projects/${projectId}/chat/report-repair`, {
          execution_id: reportExecId,
          message: desc,
        });
        setReportExecId(null);
        await load();
        onApplied();
      } catch (e: any) {
        setMessages((m) => [...m, { id: Date.now() + 1, role: "assistant", content: `Erro: ${e.message}`, meta: {}, tokens: 0, created_at: "" }]);
      } finally {
        setBusy(false);
        setPhase(null);
      }
      return;
    }
    const base = textOverride ?? input;
    const extra = attachmentsOverride ?? [];
    const files = filesOverride ?? (textOverride ? [] : attached);
    if ((!base.trim() && files.length === 0 && extra.length === 0) || busy) return;
    if (!textOverride) setInput("");
    setAttached([]);
    let content = base;
    setBusy(true);
    setStreaming("");
    setPhase(files.length ? "uploading" : "thinking");
    try {
      // already-uploaded project paths (e.g. from the interview) + new File uploads
      const uploaded: string[] = [...extra];
      for (const file of files) {
        const fd = new FormData();
        fd.append("path", "uploads");
        fd.append("file", file);
        await api.postForm(`/api/projects/${projectId}/fs/upload`, fd);
        uploaded.push(`uploads/${file.name}`);
      }
      if (uploaded.length) {
        content +=
          (content ? "\n\n" : "") + `[Arquivos anexados: ${uploaded.join(", ")}]`;
        onApplied();
      }
      setPhase("thinking");
      setMessages((m) => [
        ...m,
        { id: Date.now(), role: "user", content, meta: {}, tokens: 0, created_at: "" },
      ]);
      const res = await fetch(`/api/projects/${projectId}/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({ content, attachments: uploaded }),
      });
      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let acc = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";
        for (const part of parts) {
          const line = part.replace(/^data: /, "").trim();
          if (!line) continue;
          const evt = JSON.parse(line);
          if (evt.type === "token") {
            acc += evt.text;
            setStreaming(acc);
          } else if (evt.type === "done") {
            setStreaming("");
            await load();
            onApplied();
          }
        }
      }
    } catch (e: any) {
      setStreaming("");
      setMessages((m) => [
        ...m,
        {
          id: Date.now() + 1,
          role: "assistant",
          content: `Erro: ${e.message}`,
          meta: {},
          tokens: 0,
          created_at: "",
        },
      ]);
    } finally {
      setBusy(false);
      setAttached([]);
      setPhase(null);
    }
  }

  async function clearChat() {
    const ok = await dlg.confirm({
      title: "Limpar conversa",
      message: "Apaga todas as mensagens e pendências desta conversa. As ações já aplicadas (arquivos/nós criados) permanecem.",
      confirmLabel: "Limpar",
      danger: true,
    });
    if (!ok) return;
    await api.del(`/api/projects/${projectId}/chat`);
    autoStartedFor.current = projectId; // não reenviar autoStart após limpar
    setMessages([]);
    setPending([]);
    setStreaming("");
    load();
  }

  async function resolve(actionId: number, approve: boolean) {
    await api.post(
      `/api/projects/${projectId}/pending-actions/${actionId}/${approve ? "approve" : "reject"}`
    );
    await load();
    if (approve) onApplied();
  }

  async function saveEnv(action: PendingAction) {
    const value = envDrafts[action.id] ?? "";
    await api.put(`/api/projects/${projectId}/env`, {
      key: action.payload.key,
      value,
      secret: true,
    });
    await api.post(`/api/projects/${projectId}/pending-actions/${action.id}/approve`);
    await load();
    onApplied();
  }

  const last = messages[messages.length - 1];
  const activeQuestions =
    last && last.role === "assistant" && last.meta?.questions?.length
      ? (last.meta.questions as any[])
      : null;

  const colCls = centered ? "mx-auto w-full max-w-3xl" : "w-full";

  return (
    <div className="flex h-full flex-col bg-surface">
      <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-ink">Smart Chat</span>
          <span className="badge" data-status={ctx.ai_enabled ? "success" : "inactive"}>
            {ctx.ai_enabled ? "IA ativa" : "modo simulado"}
          </span>
        </div>
        {messages.length > 0 && (
          <button
            onClick={clearChat}
            title="Limpar conversa"
            className="text-xs text-ink3 hover:text-err"
          >
            Limpar conversa
          </button>
        )}
      </div>

      <div className="border-b border-line px-4 py-1.5">
        <div className="flex items-center justify-between text-[11px] text-ink3">
          <span>Contexto da IA</span>
          <span>{ctx.percent}%</span>
        </div>
        <div className="mt-1 h-1.5 overflow-hidden rounded-full" style={{ background: "var(--border)" }}>
          <div
            className="h-full"
            style={{ width: `${Math.min(100, ctx.percent)}%`, background: "var(--brand)" }}
          />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-4">
        <div className={`${colCls} space-y-3`}>
          {messages.length === 0 && !busy && !streaming && (
            <div className="rounded-2xl border border-line bg-surface-2 p-4 text-sm text-ink2">
              Descreva a automação que você quer criar. A IA fará perguntas e
              proporá ações que você aprova antes de aplicar.
            </div>
          )}
          <AnimatePresence initial={false}>
            {messages.map((m) => (
              <div key={m.id} className="space-y-2">
                {m.meta?.execution_report && (
                  <ReportCard report={m.meta.execution_report as ExecutionReport} />
                )}
                <Bubble message={m} />
              </div>
            ))}
          </AnimatePresence>
          {streaming && (
            <Bubble
              streaming
              message={{
                id: -1,
                role: "assistant",
                content: streaming,
                meta: {},
                tokens: 0,
                created_at: "",
              }}
            />
          )}
          {busy && !streaming && <TypingIndicator phase={phase} />}
          <div ref={bottomRef} />
        </div>
      </div>

      {pending.length > 0 && (
        <div
          className="max-h-64 overflow-auto border-t border-line p-3"
          style={{ background: "var(--warn2-soft)" }}
        >
          <div className="mb-2 text-xs font-semibold uppercase text-warn2">
            Pendências ({pending.length})
          </div>
          <div className="space-y-2">
            {pending.map((a) =>
              a.kind === "require_env" ? (
                <div
                  key={a.id}
                  className="rounded-lg border bg-surface p-2.5"
                  style={{ borderColor: "var(--warn2)" }}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-semibold uppercase text-warn2">
                      configuração obrigatória
                    </span>
                  </div>
                  <div className="text-sm font-medium text-ink">
                    {a.payload?.key}
                  </div>
                  {a.payload?.description && (
                    <div className="text-xs text-ink2">
                      {a.payload.description}
                    </div>
                  )}
                  <div className="mt-2 flex gap-2">
                    <input
                      type="password"
                      autoComplete="off"
                      placeholder={a.payload?.example || "valor"}
                      value={envDrafts[a.id] ?? ""}
                      onChange={(e) =>
                        setEnvDrafts((d) => ({ ...d, [a.id]: e.target.value }))
                      }
                      className="input py-1 text-xs"
                    />
                    <button
                      onClick={() => saveEnv(a)}
                      className="btn-accent px-2.5 py-1 text-xs"
                    >
                      Salvar
                    </button>
                  </div>
                  <p className="mt-1 text-[10px] text-warn2">
                    Necessário preencher para testar a automação.
                  </p>
                </div>
              ) : (
                <div
                  key={a.id}
                  className="rounded-lg border bg-surface p-2.5"
                  style={{ borderColor: "var(--warn2)" }}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs text-ink2">{a.kind}</span>
                  </div>
                  <div className="text-sm font-medium text-ink">{a.title}</div>
                  {a.payload?.path && (
                    <div className="text-xs text-ink3">{a.payload.path}</div>
                  )}
                  <div className="mt-2 flex gap-2">
                    <button
                      onClick={() => resolve(a.id, true)}
                      className="btn-accent px-2.5 py-1 text-xs"
                    >
                      Aprovar
                    </button>
                    <button
                      onClick={() => resolve(a.id, false)}
                      className="btn-outline px-2.5 py-1 text-xs"
                    >
                      Rejeitar
                    </button>
                  </div>
                </div>
              )
            )}
          </div>
        </div>
      )}

      {activeQuestions && (
        <InterviewPanel
          projectId={projectId}
          questions={activeQuestions}
          busy={busy}
          centered={centered}
          onAnswer={(t, a) => send(t, a)}
        />
      )}

      {built && !activeQuestions && (
        <div className="border-t border-line px-4 py-2.5" style={{ background: "var(--accent-soft)" }}>
          <div className={`${colCls} flex flex-wrap items-center justify-between gap-2`}>
            <span className="text-sm text-ink">
              Sua automação está pronta para testar.
            </span>
            <button
              onClick={() => nav(`/projects/${projectId}/assistente`)}
              className="btn-accent py-1.5 text-sm"
            >
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <path d="M6 4l14 8-14 8V4z" />
              </svg>
              Testar agora
            </button>
          </div>
        </div>
      )}

      <div className="border-t border-line p-3">
        <div className={colCls}>
        {attached.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1">
            {attached.map((f, i) => (
              <span
                key={i}
                className="badge"
                style={{ background: "var(--accent-soft)", color: "var(--accent)" }}
                title={f.name}
              >
                📎 {f.name}
                <button
                  type="button"
                  onClick={() =>
                    setAttached((a) => a.filter((_, idx) => idx !== i))
                  }
                  className="ml-1 text-accentv hover:text-err"
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2">
          <textarea
            className="input min-h-[42px] resize-none"
            rows={1}
            placeholder={reportExecId ? "Descreva o que ficou errado neste resultado..." : "Descreva o que automatizar..."}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />
          <label className="btn-outline cursor-pointer px-2.5 py-2" title="Anexar">
            📎
            <input
              type="file"
              multiple
              className="hidden"
              onChange={(e) => {
                const fs = Array.from(e.target.files ?? []);
                if (fs.length) setAttached((a) => [...a, ...fs]);
                e.target.value = "";
              }}
            />
          </label>
          <motion.button
            onClick={() => send()}
            disabled={busy}
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.96 }}
            className="btn-primary px-4 py-2"
          >
            Enviar
          </motion.button>
        </div>
        </div>
      </div>
    </div>
  );
}

function Bubble({
  message,
  streaming = false,
}: {
  message: ChatMessage;
  streaming?: boolean;
}) {
  const isUser = message.role === "user";
  const reduce = useReducedMotion();
  return (
    <motion.div
      layout="position"
      initial={reduce ? false : { opacity: 0, y: 10, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 380, damping: 30 }}
      className={`flex items-end gap-2 ${isUser ? "justify-end" : "justify-start"}`}
    >
      {!isUser && <Avatar />}
      <div
        className={`max-w-[85%] rounded-2xl px-3.5 py-2 text-sm shadow-token-sm ${
          isUser
            ? "rounded-br-md"
            : "rounded-bl-md border border-line bg-surface-2 text-ink"
        }`}
        style={isUser ? { background: "var(--user-bubble)", color: "var(--user-text)" } : undefined}
      >
        <MessageContent text={message.content} markdown={!isUser} />
        {streaming && (
          <motion.span
            aria-hidden
            className="ml-0.5 inline-block h-3.5 w-[2px] translate-y-0.5 rounded-full align-middle"
            style={{ background: "var(--accent)" }}
            animate={{ opacity: [1, 0.15, 1] }}
            transition={{ duration: 0.9, repeat: Infinity }}
          />
        )}
      </div>
    </motion.div>
  );
}

/** Avatar do assistente — gradiente da marca, dá rosto à conversa. */
function Avatar() {
  return (
    <div
      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-bold text-white shadow-token-sm"
      style={{ background: "linear-gradient(135deg, var(--brand), var(--accent))" }}
    >
      FD
    </div>
  );
}

/** Status reais que o balão exibe enquanto processa. Reflete a fase atual, não um loop. */
type Fase = "uploading" | "thinking";
const STATUS: Record<Fase, { text: string; emoji: string }> = {
  uploading: { text: "Enviando seus arquivos", emoji: "📎" },
  thinking: { text: "Analisando seu pedido", emoji: "🔎" },
};

/** Texto do status: "digita" letra por letra (revela em sequência, procedural) e as
 * letras já visíveis ondulam bem devagar. As duas animações rodam em conjunto. */
function WaveText({ text, animate }: { text: string; animate: boolean }) {
  return (
    <span className="inline-flex whitespace-pre" aria-label={text}>
      {[...text].map((ch, i) => (
        <motion.span
          key={i}
          aria-hidden
          className="inline-block"
          initial={animate ? { opacity: 0 } : false}
          animate={{ opacity: 1 }}
          transition={animate ? { delay: i * 0.06, duration: 0.12 } : { duration: 0 }}
        >
          <motion.span
            className="inline-block"
            animate={animate ? { y: [0, -3, 0] } : undefined}
            transition={
              animate
                ? { duration: 2.4, repeat: Infinity, delay: i * 0.08, ease: "easeInOut" }
                : undefined
            }
          >
          {ch === " " ? " " : ch}
          </motion.span>
        </motion.span>
      ))}
    </span>
  );
}

/** Indicador de status: mostra a fase atual (com onda nas letras), sem pontinhos e sem loop. */
function TypingIndicator({ phase }: { phase: Fase | null }) {
  const reduce = useReducedMotion();
  const key = phase ?? "thinking";
  const s = STATUS[key];
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-end gap-2"
    >
      <Avatar />
      <motion.div
        layout
        className="flex items-center gap-1.5 rounded-2xl rounded-bl-md border border-line bg-surface-2 px-3.5 py-2.5 text-xs font-medium text-ink2 shadow-token-sm"
        aria-live="polite"
      >
        <AnimatePresence mode="wait">
          <motion.span
            key={key}
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: -4 }}
            transition={{ duration: 0.2 }}
            className="flex items-center gap-1"
          >
            <WaveText text={s.text} animate={!reduce} />
            <span aria-hidden>{s.emoji}</span>
          </motion.span>
        </AnimatePresence>
      </motion.div>
    </motion.div>
  );
}

/** grill-me style: one question at a time with an X/N progress indicator. */
function InterviewPanel({
  projectId,
  questions,
  busy,
  centered = false,
  onAnswer,
}: {
  projectId: number;
  questions: any[];
  busy: boolean;
  centered?: boolean;
  onAnswer: (text: string, attachments?: string[]) => void;
}) {
  const [idx, setIdx] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [draft, setDraft] = useState("");
  const [files, setFiles] = useState<string[]>([]);
  const [working, setWorking] = useState(false);
  const [other, setOther] = useState(false);
  const [otherVal, setOtherVal] = useState("");

  // reset when a new question set arrives
  const sig = useMemo(() => questions.map((q) => q.id).join("|"), [questions]);
  useEffect(() => {
    setIdx(0);
    setAnswers({});
    setDraft("");
    setFiles([]);
    setOther(false);
    setOtherVal("");
  }, [sig]);

  const total = questions.length;
  const q = questions[Math.min(idx, total - 1)];
  if (!q) return null;

  function answer(value: string, extraFile?: string) {
    const nextFiles = extraFile ? [...files, extraFile] : files;
    if (extraFile) setFiles(nextFiles);
    const next: Record<string, string> = { ...answers, [q.id]: value };
    setAnswers(next);
    setDraft("");
    setOther(false);
    setOtherVal("");
    if (idx < total - 1) {
      setIdx(idx + 1);
    } else {
      const text = questions
        .map((qq) => `- ${qq.label || qq.question || qq.text} ${next[qq.id] ?? "(sem resposta)"}`)
        .join("\n");
      onAnswer("Respostas da entrevista:\n" + text, nextFiles);
    }
  }

  async function uploadBase(file: File) {
    setWorking(true);
    try {
      const fd = new FormData();
      fd.append("path", "uploads");
      fd.append("file", file);
      await api.postForm(`/api/projects/${projectId}/fs/upload`, fd);
      answer(`arquivo "${file.name}"`, `uploads/${file.name}`);
    } finally {
      setWorking(false);
    }
  }

  async function generateSample() {
    setWorking(true);
    try {
      const r = await api.post<{ path: string; name: string }>(
        `/api/projects/${projectId}/sample-spreadsheet`
      );
      // download it for the user to inspect/test
      fetch(
        `/api/projects/${projectId}/fs/download?path=${encodeURIComponent(r.path)}`,
        { headers: { Authorization: `Bearer ${getToken()}` } }
      )
        .then((res) => res.blob())
        .then((blob) => {
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = r.name;
          a.click();
        });
      answer(`exemplo gerado "${r.name}"`, r.path);
    } finally {
      setWorking(false);
    }
  }

  const hasOptions = Array.isArray(q.options) && q.options.length > 0;
  const disabled = busy || working;

  return (
    <div className="border-t border-line p-3" style={{ background: "var(--accent-soft)" }}>
      <div className={centered ? "mx-auto w-full max-w-3xl" : "w-full"}>
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs font-semibold text-brandv">
          Só mais algumas perguntas para acertar a automação
        </span>
        <span
          className="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium text-brandv"
          style={{ background: "var(--accent-soft)" }}
        >
          {idx + 1} de {total}
        </span>
      </div>
      <div className="mb-2.5 h-1 w-full overflow-hidden rounded-full" style={{ background: "var(--border)" }}>
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${((idx + 1) / total) * 100}%`, background: "var(--accent)" }}
        />
      </div>
      {idx === 0 && (
        <p className="mb-2 text-xs leading-relaxed text-ink2">
          Pode responder clicando em uma opção ou escrevendo. Se não souber, é só pular.
        </p>
      )}

      <div className="text-sm font-medium text-ink">{q.label || q.question || q.text}</div>

      {hasOptions ? (
        <div className="mt-2">
          <div className="flex flex-wrap gap-1.5">
            {q.options.map((opt: string) => {
              const isRec = q.recommended === opt;
              return (
                <button
                  key={opt}
                  type="button"
                  disabled={disabled}
                  onClick={() => answer(opt)}
                  className={`badge border bg-surface transition disabled:opacity-50 hover:bg-surface-2 ${
                    isRec
                      ? "text-accentv"
                      : "border-line text-ink2 hover:text-ink"
                  }`}
                  style={isRec ? { borderColor: "var(--accent)" } : undefined}
                >
                  {opt}
                  {isRec && " ★"}
                </button>
              );
            })}
            <button
              type="button"
              disabled={disabled}
              onClick={() => setOther((v) => !v)}
              className={`badge border transition ${
                other
                  ? "text-brandv"
                  : "border-dashed border-line bg-surface text-ink2 hover:bg-surface-2"
              }`}
              style={other ? { borderColor: "var(--brand)", background: "var(--accent-soft)" } : undefined}
            >
              Outro…
            </button>
          </div>
          {other && (
            <div className="mt-2 flex gap-2">
              <input
                autoFocus
                className="input"
                placeholder="Digite sua resposta"
                value={otherVal}
                disabled={disabled}
                onChange={(e) => setOtherVal(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && otherVal.trim()) answer(otherVal.trim());
                }}
              />
              <button
                type="button"
                disabled={disabled || !otherVal.trim()}
                onClick={() => answer(otherVal.trim())}
                className="btn-primary py-1.5 text-xs disabled:opacity-50"
              >
                OK
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className="mt-2 flex gap-2">
          <input
            className="input"
            placeholder="Sua resposta"
            value={draft}
            disabled={disabled}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && draft.trim()) answer(draft.trim());
            }}
          />
          <button
            type="button"
            disabled={disabled || !draft.trim()}
            onClick={() => answer(draft.trim())}
            className="btn-primary py-1.5 text-xs disabled:opacity-50"
          >
            OK
          </button>
        </div>
      )}

      {/* upload base file / generate a sample to test */}
      <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-line pt-2 text-xs">
        <label className="btn-outline cursor-pointer py-1 text-xs">
          📎 Subir arquivo base
          <input
            type="file"
            multiple
            className="hidden"
            disabled={disabled}
            onChange={(e) => {
              Array.from(e.target.files ?? []).forEach((f) => uploadBase(f));
              e.target.value = "";
            }}
          />
        </label>
        <button
          type="button"
          disabled={disabled}
          onClick={generateSample}
          className="btn-outline py-1 text-xs disabled:opacity-50"
        >
          {working ? "Gerando..." : "Gerar exemplo p/ testar"}
        </button>
        {files.length > 0 && (
          <span className="text-ok">✓ {files.length} arquivo(s)</span>
        )}
      </div>

      <div className="mt-2 flex items-center justify-between text-[11px]">
        {idx > 0 ? (
          <button
            type="button"
            onClick={() => setIdx(idx - 1)}
            className="text-ink2 hover:text-accentv"
          >
            ← Voltar
          </button>
        ) : (
          <span />
        )}
        <button
          type="button"
          onClick={() => answer("(sem preferência)")}
          className="text-ink3 hover:text-accentv"
        >
          Pular
        </button>
      </div>
      </div>
    </div>
  );
}

/** Splits assistant text into prose and fenced code blocks. The internal
 * flowdesk-actions block is stripped (it drives questions/actions, not display). */
function splitCode(text: string) {
  const cleaned = text.replace(/```flowdesk-actions[\s\S]*?(?:```|$)/g, "").trimEnd();
  const parts: { type: "text" | "code"; lang: string; body: string }[] = [];
  const re = /```(\w*)\n?([\s\S]*?)(?:```|$)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(cleaned))) {
    if (m.index > last)
      parts.push({ type: "text", lang: "", body: cleaned.slice(last, m.index) });
    parts.push({ type: "code", lang: m[1] || "", body: m[2] });
    last = re.lastIndex;
    if (re.lastIndex === m.index) re.lastIndex++;
  }
  if (last < cleaned.length)
    parts.push({ type: "text", lang: "", body: cleaned.slice(last) });
  return parts;
}

/** Componentes de estilo para o markdown do assistente (sem plugin typography). */
const MD_COMPONENTS = {
  p: (props: any) => <p className="mb-2 leading-relaxed last:mb-0" {...props} />,
  strong: (props: any) => <strong className="font-semibold text-ink" {...props} />,
  em: (props: any) => <em className="italic" {...props} />,
  ul: (props: any) => <ul className="my-2 list-disc space-y-1 pl-5" {...props} />,
  ol: (props: any) => <ol className="my-2 list-decimal space-y-1 pl-5" {...props} />,
  li: (props: any) => <li className="leading-relaxed" {...props} />,
  a: (props: any) => <a className="font-medium text-brandv underline" {...props} />,
  h1: (props: any) => <h3 className="mb-1 mt-2 font-semibold text-ink" {...props} />,
  h2: (props: any) => <h3 className="mb-1 mt-2 font-semibold text-ink" {...props} />,
  h3: (props: any) => <h3 className="mb-1 mt-2 font-semibold text-ink" {...props} />,
  code: (props: any) => (
    <code className="rounded bg-surface-2 px-1 py-0.5 font-mono text-[12px] text-brandv" {...props} />
  ),
};

function MessageContent({ text, markdown }: { text: string; markdown?: boolean }) {
  const parts = useMemo(() => splitCode(text), [text]);
  return (
    <>
      {parts.map((p, i) =>
        p.type === "code" ? (
          <CodeBlock key={i} lang={p.lang} body={p.body} />
        ) : markdown ? (
          <ReactMarkdown key={i} components={MD_COMPONENTS}>
            {p.body}
          </ReactMarkdown>
        ) : (
          <span key={i} className="whitespace-pre-wrap">
            {p.body}
          </span>
        )
      )}
    </>
  );
}

function CodeBlock({ lang, body }: { lang: string; body: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="my-2 overflow-hidden rounded-lg text-left" style={{ border: "1px solid #0b1f33" }}>
      <div className="flex items-center justify-between px-3 py-1" style={{ background: "#0b1f33" }}>
        <span className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
          {lang || "código"}
        </span>
        <button
          type="button"
          onClick={() => {
            navigator.clipboard.writeText(body);
            setCopied(true);
            setTimeout(() => setCopied(false), 1200);
          }}
          className="text-[10px] text-slate-400 hover:text-white"
        >
          {copied ? "copiado" : "copiar"}
        </button>
      </div>
      <pre className="overflow-auto p-3 font-mono text-xs leading-relaxed text-slate-100" style={{ background: "#0b1f33" }}>
        <code>{body}</code>
      </pre>
    </div>
  );
}
