import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion, AnimatePresence, useReducedMotion, type Variants } from "framer-motion";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { Project, TemplateInfo } from "../lib/types";
import TopNav from "../components/TopNav";
import SmartChat from "../components/SmartChat";
import { Spinner } from "../components/ui";

const SUGGESTIONS = [
  "Conciliar débito e crédito de um razão contábil que se zeram",
  "Remover linhas duplicadas de uma planilha pela coluna Valor",
  "Somar notas por CNPJ e gerar um resumo em Excel",
  "Gerar um relatório mensal de despesas a partir de um CSV",
];

export default function Chat() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [autoStart, setAutoStart] = useState<{ content: string; files: File[] } | null>(null);
  const [prompt, setPrompt] = useState(() => localStorage.getItem("flowdesk_chat_draft") || "");
  const [files, setFiles] = useState<File[]>([]);
  const [creating, setCreating] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [instantiating, setInstantiating] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);
  const reduce = useReducedMotion();

  const firstName = (user?.name || "").trim().split(" ")[0] || "tudo bem";

  useEffect(() => {
    if (!project) localStorage.setItem("flowdesk_chat_draft", prompt);
  }, [prompt, project]);

  useEffect(() => {
    api.get<TemplateInfo[]>("/api/templates").then(setTemplates).catch(() => {});
  }, []);

  async function useTemplate(key: string) {
    if (instantiating) return;
    setInstantiating(key);
    try {
      const r = await api.post<{ project_id: number }>(`/api/templates/${key}/instantiate`);
      nav(`/projects/${r.project_id}/assistente`);
    } catch {
      setInstantiating("");
    }
  }

  async function start() {
    if (!prompt.trim() && files.length === 0) return;
    setCreating(true);
    const name =
      (prompt.trim().split("\n")[0].slice(0, 48) || "Conversa") +
      (prompt.length > 48 ? "…" : "");
    const p = await api.post<Project>("/api/projects", {
      name,
      description: "Criado pelo Chat",
    });
    setProject(p);
    setAutoStart({ content: prompt.trim() || "Analise o arquivo anexado.", files });
    localStorage.removeItem("flowdesk_chat_draft");
    setCreating(false);
    // melhora o nome em segundo plano (IA gera um título curto a partir do pedido)
    if (prompt.trim()) {
      api
        .post<{ name: string }>(`/api/projects/${p.id}/auto-name`, { prompt: prompt.trim() })
        .then((r) => r?.name && setProject((cur) => (cur ? { ...cur, name: r.name } : cur)))
        .catch(() => {});
    }
  }

  function novaConversa() {
    setProject(null);
    setAutoStart(null);
    setPrompt("");
    setFiles([]);
  }

  function useSuggestion(s: string) {
    setPrompt(s);
    taRef.current?.focus();
  }

  const container: Variants = {
    hidden: {},
    show: {
      transition: { staggerChildren: reduce ? 0 : 0.08, delayChildren: 0.05 },
    },
  };
  const item: Variants = {
    hidden: { opacity: 0, y: reduce ? 0 : 14 },
    show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 320, damping: 26 } },
  };

  return (
    <div className="flex h-screen flex-col">
      <TopNav />
      <AnimatePresence mode="wait">
        {!project ? (
          <motion.main
            key="hero"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="relative flex flex-1 flex-col items-center justify-center overflow-hidden px-4"
          >
            {/* atmosfera: gradiente suave da marca + brilho */}
            <div
              className="pointer-events-none absolute inset-0 -z-10"
              style={{ background: "linear-gradient(to bottom, var(--accent-soft), var(--bg) 55%, var(--accent-soft))" }}
            />
            <div
              className="pointer-events-none absolute left-1/2 top-1/4 -z-10 h-72 w-72 -translate-x-1/2 rounded-full blur-3xl"
              style={{ background: "var(--accent-glow)" }}
            />

            <motion.div
              variants={container}
              initial="hidden"
              animate="show"
              className="w-full max-w-2xl"
            >
              <motion.div variants={item} className="mb-1 text-center text-sm font-medium text-accentv">
                Olá, {firstName} 👋
              </motion.div>
              <motion.h1
                variants={item}
                className="text-center text-3xl font-bold tracking-tight text-ink"
              >
                O que vamos automatizar hoje?
              </motion.h1>
              <motion.p variants={item} className="mx-auto mt-2 max-w-lg text-center text-sm text-ink2">
                Descreva o processo em português e anexe um exemplo. O Smart Chat cria um
                projeto e monta a automação com você, passo a passo.
              </motion.p>

              <motion.div
                variants={item}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={(e) => {
                  e.preventDefault();
                  setDragOver(false);
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(false);
                  const dropped = Array.from(e.dataTransfer.files || []);
                  if (dropped.length) setFiles((fs) => [...fs, ...dropped]);
                }}
                animate={{
                  boxShadow: dragOver
                    ? "0 20px 50px -12px rgba(24,177,168,0.35)"
                    : "0 10px 30px -15px rgba(10,31,51,0.25)",
                }}
                className={`relative mt-7 rounded-2xl border bg-surface p-4 transition-colors ${
                  dragOver ? "border-accentv ring-2 ring-accent-200" : "border-line"
                }`}
              >
                <textarea
                  ref={taRef}
                  autoFocus
                  rows={4}
                  className="input resize-none border-0 text-base focus:ring-0"
                  placeholder="Ex: tenho um razão contábil em xlsx e quero conciliar débito x crédito que se zeram, mantendo todos os registros…"
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) start();
                  }}
                />
                <AnimatePresence>
                  {files.length > 0 && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      className="mt-2 flex flex-wrap gap-1.5 overflow-hidden"
                    >
                      {files.map((f, i) => (
                        <span
                          key={i}
                          className="badge"
                          style={{ background: "var(--accent-soft)", color: "var(--accent)" }}
                        >
                          📎 {f.name}
                          <button
                            onClick={() => setFiles((fs) => fs.filter((_, idx) => idx !== i))}
                            className="ml-1 text-accentv hover:text-err"
                          >
                            ✕
                          </button>
                        </span>
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>
                <div className="mt-3 flex items-center justify-between">
                  <label className="btn-outline cursor-pointer py-1.5 text-sm">
                    📎 Anexar arquivo
                    <input
                      type="file"
                      multiple
                      className="hidden"
                      onChange={(e) => {
                        const sel = Array.from(e.target.files ?? []);
                        if (sel.length) setFiles((fs) => [...fs, ...sel]);
                        e.target.value = "";
                      }}
                    />
                  </label>
                  <motion.button
                    onClick={start}
                    disabled={creating}
                    whileHover={{ scale: 1.04 }}
                    whileTap={{ scale: 0.96 }}
                    className="btn-primary"
                  >
                    {creating ? <Spinner /> : "Começar →"}
                  </motion.button>
                </div>
                <AnimatePresence>
                  {dragOver && (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-2xl text-sm font-medium text-accentv"
                      style={{ background: "var(--accent-soft)" }}
                    >
                      📎 Solte o arquivo aqui
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>

              {/* chips de sugestão: fila horizontal rolável (evita empilhar frases longas) */}
              <motion.div
                variants={item}
                className="mt-5 flex gap-2 overflow-x-auto pb-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
              >
                {SUGGESTIONS.map((s) => (
                  <motion.button
                    key={s}
                    onClick={() => useSuggestion(s)}
                    whileHover={{ scale: 1.04, y: -2 }}
                    whileTap={{ scale: 0.97 }}
                    className="shrink-0 whitespace-nowrap rounded-full border border-line bg-surface/70 px-3 py-1.5 text-xs text-ink2 backdrop-blur transition-colors hover:border-accentv hover:text-ink"
                  >
                    {s}
                  </motion.button>
                ))}
              </motion.div>

              <motion.p variants={item} className="mt-4 text-center text-xs text-ink3">
                Dica: Ctrl/Cmd + Enter para começar.
              </motion.p>

              {templates.length > 0 && (
                <motion.div variants={item} className="mt-8">
                  <h2 className="mb-3 text-center text-xs font-bold uppercase tracking-wide text-ink3">
                    Ou comece com um modelo
                  </h2>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {templates.map((t) => (
                      <button
                        key={t.key}
                        onClick={() => useTemplate(t.key)}
                        disabled={!!instantiating}
                        className="rounded-2xl border border-dashed border-line-strong p-4 text-left transition hover:border-accentv disabled:opacity-60"
                        style={{ background: "var(--accent-soft)" }}
                      >
                        <div className="font-semibold text-ink">
                          {instantiating === t.key ? "Criando…" : t.name}
                        </div>
                        <div className="mt-1 text-sm text-ink2">{t.description}</div>
                      </button>
                    ))}
                  </div>
                </motion.div>
              )}
            </motion.div>
          </motion.main>
        ) : (
          <motion.main
            key="conversation"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-1 flex-col overflow-hidden bg-surface-2"
          >
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass flex items-center justify-between border-b border-line px-5 py-2.5"
            >
              <div className="min-w-0">
                <div className="text-[11px] uppercase tracking-wide text-ink3">Projeto</div>
                <div className="truncate font-semibold text-ink">{project.name}</div>
              </div>
              <div className="flex gap-2">
                <motion.button
                  onClick={novaConversa}
                  whileTap={{ scale: 0.96 }}
                  className="btn-primary py-1.5 text-sm"
                >
                  + Nova conversa
                </motion.button>
                <Link to={`/projects/${project.id}/editor`} className="btn-outline py-1.5 text-sm">
                  Abrir no editor
                </Link>
                <Link to={`/projects/${project.id}/workflow`} className="btn-outline py-1.5 text-sm">
                  Workflow
                </Link>
              </div>
            </motion.div>
            <div className="flex-1 overflow-hidden">
              <SmartChat
                key={project.id}
                projectId={project.id}
                autoStart={autoStart ?? undefined}
                onApplied={() => {}}
                centered
              />
            </div>
          </motion.main>
        )}
      </AnimatePresence>
    </div>
  );
}
