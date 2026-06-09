"""Disk file manager (Sistema de Arquivos): uploads, outputs, browse."""
from __future__ import annotations

import shutil
from pathlib import PurePath

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import User
from ..services import storage
from .projects import get_project

router = APIRouter(prefix="/api", tags=["files"])


@router.get("/projects/{project_id}/fs")
def browse(
    project_id: int,
    path: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project(db, project_id, user)
    root = storage.ensure_project_dirs(project)
    try:
        entries = storage.list_dir(root, path)
    except ValueError:
        raise HTTPException(status_code=400, detail="Caminho inválido")
    return {"path": path, "entries": entries}


@router.post("/projects/{project_id}/fs/upload")
def upload(
    project_id: int,
    path: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project(db, project_id, user)
    root = storage.ensure_project_dirs(project)
    try:
        target_dir = storage.safe_join(root, path) if path else root
    except ValueError:
        raise HTTPException(status_code=400, detail="Caminho inválido")
    if file.size and file.size > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Arquivo muito grande (máx. 50 MB)")
    target_dir.mkdir(parents=True, exist_ok=True)
    # never trust the multipart filename — use only its basename to prevent traversal
    safe_name = PurePath(file.filename or "arquivo").name or "arquivo"
    dest = target_dir / safe_name
    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    return {"ok": True, "name": dest.name}


@router.post("/projects/{project_id}/fs/folder")
def make_folder(
    project_id: int,
    path: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project(db, project_id, user)
    root = storage.ensure_project_dirs(project)
    try:
        target = storage.safe_join(root, path)
    except ValueError:
        raise HTTPException(status_code=400, detail="Caminho inválido")
    target.mkdir(parents=True, exist_ok=True)
    return {"ok": True}


@router.post("/projects/{project_id}/fs/rename")
def rename(
    project_id: int,
    path: str = Form(...),
    new_name: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project(db, project_id, user)
    root = storage.ensure_project_dirs(project)
    try:
        src = storage.safe_join(root, path)
        dst = src.parent / new_name
        storage.safe_join(root, str(dst.relative_to(root)))
    except ValueError:
        raise HTTPException(status_code=400, detail="Caminho inválido")
    if not src.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    src.rename(dst)
    return {"ok": True}


@router.delete("/projects/{project_id}/fs")
def remove(
    project_id: int,
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project(db, project_id, user)
    root = storage.ensure_project_dirs(project)
    try:
        storage.delete_path(root, path)
    except ValueError:
        raise HTTPException(status_code=400, detail="Caminho inválido")
    return {"ok": True}


@router.post("/projects/{project_id}/sample-spreadsheet")
def sample_spreadsheet(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate a sample base spreadsheet in uploads/ so the user can test the flow."""
    import pandas as pd

    project = get_project(db, project_id, user)
    root = storage.ensure_project_dirs(project)
    df = pd.DataFrame(
        {
            "data": [
                "2026-06-01", "2026-06-01", "2026-06-02", "2026-06-02",
                "2026-06-03", "2026-06-03", "2026-06-04", "2026-06-05",
                "2026-06-05", "2026-06-06",
            ],
            "regiao": ["Sudeste", "Sul", "Nordeste", "Sudeste", "Norte",
                       "Sul", "Sudeste", "Nordeste", "Centro-Oeste", "Sudeste"],
            "produto": ["Plano A", "Plano B", "Plano A", "Plano C", "Plano B",
                        "Plano A", "Plano C", "Plano B", "Plano A", "Plano C"],
            "vendedor": ["Ana", "Bruno", "Ana", "Carla", "Bruno",
                         "Ana", "Carla", "Bruno", "Ana", "Carla"],
            "quantidade": [3, 1, 5, 2, 4, 2, 1, 6, 3, 2],
            "valor_total": [2970.0, 1490.0, 4950.0, 5980.0, 5960.0,
                            1980.0, 2990.0, 8940.0, 2970.0, 5980.0],
        }
    )
    dest = root / "uploads" / "exemplo_base.xlsx"
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(dest, index=False)
    return {"path": "uploads/exemplo_base.xlsx", "name": "exemplo_base.xlsx"}


@router.get("/projects/{project_id}/fs/download")
def download(
    project_id: int,
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project(db, project_id, user)
    root = storage.ensure_project_dirs(project)
    try:
        target = storage.safe_join(root, path)
    except ValueError:
        raise HTTPException(status_code=400, detail="Caminho inválido")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    return FileResponse(str(target), filename=target.name)
