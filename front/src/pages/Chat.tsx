import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import type { Project } from "../lib/types";
import TopNav from "../components/TopNav";
import SmartChat from "../components/SmartChat";
import { Spinner } from "../components/ui";

export default function Chat() {
  const [project, setProject] = useState<Project | null>(null);
  const [autoStart, setAutoStart] = useState<{ content: string; files: File[] } | null>(null);
  const [prompt, setPrompt] = useState(() => localStorage.getItem("flowdesk_chat_draft") || "");
  const [files, setFiles] = useState<File[]>([]);
  const [creating, setCreating] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  // keep a draft of the prompt so navigating away does not lose it
  useEffect(() => {
    if (!project) localStorage.setItem("flowdesk_chat_draft", prompt);
  }, [prompt, project]);

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
  }

  function novaConversa() {
    setProject(null);
    setAutoStart(null);
    setPrompt("");
    setFiles([]);
  }

  return (
    <div className="flex h-screen flex-col">
      <TopNav />
      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col overflow-hidden px-4 py-6">
        {!project ? (
          <div className="flex flex-1 flex-col items-center justify-center">
            <div className="w-full">
              <h1 className="text-center text-2xl font-bold text-brand-900">
                O que você quer automatizar?
              </h1>
              <p className="mt-1 text-center text-sm text-slate-500">
                Descreva o processo, anexe um arquivo de exemplo e o Smart Chat monta o
                projeto com você. Um novo projeto é criado automaticamente.
              </p>

              <div
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
                className={`relative mt-6 rounded-2xl border bg-white p-4 shadow-sm transition ${
                  dragOver ? "border-brand-400 ring-2 ring-brand-200" : "border-slate-200"
                }`}
              >
                <textarea
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
                {files.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {files.map((f, i) => (
                      <span key={i} className="badge bg-brand-50 text-brand-600">
                        📎 {f.name}
                        <button
                          onClick={() => setFiles((fs) => fs.filter((_, idx) => idx !== i))}
                          className="ml-1 text-brand-400 hover:text-red-500"
                        >
                          ✕
                        </button>
                      </span>
                    ))}
                  </div>
                )}
                <div className="mt-3 flex items-center justify-between">
                  <label className="btn-outline cursor-pointer py-1.5 text-sm">
                    📎 Anexar arquivo
                    <input
                      type="file"
                      className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) setFiles((fs) => [...fs, f]);
                        e.target.value = "";
                      }}
                    />
                  </label>
                  <button onClick={start} disabled={creating} className="btn-primary">
                    {creating ? <Spinner /> : "Começar →"}
                  </button>
                </div>
                {dragOver && (
                  <div className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-2xl bg-brand-50/90 text-sm font-medium text-brand-700">
                    📎 Solte o arquivo aqui
                  </div>
                )}
              </div>
              <p className="mt-3 text-center text-xs text-slate-400">
                Dica: Ctrl/Cmd + Enter para começar.
              </p>
            </div>
          </div>
        ) : (
          <div className="flex flex-1 flex-col overflow-hidden">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Projeto</div>
                <div className="font-semibold text-brand-900">{project.name}</div>
              </div>
              <div className="flex gap-2">
                <button onClick={novaConversa} className="btn-primary py-1.5 text-sm">
                  + Nova conversa
                </button>
                <Link to={`/projects/${project.id}/editor`} className="btn-outline py-1.5 text-sm">
                  Abrir no editor
                </Link>
                <Link to={`/projects/${project.id}/workflow`} className="btn-outline py-1.5 text-sm">
                  Workflow
                </Link>
              </div>
            </div>
            <div className="flex-1 overflow-hidden rounded-2xl border border-slate-200 shadow-sm">
              <SmartChat
                key={project.id}
                projectId={project.id}
                autoStart={autoStart ?? undefined}
                onApplied={() => {}}
              />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
