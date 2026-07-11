"""Projects, folders, stages, edges and source files."""
from __future__ import annotations

import re
import unicodedata
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_admin
from ..config import settings
from ..services import ai_call, ai_config
from ..services.ai_guard import SECURITY_PREAMBLE
from ..database import get_db
from ..models import (
    ApiKey,
    Build,
    ChatMessage,
    Connector,
    DataRow,
    DataTable,
    Edge,
    EnvVar,
    Execution,
    PendingAction,
    Project,
    ProjectFolder,
    ProjectMember,
    Role,
    SourceFile,
    Stage,
    User,
)
from ..schemas import (
    AutoNameIn,
    BulkDeleteRequest,
    EdgeCreate,
    EdgeOut,
    FolderCreate,
    FolderOut,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    SourceFileOut,
    SourceFileWrite,
    StageCreate,
    StageOut,
    StageUpdate,
    WizardStateUpdate,
)
from ..services import storage

router = APIRouter(prefix="/api", tags=["projects"])


_SLUG_STOPWORDS = {"o", "a", "os", "as", "de", "do", "da", "dos", "das", "e", "com", "para", "em", "um", "uma"}


def slugify(value: str, max_words: int = 5) -> str:
    """Slug ASCII para URL/chave. Translitera acentos (á->a, ção->cao, NUNCA apaga
    a letra), remove palavras vazias e limita a max_words para a URL não virar uma
    frase inteira. max_words=0 desliga o corte (usado em chaves de nó)."""
    ascii_only = (
        unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    )
    words = [w for w in re.sub(r"[^a-z0-9]+", " ", ascii_only.lower()).split() if w]
    if max_words:
        kept = [w for w in words if w not in _SLUG_STOPWORDS][:max_words]
        words = kept or words[:max_words]  # tudo stopword? mantém as primeiras
    return "-".join(words) or "projeto"


def unique_subdomain(db: Session, name: str, exclude_id: int | None = None) -> str:
    """Subdomínio único a partir do nome, com sufixo curto só em caso de colisão."""
    base = slugify(name)
    sub = base
    while True:
        q = db.query(Project).filter(Project.subdomain == sub)
        if exclude_id is not None:
            q = q.filter(Project.id != exclude_id)
        if not q.first():
            return sub
        sub = f"{base}-{uuid.uuid4().hex[:4]}"


def unsafe_source_path(path: str) -> bool:
    """Reject traversal / absolute paths for project source files."""
    p = (path or "").strip()
    if not p:
        return True
    normalized = p.replace("\\", "/")
    if normalized.startswith("/") or ".." in normalized.split("/"):
        return True
    import os

    if os.path.isabs(p) or (len(p) > 1 and p[1] == ":"):  # absolute / Windows drive
        return True
    return False


def get_project(db: Session, project_id: int, user: User) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    return project


def _mark_wizard_dirty(project: Project) -> None:
    """Edição manual (modo avançado) pode defasar o rascunho do assistente.
    Só marca se o fluxo já tiver sido montado pelo wizard (`_built`)."""
    if (project.wizard_state or {}).get("_built"):
        project.wizard_dirty = True


# ---- folders ----
@router.get("/folders", response_model=list[FolderOut])
def list_folders(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(ProjectFolder).filter(ProjectFolder.org_id == user.org_id).all()


@router.post("/folders", response_model=FolderOut)
def create_folder(
    body: FolderCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    nome = body.name.strip()
    clash = (
        db.query(ProjectFolder)
        .filter(ProjectFolder.org_id == user.org_id, func.lower(ProjectFolder.name) == nome.lower())
        .first()
    )
    if clash:
        raise HTTPException(status_code=400, detail=f'Já existe uma pasta chamada "{clash.name}"')
    folder = ProjectFolder(org_id=user.org_id, name=nome)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


def _get_folder(db: Session, folder_id: int, user: User) -> ProjectFolder:
    folder = db.get(ProjectFolder, folder_id)
    if folder is None or folder.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Pasta não encontrada")
    return folder


@router.patch("/folders/{folder_id}", response_model=FolderOut)
def rename_folder(
    folder_id: int,
    body: FolderCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    folder = _get_folder(db, folder_id, user)
    nome = body.name.strip()
    clash = (
        db.query(ProjectFolder)
        .filter(
            ProjectFolder.org_id == user.org_id,
            func.lower(ProjectFolder.name) == nome.lower(),
            ProjectFolder.id != folder_id,
        )
        .first()
    )
    if clash:
        raise HTTPException(status_code=400, detail=f'Já existe uma pasta chamada "{clash.name}"')
    folder.name = nome
    db.commit()
    db.refresh(folder)
    return folder


@router.delete("/folders/{folder_id}")
def delete_folder(
    folder_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    folder = _get_folder(db, folder_id, user)
    # move projects out of the folder instead of deleting them
    db.query(Project).filter(Project.folder_id == folder_id).update(
        {Project.folder_id: None}, synchronize_session=False
    )
    db.delete(folder)
    db.commit()
    return {"ok": True}


# ---- projects ----
@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    projects = (
        db.query(Project)
        .filter(Project.org_id == user.org_id)
        .order_by(Project.updated_at.desc())
        .all()
    )
    if not projects:
        return []
    ids = [p.id for p in projects]
    counts = dict(
        db.query(Execution.project_id, func.count(Execution.id))
        .filter(Execution.project_id.in_(ids))
        .group_by(Execution.project_id)
        .all()
    )
    owner_ids = {p.created_by_id for p in projects if p.created_by_id}
    owners = (
        dict(db.query(User.id, User.name).filter(User.id.in_(owner_ids)).all())
        if owner_ids
        else {}
    )
    for p in projects:
        # atributos não mapeados, lidos pelo ProjectOut (from_attributes)
        p.execution_count = counts.get(p.id, 0)
        p.owner_name = owners.get(p.created_by_id)
    return projects


@router.post("/projects", response_model=ProjectOut)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    subdomain = unique_subdomain(db, body.name)
    project = Project(
        org_id=user.org_id,
        created_by_id=user.id,
        folder_id=body.folder_id,
        name=body.name,
        description=body.description,
        subdomain=subdomain,
        status="draft",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    storage.ensure_project_dirs(project)
    # seed default source files (requirements + readme stub)
    db.add_all(
        [
            SourceFile(
                project_id=project.id,
                path="requirements.txt",
                content="# pacotes Python do projeto\n",
            ),
            SourceFile(
                project_id=project.id,
                path="README.md",
                content=f"# {project.name}\n\n{project.description}\n",
            ),
        ]
    )
    db.commit()
    return project


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project_detail(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return get_project(db, project_id, user)


@router.put("/projects/{project_id}/wizard", response_model=ProjectOut)
def save_wizard_state(
    project_id: int,
    body: WizardStateUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Salva o rascunho do assistente (wizard) de criação.

    Salvar pelo wizard torna o rascunho a referência da intenção do usuário, então
    limpa a marca de defasagem (wizard_dirty=False por padrão). Stages/código
    continuam canônicos.
    """
    project = get_project(db, project_id, user)
    project.wizard_state = body.state
    project.wizard_dirty = body.dirty
    db.commit()
    db.refresh(project)
    return project


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    body: ProjectUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project(db, project_id, user)
    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    if body.subdomain is not None:
        # subdomínio digitado à mão: respeita as palavras do usuário (só translitera
        # e hifeniza), sem remover stopword nem cortar como na derivação do nome.
        sub = slugify(body.subdomain, max_words=0)
        clash = (
            db.query(Project)
            .filter(Project.subdomain == sub, Project.id != project_id)
            .first()
        )
        if clash:
            raise HTTPException(status_code=400, detail="Subdomínio já em uso")
        project.subdomain = sub
    if body.clear_folder:
        project.folder_id = None
    elif body.folder_id is not None:
        folder = db.get(ProjectFolder, body.folder_id)
        if folder is None or folder.org_id != user.org_id:
            raise HTTPException(status_code=400, detail="Pasta inválida")
        project.folder_id = body.folder_id
    db.commit()
    db.refresh(project)
    return project


def _purge_project(db: Session, project: Project) -> None:
    """Remove a project and all dependent rows + on-disk storage (no commit)."""
    project_id = project.id
    # remove child rows that have no ORM cascade configured
    table_ids = [
        t.id for t in db.query(DataTable).filter(DataTable.project_id == project_id)
    ]
    if table_ids:
        db.query(DataRow).filter(DataRow.table_id.in_(table_ids)).delete(
            synchronize_session=False
        )
    # ordem importa no Postgres (FKs enforced): Execution referencia builds.id e
    # stages.id, então apaga Execution antes de Build. Stages caem depois via cascade.
    for model in (
        Execution, Build, Role, ProjectMember, EnvVar, ApiKey, Connector,
        DataTable, ChatMessage, PendingAction,
    ):
        db.query(model).filter(model.project_id == project_id).delete(
            synchronize_session=False
        )
    db.delete(project)  # stages/edges/source_files cascade via relationship
    # best-effort removal of the project's on-disk storage
    import shutil

    root = storage.STORAGE_DIR / str(project_id)
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)


@router.delete("/projects/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project(db, project_id, user)
    _purge_project(db, project)
    db.commit()
    return {"ok": True}


@router.post("/projects/bulk-delete")
def bulk_delete_projects(
    body: BulkDeleteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Exclusão em massa, restrita a administradores."""
    deleted = 0
    for project_id in set(body.ids):
        project = db.get(Project, project_id)
        if project is None or project.org_id != user.org_id:
            continue
        _purge_project(db, project)
        deleted += 1
    db.commit()
    return {"ok": True, "deleted": deleted}


@router.post("/projects/{project_id}/auto-name")
def auto_name(
    project_id: int,
    body: AutoNameIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Gera um título curto e claro para a aplicação a partir do pedido do usuário.
    Sem IA (ou em caso de falha), mantém o nome atual."""
    project = get_project(db, project_id, user)
    prompt = body.prompt.strip()
    if not prompt or not settings.ai_enabled:
        return {"name": project.name}
    instr = (
        "Gere um TÍTULO curto (2 a 5 palavras), claro e em português, para uma automação "
        "descrita pelo usuário. Estilo título, sem aspas e sem ponto final "
        "(ex.: 'Totais de vendas por produto', 'Conciliação de planilhas'). "
        "Responda apenas com o título."
    )
    try:
        raw = ai_call.complete(
            ai_config.get_model(),
            [
                {"role": "system", "content": SECURITY_PREAMBLE},
                {"role": "system", "content": instr},
                {"role": "user", "content": prompt[:1000]},
            ],
            temperature=0.3,
            max_tokens=20,
        )
        name = (raw or "").strip().strip('"').strip()[:60]
        if name:
            project.name = name
            db.commit()
            return {"name": name}
    except Exception:
        pass
    return {"name": project.name}


# ---- stages ----
@router.get("/projects/{project_id}/stages", response_model=list[StageOut])
def list_stages(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project(db, project_id, user)
    stages = db.query(Stage).filter(Stage.project_id == project_id).all()
    # auto-heal: um Form de entrada montado antes pode ter menos campos de arquivo do
    # que o script usa (get_file(0), get_file(1), ...). Reconcilia na leitura, para
    # projetos ainda nao publicados, sem exigir que a pessoa reedite o script.
    if project.status != "live":
        from .chat import _sync_input_file_fields

        script = next((s for s in stages if s.type == "script" and s.entry_file), None)
        if script and _sync_input_file_fields(db, project_id, script.entry_file):
            db.commit()
            stages = db.query(Stage).filter(Stage.project_id == project_id).all()
    return stages


@router.post("/projects/{project_id}/stages", response_model=StageOut)
def create_stage(
    project_id: int,
    body: StageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project(db, project_id, user)
    if body.type not in ("form", "script", "job", "hook", "agent"):
        raise HTTPException(status_code=400, detail="Tipo de nó inválido")
    key = body.key or slugify(body.name)
    base_key = key
    n = 1
    while db.query(Stage).filter(Stage.project_id == project_id, Stage.key == key).first():
        n += 1
        key = f"{base_key}-{n}"
    entry_file = f"{key}.py" if body.type in ("script", "job", "agent") else ""
    config = dict(body.config or {})
    if body.type == "hook" and not config.get("webhook_id"):
        config["webhook_id"] = uuid.uuid4().hex
        config.setdefault("method", "POST")
    stage = Stage(
        project_id=project_id,
        type=body.type,
        name=body.name,
        key=key,
        config=config,
        entry_file=entry_file,
        timeout_seconds=body.timeout_seconds,
        pos_x=body.pos_x,
        pos_y=body.pos_y,
    )
    db.add(stage)
    _mark_wizard_dirty(project)
    db.commit()
    db.refresh(stage)
    # scaffold a source file for executable stages (skip if one already exists)
    if entry_file:
        exists = (
            db.query(SourceFile)
            .filter(SourceFile.project_id == project_id, SourceFile.path == entry_file)
            .first()
        )
        if not exists:
            db.add(
                SourceFile(
                    project_id=project_id,
                    path=entry_file,
                    content=_SCRIPT_TEMPLATE.format(name=stage.name),
                )
            )
            db.commit()
    return stage


@router.patch("/projects/{project_id}/stages/{stage_id}", response_model=StageOut)
def update_stage(
    project_id: int,
    stage_id: int,
    body: StageUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project(db, project_id, user)
    stage = db.get(Stage, stage_id)
    if stage is None or stage.project_id != project_id:
        raise HTTPException(status_code=404, detail="Nó não encontrado")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(stage, field, value)
    _mark_wizard_dirty(project)
    db.commit()
    db.refresh(stage)
    return stage


@router.delete("/projects/{project_id}/stages/{stage_id}")
def delete_stage(
    project_id: int,
    stage_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project(db, project_id, user)
    stage = db.get(Stage, stage_id)
    if stage is None or stage.project_id != project_id:
        raise HTTPException(status_code=404, detail="Nó não encontrado")
    _mark_wizard_dirty(project)
    db.query(Edge).filter(
        (Edge.source_stage_id == stage_id) | (Edge.target_stage_id == stage_id)
    ).delete(synchronize_session=False)
    db.delete(stage)
    db.commit()
    return {"ok": True}


# ---- edges ----
@router.get("/projects/{project_id}/edges", response_model=list[EdgeOut])
def list_edges(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project(db, project_id, user)
    return db.query(Edge).filter(Edge.project_id == project_id).all()


@router.post("/projects/{project_id}/edges", response_model=EdgeOut)
def create_edge(
    project_id: int,
    body: EdgeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project(db, project_id, user)
    _mark_wizard_dirty(project)
    edge = Edge(
        project_id=project_id,
        source_stage_id=body.source_stage_id,
        target_stage_id=body.target_stage_id,
        variable_label=body.variable_label,
    )
    db.add(edge)
    db.commit()
    db.refresh(edge)
    return edge


@router.delete("/projects/{project_id}/edges/{edge_id}")
def delete_edge(
    project_id: int,
    edge_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project(db, project_id, user)
    edge = db.get(Edge, edge_id)
    if edge and edge.project_id == project_id:
        _mark_wizard_dirty(project)
        db.delete(edge)
        db.commit()
    return {"ok": True}


# ---- source files (Monaco explorer) ----
@router.get("/projects/{project_id}/files", response_model=list[SourceFileOut])
def list_source_files(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project(db, project_id, user)
    return (
        db.query(SourceFile)
        .filter(SourceFile.project_id == project_id)
        .order_by(SourceFile.path)
        .all()
    )


@router.put("/projects/{project_id}/files", response_model=SourceFileOut)
def write_source_file(
    project_id: int,
    body: SourceFileWrite,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project(db, project_id, user)
    if unsafe_source_path(body.path):
        raise HTTPException(status_code=400, detail="Caminho de arquivo inválido")
    _mark_wizard_dirty(project)
    existing = (
        db.query(SourceFile)
        .filter(SourceFile.project_id == project_id, SourceFile.path == body.path)
        .first()
    )
    if existing:
        existing.content = body.content
        db.commit()
        db.refresh(existing)
        return existing
    sf = SourceFile(
        project_id=project_id,
        path=body.path,
        content=body.content,
        is_dir=body.is_dir,
    )
    db.add(sf)
    db.commit()
    db.refresh(sf)
    return sf


@router.delete("/projects/{project_id}/files")
def delete_source_file(
    project_id: int,
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project(db, project_id, user)
    _mark_wizard_dirty(project)
    db.query(SourceFile).filter(
        SourceFile.project_id == project_id, SourceFile.path == path
    ).delete()
    db.commit()
    return {"ok": True}


_SCRIPT_TEMPLATE = '''"""{name}"""
from flowdesk_sdk import get_input, set_output, output_path, log


def main():
    data = get_input()
    log("Recebido:", data)
    # TODO: implementar a lógica do script
    set_output({{"ok": True}})


if __name__ == "__main__":
    main()
'''
