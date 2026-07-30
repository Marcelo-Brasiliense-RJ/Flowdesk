import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useDialog } from "../components/Dialog";
import type { Folder, Project } from "../lib/types";
import { Spinner, StatusBadge } from "../components/ui";
import TopNav from "../components/TopNav";

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

// ponytail: favoritos por navegador (localStorage); trocar por coluna/endpoint se precisar sincronizar entre dispositivos
const FAV_KEY = "flowdesk_favorites";
function loadFavs(): Set<number> {
  try {
    return new Set(JSON.parse(localStorage.getItem(FAV_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

function fmtData(iso?: string) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const hoje = new Date();
  if (d.toDateString() === hoje.toDateString()) {
    return `hoje, ${d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
  }
  return `${d.getDate()} ${MESES[d.getMonth()]} ${d.getFullYear()}`;
}

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
  const [favorites, setFavorites] = useState<Set<number>>(loadFavs);

  function toggleFavorite(id: number) {
    setFavorites((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      localStorage.setItem(FAV_KEY, JSON.stringify([...next]));
      return next;
    });
  }

  async function load() {
    // carrega projetos e pastas em paralelo e renderiza juntos (evita o flash em
    // que projetos de pastas somem até as pastas chegarem)
    const [ps, fs] = await Promise.all([
      api.get<Project[]>("/api/projects"),
      api.get<Folder[]>("/api/folders"),
    ]);
    setProjects(ps);
    setFolders(fs);
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
    const n = selected.size;
    if (n === 0) return;
    const ok = await dlg.confirm({
      title: `Excluir ${n} projeto(s)`,
      message:
        "Esta ação não pode ser desfeita. Versões, execuções e arquivos de todos os projetos selecionados serão removidos.",
      confirmLabel: "Excluir selecionados",
      danger: true,
    });
    if (!ok) return;
    try {
      const r = await api.post<{ deleted: number }>("/api/projects/bulk-delete", {
        ids: [...selected],
      });
      exitSelectMode();
      await load();
      // feedback explícito: a lista some sozinha, mas o usuário precisa de confirmação
      await dlg.confirm({
        title:
          r.deleted >= n
            ? `${r.deleted} projeto(s) excluído(s)`
            : `${r.deleted} de ${n} projeto(s) excluído(s)`,
        message:
          r.deleted < n
            ? "Os demais não foram excluídos: podem já ter sido removidos ou pertencer a outra organização."
            : undefined,
        confirmLabel: "Entendi",
      });
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
  // "Sem pasta" mostra só o que está no ar; rascunhos sem pasta vão para a seção "Rascunhos"
  const ungroupedLive = projects.filter((p) => !p.folder_id && p.status === "live");
  const drafts = projects.filter((p) => !p.folder_id && p.status === "draft");
  const favorited = projects.filter((p) => favorites.has(p.id));

  return (
    <div className="min-h-full">
      <TopNav />

      <main className="mx-auto max-w-7xl px-6 py-8">
        <>
            <div className="mb-6 flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-extrabold tracking-tight text-ink">Automações</h1>
                <p className="text-sm text-ink2">
                  {projects.length} automações · organize em pastas e acompanhe a saúde de cada uma
                </p>
              </div>
              <div className="flex gap-2">
                {isAdmin &&
                  (selectMode ? (
                    <>
                      <button
                        onClick={bulkDelete}
                        disabled={selected.size === 0}
                        className="rounded-xl px-4 py-2 text-sm font-semibold text-white transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50"
                        style={{ background: "var(--err)" }}
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

            {loading ? (
              <div className="flex justify-center py-20">
                <Spinner className="h-8 w-8 text-ink3" />
              </div>
            ) : (
              <>
                <Section
                  title="⭐ Favoritos"
                  count={favorited.length}
                  projects={favorited}
                  onDelete={deleteProject}
                  onMoveMenu={moveProjectViaMenu}
                  selectMode={selectMode}
                  selected={selected}
                  onToggleSelect={toggleSelect}
                  favorites={favorites}
                  onToggleFavorite={toggleFavorite}
                  pinned
                  emptyHint="Nenhum favorito ainda — clique na ⭐ de uma automação para fixá-la aqui"
                />
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
                    favorites={favorites}
                    onToggleFavorite={toggleFavorite}
                  />
                ))}
                <Section
                  title="Sem pasta"
                  count={ungroupedLive.length}
                  projects={ungroupedLive}
                  onDelete={deleteProject}
                  onMoveMenu={moveProjectViaMenu}
                  onDropProject={(id) => moveProject(id, null)}
                  selectMode={selectMode}
                  selected={selected}
                  onToggleSelect={toggleSelect}
                  favorites={favorites}
                  onToggleFavorite={toggleFavorite}
                />
                <Section
                  title="📝 Rascunhos"
                  count={drafts.length}
                  projects={drafts}
                  onDelete={deleteProject}
                  onMoveMenu={moveProjectViaMenu}
                  selectMode={selectMode}
                  selected={selected}
                  onToggleSelect={toggleSelect}
                  favorites={favorites}
                  onToggleFavorite={toggleFavorite}
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
  favorites,
  onToggleFavorite,
  pinned,
  emptyHint,
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
  favorites: Set<number>;
  onToggleFavorite: (id: number) => void;
  pinned?: boolean;
  emptyHint?: string;
}) {
  const [menu, setMenu] = useState(false);
  const [over, setOver] = useState(false);
  // hide only the virtual "Sem pasta" group when empty; keep real (empty) folders and pinned sections (favoritos)
  if (projects.length === 0 && !folderId && !pinned) return null;
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
      <h2 className="mb-3 flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-ink3">
        {folderId && <span className="text-base">📁</span>}
        {title}
        <span
          className="rounded-full px-2 text-xs text-neutral2"
          style={{ background: "var(--neutral-soft)" }}
        >
          {count}
        </span>
        {folderId && (
          <span className="relative">
            <button
              onClick={() => setMenu((m) => !m)}
              className="rounded px-1 text-ink3 transition hover:bg-surface-2 hover:text-ink2"
            >
              ⋮
            </button>
            {menu && (
              <div
                className="absolute left-0 top-6 z-20 w-36 rounded-xl border border-line bg-surface py-1 text-left normal-case shadow-token-lg"
                onClick={() => setMenu(false)}
              >
                <button
                  onClick={onRenameFolder}
                  className="block w-full px-3 py-1.5 text-left text-sm text-ink2 hover:bg-surface-2"
                >
                  Renomear pasta
                </button>
                <button
                  onClick={onDeleteFolder}
                  className="block w-full px-3 py-1.5 text-left text-sm text-err"
                  style={{ background: "transparent" }}
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
          className={`rounded-2xl border border-dashed p-6 text-center text-sm transition ${
            over ? "border-accentv text-accentv" : "border-line text-ink3"
          }`}
          style={over ? { background: "var(--accent-soft)" } : undefined}
        >
          {over ? "Solte aqui para mover" : emptyHint ?? "Pasta vazia — arraste projetos para cá"}
        </div>
      ) : (
        <div
          className={`grid grid-cols-1 gap-4 rounded-2xl sm:grid-cols-2 lg:grid-cols-3 ${
            over ? "ring-2 ring-offset-4" : ""
          }`}
          style={over ? { boxShadow: "0 0 0 2px var(--accent-glow)" } : undefined}
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
              isFavorite={favorites.has(p.id)}
              onToggleFavorite={onToggleFavorite}
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
  isFavorite,
  onToggleFavorite,
}: {
  project: Project;
  onDelete: (id: number) => void;
  onMove: (p: Project) => void;
  selectMode: boolean;
  selected: boolean;
  onToggleSelect: (id: number) => void;
  isFavorite: boolean;
  onToggleFavorite: (id: number) => void;
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
      className={`card group relative flex cursor-pointer flex-col p-5 pl-6 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-token active:cursor-grabbing ${
        selectMode && selected ? "ring-2" : ""
      }`}
      style={
        selectMode && selected
          ? { borderColor: "var(--accent)", boxShadow: "0 0 0 2px var(--accent-glow)" }
          : undefined
      }
    >
      {/* trilho lateral indica o status (no ar / rascunho) */}
      <span
        className="pointer-events-none absolute bottom-4 left-0 top-4 w-1 rounded-r-full transition-all duration-200 group-hover:bottom-3 group-hover:top-3"
        style={{ background: live ? "var(--accent)" : "var(--border-strong)" }}
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
          <h3 className="line-clamp-2 font-semibold leading-snug text-ink">
            {project.name}
          </h3>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onToggleFavorite(project.id);
            }}
            title={isFavorite ? "Remover dos favoritos" : "Favoritar"}
            aria-label={isFavorite ? "Remover dos favoritos" : "Favoritar"}
            aria-pressed={isFavorite}
            className={`rounded-md px-1 text-base leading-none transition hover:bg-surface-2 ${
              isFavorite ? "text-amber-400" : "text-ink3 hover:text-ink2"
            }`}
          >
            {isFavorite ? "★" : "☆"}
          </button>
          <span className="badge font-mono">#{project.id}</span>
          <StatusBadge status={project.status} />
          {!selectMode && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setMenu((m) => !m);
              }}
              className="rounded-md px-1 text-lg leading-none text-ink3 transition hover:bg-surface-2 hover:text-ink2"
            >
              ⋮
            </button>
          )}
        </div>
      </div>

      {menu && (
        <div
          className="absolute right-3 top-12 z-20 w-44 overflow-hidden rounded-xl border border-line bg-surface py-1 shadow-token-lg"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            onClick={() => {
              setMenu(false);
              onMove(project);
            }}
            className="block w-full px-3 py-2 text-left text-sm text-ink2 transition hover:bg-surface-2"
          >
            Mover para pasta
          </button>
          <button
            onClick={() => {
              setMenu(false);
              onDelete(project.id);
            }}
            className="block w-full px-3 py-2 text-left text-sm text-err transition"
          >
            Excluir projeto
          </button>
        </div>
      )}

      <p className="mt-1.5 line-clamp-2 text-sm leading-relaxed text-ink2">
        {project.description || "Sem descrição"}
      </p>

      <div className="mt-4 flex items-center gap-2">
        <a
          href={`/app/${project.subdomain}`}
          target="_blank"
          rel="noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="inline-flex min-w-0 items-center gap-1.5 rounded-md bg-surface-2 px-2 py-1 font-mono text-[11px] text-brandv ring-1 ring-inset ring-[color:var(--border)] transition hover:brightness-105"
          title={`Abrir app publicado: /app/${project.subdomain}`}
        >
          <svg viewBox="0 0 24 24" fill="none" className="h-3 w-3 shrink-0 opacity-70" aria-hidden>
            <path d="M7 17 17 7M9 7h8v8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span className="truncate">/app/{project.subdomain}</span>
        </a>
        {live && (
          <a
            href={`/app/${project.subdomain}`}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="btn-primary ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 text-xs"
            title="Abrir automação publicada"
          >
            Usar
            <svg viewBox="0 0 24 24" fill="none" className="h-3 w-3" aria-hidden>
              <path d="M7 17 17 7M9 7h8v8" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </a>
        )}
      </div>

      <div className="mt-3 flex flex-col gap-1.5 text-[11px] text-ink3">
        {project.owner_name && (
          <div className="flex items-center gap-1.5">
            <svg viewBox="0 0 24 24" fill="none" className="h-3 w-3 shrink-0" aria-hidden>
              <circle cx="12" cy="8" r="3.2" stroke="currentColor" strokeWidth="1.9" />
              <path d="M5 20c0-3.3 3.1-5.5 7-5.5s7 2.2 7 5.5" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
            </svg>
            Criado por <span className="font-semibold text-ink2">{project.owner_name}</span>
          </div>
        )}
        <div className="flex items-center gap-1.5">
          <svg viewBox="0 0 24 24" fill="none" className="h-3 w-3 shrink-0" aria-hidden>
            <rect x="3" y="4.5" width="18" height="16" rx="2.5" stroke="currentColor" strokeWidth="1.9" />
            <path d="M3 9h18M8 2.5v4M16 2.5v4" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
          </svg>
          Criado em {fmtData(project.created_at)} · atualizado {fmtData(project.updated_at)}
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-line pt-3 text-xs text-ink3">
        <span>{project.execution_count ?? 0} execuções</span>
        <span className="flex gap-1">
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
      className="rounded-md px-2 py-1 font-medium text-ink3 transition hover:text-accentv"
    >
      {children}
    </Link>
  );
}
