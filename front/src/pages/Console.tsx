import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useDialog } from "../components/Dialog";
import type { Folder, Project, TemplateInfo } from "../lib/types";
import { Spinner, StatusBadge } from "../components/ui";
import TopNav from "../components/TopNav";

export default function Console() {
  const dlg = useDialog();
  const nav = useNavigate();
  const { user } = useAuth();
  const isAdmin = !!user?.is_admin;
  const [projects, setProjects] = useState<Project[]>([]);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [instantiating, setInstantiating] = useState("");

  async function useTemplate(key: string) {
    if (instantiating) return;
    setInstantiating(key);
    try {
      const r = await api.post<{ project_id: number }>(`/api/templates/${key}/instantiate`);
      nav(`/projects/${r.project_id}/assistente`);
    } catch (e: any) {
      await dlg.confirm({ title: "Não foi possível criar", message: e?.message || "Erro ao usar o modelo.", confirmLabel: "Entendi" });
      setInstantiating("");
    }
  }

  async function load() {
    // carrega projetos e pastas em paralelo e renderiza juntos (evita o flash em
    // que projetos de pastas somem até as pastas chegarem)
    const [ps, fs, ts] = await Promise.all([
      api.get<Project[]>("/api/projects"),
      api.get<Folder[]>("/api/folders"),
      api.get<TemplateInfo[]>("/api/templates").catch(() => [] as TemplateInfo[]),
    ]);
    setProjects(ps);
    setFolders(fs);
    setTemplates(ts);
    setLoading(false);
  }
  useEffect(() => {
    load();
  }, []);

  function toggleSelect(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function exitSelectMode() {
    setSelectMode(false);
    setSelected(new Set());
  }

  async function bulkDelete() {
    if (selected.size === 0) return;
    const ok = await dlg.confirm({
      title: `Excluir ${selected.size} projeto(s)`,
      message:
        "Esta ação não pode ser desfeita. Versões, execuções e arquivos de todos os projetos selecionados serão removidos.",
      confirmLabel: "Excluir selecionados",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.post("/api/projects/bulk-delete", { ids: [...selected] });
      exitSelectMode();
      load();
    } catch (e: any) {
      await dlg.confirm({
        title: "Não foi possível excluir",
        message:
          (e?.message || "Erro ao excluir os projetos.") +
          " Se o erro persistir, recarregue a página e tente novamente.",
        confirmLabel: "Entendi",
      });
    }
  }

  async function createProject(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    const p = await api.post<Project>("/api/projects", { name: newName });
    setCreating(false);
    setNewName("");
    nav(`/projects/${p.id}/assistente`);
  }

  async function deleteProject(id: number) {
    const ok = await dlg.confirm({
      title: "Excluir projeto",
      message: "Esta ação não pode ser desfeita. Versões, execuções e arquivos do projeto serão removidos.",
      confirmLabel: "Excluir",
      danger: true,
    });
    if (!ok) return;
    await api.del(`/api/projects/${id}`);
    load();
  }

  async function createFolder() {
    const name = await dlg.prompt({ title: "Nova pasta", label: "Nome da pasta", placeholder: "Ex: Fiscal" });
    if (!name?.trim()) return;
    try {
      await api.post("/api/folders", { name: name.trim() });
    } catch (e: any) {
      await dlg.confirm({ title: "Não foi possível criar", message: e?.message || "Erro ao criar a pasta.", confirmLabel: "Entendi" });
    }
    load();
  }

  async function renameFolder(id: number, current: string) {
    const name = await dlg.prompt({ title: "Renomear pasta", label: "Novo nome", defaultValue: current });
    if (!name?.trim()) return;
    try {
      await api.patch(`/api/folders/${id}`, { name: name.trim() });
    } catch (e: any) {
      await dlg.confirm({ title: "Não foi possível renomear", message: e?.message || "Erro ao renomear a pasta.", confirmLabel: "Entendi" });
    }
    load();
  }

  async function deleteFolder(id: number) {
    const ok = await dlg.confirm({
      title: "Excluir pasta",
      message: "Os projetos desta pasta voltam para 'Sem pasta' (não são excluídos).",
      confirmLabel: "Excluir pasta",
      danger: true,
    });
    if (!ok) return;
    await api.del(`/api/folders/${id}`);
    load();
  }

  async function moveProject(id: number, folderId: number | null) {
    await api.patch(`/api/projects/${id}`, folderId === null ? { clear_folder: true } : { folder_id: folderId });
    load();
  }

  async function moveProjectViaMenu(p: Project) {
    const choice = await dlg.selectOption({
      title: "Mover para pasta",
      label: `Projeto: ${p.name}`,
      options: [
        { value: "", label: "Sem pasta" },
        ...folders.map((f) => ({ value: String(f.id), label: f.name })),
      ],
    });
    if (choice === null) return;
    moveProject(p.id, choice === "" ? null : Number(choice));
  }

  const grouped = folders.map((f) => ({
    folder: f,
    items: projects.filter((p) => p.folder_id === f.id),
  }));
  const ungrouped = projects.filter((p) => !p.folder_id);

  return (
    <div className="min-h-full">
      <TopNav />

      <main className="mx-auto max-w-7xl px-6 py-8">
        <>
            <div className="mb-6 flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-bold text-brand-900">Automações</h1>
                <p className="text-sm text-slate-500">
                  {projects.length} automação(ões) · arraste um card para movê-lo entre pastas
                </p>
              </div>
              <div className="flex gap-2">
                {isAdmin &&
                  (selectMode ? (
                    <>
                      <button
                        onClick={bulkDelete}
                        disabled={selected.size === 0}
                        className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Excluir selecionados ({selected.size})
                      </button>
                      <button onClick={exitSelectMode} className="btn-ghost">
                        Cancelar
                      </button>
                    </>
                  ) : (
                    <button onClick={() => setSelectMode(true)} className="btn-outline">
                      Selecionar
                    </button>
                  ))}
                <button onClick={createFolder} className="btn-outline">
                  + Nova pasta
                </button>
                <button onClick={() => setCreating(true)} className="btn-primary">
                  + Nova automação
                </button>
              </div>
            </div>

            {creating && (
              <form
                onSubmit={createProject}
                className="card mb-6 flex items-center gap-3 p-4"
              >
                <input
                  autoFocus
                  className="input"
                  placeholder="Nome do projeto"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                />
                <button className="btn-primary">Criar</button>
                <button
                  type="button"
                  onClick={() => setCreating(false)}
                  className="btn-ghost"
                >
                  Cancelar
                </button>
              </form>
            )}

            {!loading && templates.length > 0 && (
              <section className="mb-8">
                <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
                  Comece com um modelo
                </h2>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {templates.map((t) => (
                    <button
                      key={t.key}
                      onClick={() => useTemplate(t.key)}
                      disabled={!!instantiating}
                      className="rounded-xl border border-dashed border-brand-200 bg-brand-50/40 p-4 text-left transition hover:border-accent-400 hover:bg-accent-400/5 disabled:opacity-60"
                    >
                      <div className="font-medium text-brand-900">
                        {instantiating === t.key ? "Criando…" : t.name}
                      </div>
                      <div className="mt-1 text-sm text-slate-500">{t.description}</div>
                    </button>
                  ))}
                </div>
              </section>
            )}

            {loading ? (
              <div className="flex justify-center py-20">
                <Spinner className="h-8 w-8 text-brand-600" />
              </div>
            ) : (
              <>
                {grouped.map(({ folder, items }) => (
                  <Section
                    key={folder.id}
                    title={folder.name}
                    count={items.length}
                    projects={items}
                    onDelete={deleteProject}
                    onMoveMenu={moveProjectViaMenu}
                    folderId={folder.id}
                    onDropProject={(id) => moveProject(id, folder.id)}
                    onRenameFolder={() => renameFolder(folder.id, folder.name)}
                    onDeleteFolder={() => deleteFolder(folder.id)}
                    selectMode={selectMode}
                    selected={selected}
                    onToggleSelect={toggleSelect}
                  />
                ))}
                <Section
                  title="Sem pasta"
                  count={ungrouped.length}
                  projects={ungrouped}
                  onDelete={deleteProject}
                  onMoveMenu={moveProjectViaMenu}
                  onDropProject={(id) => moveProject(id, null)}
                  selectMode={selectMode}
                  selected={selected}
                  onToggleSelect={toggleSelect}
                />
              </>
            )}
        </>
      </main>
    </div>
  );
}

function Section({
  title,
  count,
  projects,
  onDelete,
  onMoveMenu,
  folderId,
  onDropProject,
  onRenameFolder,
  onDeleteFolder,
  selectMode,
  selected,
  onToggleSelect,
}: {
  title: string;
  count: number;
  projects: Project[];
  onDelete: (id: number) => void;
  onMoveMenu: (p: Project) => void;
  folderId?: number;
  onDropProject?: (id: number) => void;
  onRenameFolder?: () => void;
  onDeleteFolder?: () => void;
  selectMode: boolean;
  selected: Set<number>;
  onToggleSelect: (id: number) => void;
}) {
  const [menu, setMenu] = useState(false);
  const [over, setOver] = useState(false);
  // hide only the virtual "Sem pasta" group when empty; keep real (empty) folders
  if (projects.length === 0 && !folderId) return null;
  return (
    <section
      className="mb-8"
      onDragOver={(e) => {
        if (onDropProject) {
          e.preventDefault();
          setOver(true);
        }
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        setOver(false);
        const id = Number(e.dataTransfer.getData("text/plain"));
        if (id && onDropProject) onDropProject(id);
      }}
    >
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-slate-400">
        {folderId && <span className="text-base">📁</span>}
        {title}
        <span className="rounded-full bg-slate-100 px-2 text-xs text-slate-500">
          {count}
        </span>
        {folderId && (
          <span className="relative">
            <button
              onClick={() => setMenu((m) => !m)}
              className="rounded px-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            >
              ⋮
            </button>
            {menu && (
              <div
                className="absolute left-0 top-6 z-20 w-36 rounded-lg border border-slate-200 bg-white py-1 text-left normal-case shadow-lg"
                onClick={() => setMenu(false)}
              >
                <button
                  onClick={onRenameFolder}
                  className="block w-full px-3 py-1.5 text-left text-sm text-slate-600 hover:bg-slate-50"
                >
                  Renomear pasta
                </button>
                <button
                  onClick={onDeleteFolder}
                  className="block w-full px-3 py-1.5 text-left text-sm text-red-600 hover:bg-red-50"
                >
                  Excluir pasta
                </button>
              </div>
            )}
          </span>
        )}
      </h2>
      {projects.length === 0 ? (
        <div
          className={`rounded-xl border border-dashed p-6 text-center text-sm transition ${
            over ? "border-brand-400 bg-brand-50 text-brand-600" : "border-slate-200 text-slate-400"
          }`}
        >
          {over ? "Solte aqui para mover" : "Pasta vazia — arraste projetos para cá"}
        </div>
      ) : (
        <div
          className={`grid grid-cols-1 gap-4 rounded-xl sm:grid-cols-2 lg:grid-cols-3 ${
            over ? "ring-2 ring-brand-300 ring-offset-4" : ""
          }`}
        >
          {projects.map((p) => (
            <ProjectCard
              key={p.id}
              project={p}
              onDelete={onDelete}
              onMove={onMoveMenu}
              selectMode={selectMode}
              selected={selected.has(p.id)}
              onToggleSelect={onToggleSelect}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function ProjectCard({
  project,
  onDelete,
  onMove,
  selectMode,
  selected,
  onToggleSelect,
}: {
  project: Project;
  onDelete: (id: number) => void;
  onMove: (p: Project) => void;
  selectMode: boolean;
  selected: boolean;
  onToggleSelect: (id: number) => void;
}) {
  const nav = useNavigate();
  const [menu, setMenu] = useState(false);
  const live = project.status === "live";
  return (
    <div
      draggable={!selectMode}
      onDragStart={(e) => {
        e.dataTransfer.setData("text/plain", String(project.id));
        e.dataTransfer.effectAllowed = "move";
      }}
      onClick={() =>
        selectMode ? onToggleSelect(project.id) : nav(`/projects/${project.id}/assistente`)
      }
      className={`group relative flex cursor-pointer flex-col rounded-2xl border bg-white p-5 pl-6 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-brand-900/5 active:cursor-grabbing ${
        selectMode && selected
          ? "border-brand-500 ring-2 ring-brand-400/60"
          : "border-slate-200/80 hover:border-brand-200"
      }`}
    >
      {/* trilho lateral indica o status (no ar / rascunho) */}
      <span
        className={`pointer-events-none absolute bottom-4 left-0 top-4 w-1 rounded-r-full transition-all duration-200 group-hover:bottom-3 group-hover:top-3 ${
          live ? "bg-accent-400" : "bg-slate-200"
        }`}
      />

      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-start gap-2.5">
          {selectMode && (
            <input
              type="checkbox"
              checked={selected}
              onChange={() => onToggleSelect(project.id)}
              onClick={(e) => e.stopPropagation()}
              className="mt-1 h-4 w-4 shrink-0 accent-brand-600"
            />
          )}
          <h3 className="line-clamp-2 font-semibold leading-snug text-brand-900 transition-colors group-hover:text-brand-700">
            {project.name}
          </h3>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <StatusBadge status={project.status} />
          {!selectMode && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setMenu((m) => !m);
              }}
              className="rounded-md px-1 text-lg leading-none text-slate-300 transition hover:bg-slate-100 hover:text-slate-600"
            >
              ⋮
            </button>
          )}
        </div>
      </div>

      {menu && (
        <div
          className="absolute right-3 top-12 z-20 w-44 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-xl ring-1 ring-slate-900/5"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            onClick={() => {
              setMenu(false);
              onMove(project);
            }}
            className="block w-full px-3 py-2 text-left text-sm text-slate-600 transition hover:bg-slate-50"
          >
            Mover para pasta
          </button>
          <button
            onClick={() => {
              setMenu(false);
              onDelete(project.id);
            }}
            className="block w-full px-3 py-2 text-left text-sm text-red-600 transition hover:bg-red-50"
          >
            Excluir projeto
          </button>
        </div>
      )}

      <p className="mt-1.5 line-clamp-2 text-sm leading-relaxed text-slate-500">
        {project.description || "Sem descrição"}
      </p>

      <a
        href={`/app/${project.subdomain}`}
        target="_blank"
        rel="noreferrer"
        onClick={(e) => e.stopPropagation()}
        className="mt-4 inline-flex max-w-full items-center gap-1.5 self-start rounded-md bg-slate-50 px-2 py-1 font-mono text-[11px] text-brand-600 ring-1 ring-inset ring-slate-200/70 transition hover:bg-brand-50 hover:text-brand-700 hover:ring-brand-200"
        title={`Abrir app publicado: /app/${project.subdomain}`}
      >
        <svg viewBox="0 0 24 24" fill="none" className="h-3 w-3 shrink-0 opacity-70" aria-hidden>
          <path d="M7 17 17 7M9 7h8v8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="truncate">/app/{project.subdomain}</span>
      </a>

      <div className="mt-4 flex items-center justify-end gap-1 border-t border-slate-100 pt-3 text-xs">
        <CardLink to={`/projects/${project.id}/workflow`}>Workflow</CardLink>
        <CardLink to={`/projects/${project.id}/logs`}>Logs</CardLink>
      </div>
    </div>
  );
}

function CardLink({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <Link
      to={to}
      onClick={(e) => e.stopPropagation()}
      className="rounded-md px-2 py-1 font-medium text-slate-400 transition hover:bg-brand-50 hover:text-brand-700"
    >
      {children}
    </Link>
  );
}
