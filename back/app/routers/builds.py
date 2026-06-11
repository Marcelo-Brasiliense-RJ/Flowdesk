"""Version history (builds). 'Salvar e Publicar' creates an immutable build."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Build, Edge, Project, SourceFile, Stage, User
from ..schemas import BuildOut
from .projects import get_project

router = APIRouter(prefix="/api", tags=["builds"])


@router.get("/projects/{project_id}/builds", response_model=list[BuildOut])
def list_builds(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project(db, project_id, user)
    return (
        db.query(Build)
        .filter(Build.project_id == project_id)
        .order_by(Build.created_at.desc())
        .all()
    )


@router.post("/projects/{project_id}/publish", response_model=BuildOut)
def publish(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project(db, project_id, user)
    stages = db.query(Stage).filter(Stage.project_id == project_id).all()
    edges = db.query(Edge).filter(Edge.project_id == project_id).all()
    files = db.query(SourceFile).filter(SourceFile.project_id == project_id).all()

    snapshot = {
        "stages": [
            {"key": s.key, "type": s.type, "name": s.name, "config": s.config}
            for s in stages
        ],
        "edges": [
            {"source": e.source_stage_id, "target": e.target_stage_id,
             "label": e.variable_label}
            for e in edges
        ],
        "files": {f.path: f.content for f in files},
    }

    # only one build may be "live" at a time
    db.query(Build).filter(
        Build.project_id == project_id, Build.status == "live"
    ).update({Build.status: "inactive"}, synchronize_session=False)

    build = Build(
        project_id=project_id,
        hash=uuid.uuid4().hex[:8],
        framework_version="1.0.0",
        status="live",
        snapshot=snapshot,
    )
    db.add(build)
    project.status = "live"
    db.commit()
    db.refresh(build)
    return build


@router.post("/projects/{project_id}/builds/{build_id}/restore")
def restore_build(
    project_id: int,
    build_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Restaura os arquivos de código do projeto para o estado desta versão.

    Os nós/conexões atuais são mantidos (restauração de código). O rascunho é
    sobrescrito pelos arquivos do snapshot; arquivos criados depois são removidos.
    """
    get_project(db, project_id, user)
    build = db.get(Build, build_id)
    if build is None or build.project_id != project_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Versão não encontrada")
    files: dict = (build.snapshot or {}).get("files") or {}
    if not files:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="Esta versão não tem arquivos para restaurar")

    atuais = db.query(SourceFile).filter(SourceFile.project_id == project_id).all()
    por_path = {f.path: f for f in atuais}
    restaurados, removidos = 0, 0
    for path, content in files.items():
        row = por_path.get(path)
        if row:
            row.content = content
        else:
            db.add(SourceFile(project_id=project_id, path=path, content=content))
        restaurados += 1
    for f in atuais:
        if f.path not in files and not f.is_dir:
            db.delete(f)
            removidos += 1
    db.commit()
    return {"ok": True, "restaurados": restaurados, "removidos": removidos, "hash": build.hash}


@router.post("/projects/{project_id}/builds/{build_id}/activate", response_model=BuildOut)
def activate_build(
    project_id: int,
    build_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project(db, project_id, user)
    build = db.get(Build, build_id)
    if build is None or build.project_id != project_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Versão não encontrada")
    db.query(Build).filter(
        Build.project_id == project_id, Build.status == "live"
    ).update({Build.status: "inactive"}, synchronize_session=False)
    build.status = "live"
    project.status = "live"
    db.commit()
    db.refresh(build)
    return build
