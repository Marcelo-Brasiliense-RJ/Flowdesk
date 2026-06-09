import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useDialog } from "../components/Dialog";
import type { Folder, Project } from "../lib/types";
import { StatusBadge } from "../components/ui";
import TopNav from "../components/TopNav";

export default function Console() {
  const dlg = useDialog();
  const nav = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");

  async function load() {
    setProjects(await api.get<Project[]>("/api/projects"));
    setFolders(await api.get<Folder[]>("/api/folders"));
  }
  useEffect(() => {
    load();
  }, []);

  async function createProject(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    const p = await api.post<Project>("/api/projects", { name: newName });
    setCreating(false);
    setNewName("");
    nav(`/projects/${p.id}/editor`);
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
    await api.post("/api/folders", { name: name.trim() });
    load();
  }

  async function renameFolder(id: number, current: string) {
    const name = await dlg.prompt({ title: "Renomear pasta", label: "Novo nome", defaultValue: current });
    if (!name?.trim()) return;
    await api.patch(`/api/folders/${id}`, { name: name.trim() });
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
                <h1 className="text-2xl font-bold text-brand-900">Projetos</h1>
                <p className="text-sm text-slate-500">
                  {projects.length} projeto(s) de automação · arraste um card para movê-lo entre pastas
                </p>
              </div>
              <div className="flex gap-2">
                <button onClick={createFolder} className="btn-outline">
                  + Nova pasta
                </button>
                <button onClick={() => setCreating(true)} className="btn-primary">
                  + Novo projeto
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
              />
            ))}
            <Section
              title="Sem pasta"
              count={ungrouped.length}
              projects={ungrouped}
              onDelete={deleteProject}
              onMoveMenu={moveProjectViaMenu}
              onDropProject={(id) => moveProject(id, null)}
            />
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
            <ProjectCard key={p.id} project={p} onDelete={onDelete} onMove={onMoveMenu} />
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
}: {
  project: Project;
  onDelete: (id: number) => void;
  onMove: (p: Project) => void;
}) {
  const nav = useNavigate();
  const [menu, setMenu] = useState(false);
  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData("text/plain", String(project.id));
        e.dataTransfer.effectAllowed = "move";
      }}
      onClick={() => nav(`/projects/${project.id}/editor`)}
      className="card group relative cursor-pointer p-5 transition hover:border-brand-300 hover:shadow-md active:cursor-grabbing"
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-semibold text-brand-900 group-hover:text-brand-700">
          {project.name}
        </h3>
        <div className="flex shrink-0 items-center gap-1">
          <StatusBadge status={project.status} />
          <button
            onClick={(e) => {
              e.stopPropagation();
              setMenu((m) => !m);
            }}
            className="rounded px-1 text-lg leading-none text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            ⋮
          </button>
        </div>
      </div>
      {menu && (
        <div
          className="absolute right-3 top-12 z-20 w-40 rounded-lg border border-slate-200 bg-white py-1 shadow-lg"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            onClick={() => {
              setMenu(false);
              onMove(project);
            }}
            className="block w-full px-3 py-1.5 text-left text-sm text-slate-600 hover:bg-slate-50"
          >
            Mover para pasta
          </button>
          <button
            onClick={() => {
              setMenu(false);
              onDelete(project.id);
            }}
            className="block w-full px-3 py-1.5 text-left text-sm text-red-600 hover:bg-red-50"
          >
            Excluir projeto
          </button>
        </div>
      )}
      <p className="mt-1 line-clamp-2 text-sm text-slate-500">
        {project.description || "Sem descrição"}
      </p>
      <div className="mt-4 flex items-center justify-between text-xs">
        <a
          href={`/app/${project.subdomain}`}
          target="_blank"
          rel="noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="font-mono text-brand-500 hover:underline"
        >
          /app/{project.subdomain}
        </a>
        <span className="flex gap-2 text-slate-400">
          <CardLink to={`/projects/${project.id}/workflow`}>Workflow</CardLink>
          <CardLink to={`/projects/${project.id}/logs`}>Logs</CardLink>
        </span>
      </div>
    </div>
  );
}

function CardLink({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <Link
      to={to}
      onClick={(e) => e.stopPropagation()}
      className="hover:text-brand-600"
    >
      {children}
    </Link>
  );
}
