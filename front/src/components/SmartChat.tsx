import { useEffect, useMemo, useRef, useState } from "react";
import { api, getToken } from "../lib/api";
import { useDialog } from "./Dialog";
import type { ChatMessage, PendingAction } from "../lib/types";
import { Spinner } from "./ui";

export default function SmartChat({
  projectId,
  onApplied,
  autoStart,
}: {
  projectId: number;
  onApplied: () => void;
  autoStart?: { content: string; files: File[] };
}) {
  const dlg = useDialog();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState<PendingAction[]>([]);
  const [streaming, setStreaming] = useState("");
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [ctx, setCtx] = useState({ percent: 0, ai_enabled: false });
  const [attached, setAttached] = useState<File[]>([]);
  const [envDrafts, setEnvDrafts] = useState<Record<number, string>>({});
  const bottomRef = useRef<HTMLDivElement>(null);
  const autoStartedFor = useRef<number | null>(null);

  async function load() {
    setMessages(await api.get<ChatMessage[]>(`/api/projects/${projectId}/chat`));
    setPending(
      await api.get<PendingAction[]>(`/api/projects/${projectId}/pending-actions`)
    );
    setCtx(await api.get(`/api/projects/${projectId}/chat/context`));
  }
  useEffect(() => {
    // reset state when switching projects so no stale conversation leaks in
    setMessages([]);
    setPending([]);
    setStreaming("");
    load();
  }, [projectId]);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
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
    const base = textOverride ?? input;
    const extra = attachmentsOverride ?? [];
    const files = filesOverride ?? (textOverride ? [] : attached);
    if ((!base.trim() && files.length === 0 && extra.length === 0) || busy) return;
    if (!textOverride) setInput("");
    setAttached([]);
    let content = base;
    setBusy(true);
    setStreaming("");
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

  return (
    <div className="flex h-full flex-col bg-white">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-brand-900">Smart Chat</span>
          <span
            className={`badge ${
              ctx.ai_enabled
                ? "bg-emerald-100 text-emerald-700"
                : "bg-slate-100 text-slate-500"
            }`}
          >
            {ctx.ai_enabled ? "IA ativa" : "modo simulado"}
          </span>
        </div>
        {messages.length > 0 && (
          <button
            onClick={clearChat}
            title="Limpar conversa"
            className="text-xs text-slate-400 hover:text-red-600"
          >
            Limpar conversa
          </button>
        )}
      </div>

      <div className="border-b border-slate-100 px-4 py-1.5">
        <div className="flex items-center justify-between text-[11px] text-slate-400">
          <span>Contexto da IA</span>
          <span>{ctx.percent}%</span>
        </div>
        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
          <div
            className="h-full bg-brand-500"
            style={{ width: `${Math.min(100, ctx.percent)}%` }}
          />
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-auto p-4">
        {messages.length === 0 && (
          <div className="rounded-lg bg-slate-50 p-4 text-sm text-slate-500">
            Descreva a automação que você quer criar. A IA fará perguntas e
            proporá ações que você aprova antes de aplicar.
          </div>
        )}
        {messages.map((m) => (
          <Bubble key={m.id} message={m} />
        ))}
        {streaming && (
          <Bubble
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
        {busy && !streaming && (
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Spinner className="h-4 w-4" /> pensando...
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {pending.length > 0 && (
        <div className="max-h-64 overflow-auto border-t border-slate-200 bg-amber-50 p-3">
          <div className="mb-2 text-xs font-semibold uppercase text-amber-700">
            Pendências ({pending.length})
          </div>
          <div className="space-y-2">
            {pending.map((a) =>
              a.kind === "require_env" ? (
                <div
                  key={a.id}
                  className="rounded-lg border border-orange-300 bg-white p-2.5"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-semibold uppercase text-orange-600">
                      configuração obrigatória
                    </span>
                  </div>
                  <div className="text-sm font-medium text-brand-900">
                    {a.payload?.key}
                  </div>
                  {a.payload?.description && (
                    <div className="text-xs text-slate-500">
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
                  <p className="mt-1 text-[10px] text-orange-600">
                    Necessário preencher para testar a automação.
                  </p>
                </div>
              ) : (
                <div
                  key={a.id}
                  className="rounded-lg border border-amber-200 bg-white p-2.5"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs text-slate-500">{a.kind}</span>
                  </div>
                  <div className="text-sm font-medium text-brand-900">{a.title}</div>
                  {a.payload?.path && (
                    <div className="text-xs text-slate-400">{a.payload.path}</div>
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
          onAnswer={(t, a) => send(t, a)}
        />
      )}

      <div className="border-t border-slate-200 p-3">
        {attached.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1">
            {attached.map((f, i) => (
              <span
                key={i}
                className="badge bg-brand-50 text-brand-600"
                title={f.name}
              >
                📎 {f.name}
                <button
                  type="button"
                  onClick={() =>
                    setAttached((a) => a.filter((_, idx) => idx !== i))
                  }
                  className="ml-1 text-brand-400 hover:text-red-500"
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
            placeholder="Descreva o que automatizar..."
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
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) setAttached((a) => [...a, f]);
                e.target.value = "";
              }}
            />
          </label>
          <button onClick={() => send()} disabled={busy} className="btn-primary px-4 py-2">
            Enviar
          </button>
        </div>
      </div>
    </div>
  );
}

function Bubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[90%] rounded-2xl px-3.5 py-2 text-sm ${
          isUser
            ? "bg-brand-700 text-white"
            : "border border-slate-200 bg-white text-slate-700"
        }`}
      >
        <MessageContent text={message.content} />
      </div>
    </div>
  );
}

/** grill-me style: one question at a time with an X/N progress indicator. */
function InterviewPanel({
  projectId,
  questions,
  busy,
  onAnswer,
}: {
  projectId: number;
  questions: any[];
  busy: boolean;
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
    <div className="border-t border-slate-200 bg-brand-50/70 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-brand-700">
          Entrevista
        </span>
        <span className="rounded-full bg-brand-100 px-2 py-0.5 text-[11px] font-medium text-brand-700">
          {idx + 1}/{total}
        </span>
      </div>

      <div className="text-sm font-medium text-brand-900">{q.label || q.question || q.text}</div>

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
                  className={`badge border transition disabled:opacity-50 ${
                    isRec
                      ? "border-accent-500 bg-white text-accent-600 hover:bg-accent-50"
                      : "border-slate-300 bg-white text-slate-600 hover:border-brand-400 hover:text-brand-700"
                  }`}
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
                  ? "border-brand-500 bg-brand-50 text-brand-700"
                  : "border-dashed border-slate-300 bg-white text-slate-500 hover:border-brand-400"
              }`}
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
      <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-brand-100 pt-2 text-xs">
        <label className="btn-outline cursor-pointer py-1 text-xs">
          📎 Subir arquivo base
          <input
            type="file"
            className="hidden"
            disabled={disabled}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) uploadBase(f);
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
          <span className="text-emerald-600">✓ {files.length} arquivo(s)</span>
        )}
      </div>

      <div className="mt-2 flex items-center justify-between text-[11px]">
        {idx > 0 ? (
          <button
            type="button"
            onClick={() => setIdx(idx - 1)}
            className="text-slate-500 hover:text-brand-700"
          >
            ← Voltar
          </button>
        ) : (
          <span />
        )}
        <button
          type="button"
          onClick={() => answer("(sem preferência)")}
          className="text-slate-400 hover:text-brand-600"
        >
          Pular
        </button>
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

function MessageContent({ text }: { text: string }) {
  const parts = useMemo(() => splitCode(text), [text]);
  return (
    <>
      {parts.map((p, i) =>
        p.type === "code" ? (
          <CodeBlock key={i} lang={p.lang} body={p.body} />
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
    <div className="my-2 overflow-hidden rounded-lg border border-slate-700 text-left">
      <div className="flex items-center justify-between bg-slate-800 px-3 py-1">
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
      <pre className="overflow-auto bg-slate-900 p-3 font-mono text-xs leading-relaxed text-slate-100">
        <code>{body}</code>
      </pre>
    </div>
  );
}
