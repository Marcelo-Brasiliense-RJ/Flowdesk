"""Execution logs with filters + manual stage run."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Execution, Stage, User
from ..runtime.runner import runtime
from ..schemas import ExecutionOut
from ..services import storage
from .projects import get_project

router = APIRouter(prefix="/api", tags=["executions"])


@router.get("/projects/{project_id}/executions")
def list_executions(
    project_id: int,
    stage_id: Optional[int] = None,
    status: Optional[str] = None,
    build_id: Optional[int] = None,
    execution_id: Optional[str] = None,
    date_from: Optional[dt.datetime] = None,
    date_to: Optional[dt.datetime] = None,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project(db, project_id, user)
    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    q = db.query(Execution).filter(Execution.project_id == project_id)
    if stage_id:
        q = q.filter(Execution.stage_id == stage_id)
    if status:
        q = q.filter(Execution.status == status)
    if build_id:
        q = q.filter(Execution.build_id == build_id)
    if execution_id:
        q = q.filter(Execution.id.like(f"{execution_id}%"))
    if date_from:
        q = q.filter(Execution.started_at >= date_from)
    if date_to:
        q = q.filter(Execution.started_at <= date_to)
    total = q.count()
    rows = (
        q.order_by(Execution.started_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [ExecutionOut.model_validate(r).model_dump() for r in rows],
    }


@router.get("/projects/{project_id}/executions/{execution_id}")
def get_execution(
    project_id: int,
    execution_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project(db, project_id, user)
    execu = db.get(Execution, execution_id)
    if execu is None or execu.project_id != project_id:
        raise HTTPException(status_code=404, detail="Execução não encontrada")
    data = ExecutionOut.model_validate(execu).model_dump()
    data["progress"] = storage.read_progress(project_id, execution_id)
    return data


@router.get("/projects/{project_id}/executions/by-stage/recent")
def recent_by_stage(
    project_id: int,
    limit: int = Query(5, le=20),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Last N executions per stage for the workflow monitor dots."""
    get_project(db, project_id, user)
    stages = db.query(Stage).filter(Stage.project_id == project_id).all()
    result: dict[int, list] = {}
    for stage in stages:
        rows = (
            db.query(Execution)
            .filter(Execution.stage_id == stage.id)
            .order_by(Execution.started_at.desc())
            .limit(limit)
            .all()
        )
        result[stage.id] = [
            {"id": r.id, "status": r.status, "started_at": r.started_at.isoformat()}
            for r in reversed(rows)
        ]
    return {
        "stages": result,
        "pending": runtime.pending_count(),
        "avg_seconds": round(runtime.avg_duration(), 1),
    }


@router.post("/projects/{project_id}/stages/{stage_id}/run", response_model=ExecutionOut)
def run_stage(
    project_id: int,
    stage_id: int,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project(db, project_id, user)
    stage = db.get(Stage, stage_id)
    if stage is None or stage.project_id != project_id:
        raise HTTPException(status_code=404, detail="Nó não encontrado")
    if stage.type not in ("script", "job", "agent"):
        raise HTTPException(status_code=400, detail="Este nó não é executável")
    execu = Execution(
        id=str(uuid.uuid4()),
        project_id=project_id,
        stage_id=stage.id,
        stage_name=stage.name,
        stage_type=stage.type,
        status="queued",
        input_data=payload or {},
    )
    db.add(execu)
    db.commit()
    db.refresh(execu)
    runtime.submit(execu.id)
    return execu
