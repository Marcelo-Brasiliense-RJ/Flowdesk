"""Tela de gerenciamento/manutenção das aplicações (Admin + Dev).

Lista todas as aplicações da organização com indicadores de saúde (status,
última execução, erros) e permite alternar o status (no ar / rascunho).
Exclusão reaproveita as rotas existentes em /api/projects.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..auth import require_manager
from ..database import get_db
from ..models import Execution, Project, ProjectFolder, User

router = APIRouter(prefix="/api/manage", tags=["manage"])


class StatusUpdate(BaseModel):
    status: str  # "live" | "draft"


@router.get("/apps")
def list_apps(db: Session = Depends(get_db), user: User = Depends(require_manager)):
    projects = db.query(Project).filter(Project.org_id == user.org_id).all()
    folders = {
        f.id: f.name
        for f in db.query(ProjectFolder).filter(ProjectFolder.org_id == user.org_id)
    }
    out = []
    for p in projects:
        last = (
            db.query(Execution)
            .filter(Execution.project_id == p.id)
            .order_by(desc(Execution.started_at))
            .first()
        )
        errors = (
            db.query(Execution)
            .filter(Execution.project_id == p.id, Execution.status == "error")
            .count()
        )
        total = db.query(Execution).filter(Execution.project_id == p.id).count()
        out.append(
            {
                "id": p.id,
                "name": p.name,
                "subdomain": p.subdomain,
                "status": p.status,
                "folder": folders.get(p.folder_id),
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                "last_execution": (
                    {
                        "status": last.status,
                        "stage": last.stage_name,
                        "finished_at": last.finished_at.isoformat() if last.finished_at else None,
                    }
                    if last
                    else None
                ),
                "errors": errors,
                "executions": total,
            }
        )
    out.sort(key=lambda a: a["updated_at"] or "", reverse=True)
    return out


@router.post("/apps/{project_id}/status")
def set_status(
    project_id: int,
    body: StatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    if body.status not in ("live", "draft"):
        raise HTTPException(status_code=400, detail="Status inválido")
    p = db.get(Project, project_id)
    if p is None or p.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Aplicação não encontrada")
    p.status = body.status
    db.commit()
    return {"ok": True, "status": p.status}
