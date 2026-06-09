"""Webhook (Hook) nodes — n8n-style HTTP trigger for workflows.

Each Hook stage owns a unique webhook_id. A public POST to
/api/hooks/{webhook_id} triggers the downstream stage (e.g. a Script),
passing the request JSON body as the execution input.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Edge, Execution, Project, Stage, User
from ..runtime.runner import runtime
from .projects import get_project

router = APIRouter(prefix="/api", tags=["hooks"])


@router.post("/projects/{project_id}/stages/{stage_id}/webhook")
def ensure_webhook(
    project_id: int,
    stage_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Ensure a Hook stage has a webhook id and return its public info."""
    get_project(db, project_id, user)
    stage = db.get(Stage, stage_id)
    if stage is None or stage.project_id != project_id or stage.type != "hook":
        raise HTTPException(status_code=404, detail="Hook não encontrado")
    cfg = dict(stage.config or {})
    if not cfg.get("webhook_id"):
        cfg["webhook_id"] = uuid.uuid4().hex
        cfg.setdefault("method", "POST")
        stage.config = cfg
        db.commit()

    edge = (
        db.query(Edge)
        .filter(Edge.project_id == project_id, Edge.source_stage_id == stage_id)
        .first()
    )
    target = db.get(Stage, edge.target_stage_id) if edge else None
    return {
        "webhook_id": cfg["webhook_id"],
        "method": cfg.get("method", "POST"),
        "path": f"/api/hooks/{cfg['webhook_id']}",
        "target": {"id": target.id, "name": target.name, "type": target.type} if target else None,
    }


@router.post("/hooks/{webhook_id}")
async def trigger_webhook(
    webhook_id: str, request: Request, db: Session = Depends(get_db)
):
    """Public webhook endpoint. Triggers the downstream stage with the body."""
    stage = next(
        (
            s
            for s in db.query(Stage).filter(Stage.type == "hook").all()
            if (s.config or {}).get("webhook_id") == webhook_id
        ),
        None,
    )
    if stage is None:
        raise HTTPException(status_code=404, detail="Webhook não encontrado")

    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {"data": body}

    project = db.get(Project, stage.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    edge = (
        db.query(Edge)
        .filter(Edge.project_id == stage.project_id, Edge.source_stage_id == stage.id)
        .first()
    )
    if edge is None:
        return {"status": "received", "message": "Webhook recebido (sem etapa conectada).", "payload": body}

    target = db.get(Stage, edge.target_stage_id)
    if target and target.type in ("script", "job", "agent"):
        execu = Execution(
            id=str(uuid.uuid4()),
            project_id=project.id,
            stage_id=target.id,
            stage_name=target.name,
            stage_type=target.type,
            status="queued",
            input_data=body,
        )
        db.add(execu)
        db.commit()
        runtime.submit(execu.id)
        return {"status": "triggered", "execution_id": execu.id, "stage": target.name}

    return {"status": "received", "next_stage": target.name if target else None, "payload": body}
