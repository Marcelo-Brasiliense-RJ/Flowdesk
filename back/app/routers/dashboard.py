"""Dashboard: KPIs and operational overview across the org's automations."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Execution, Project, User

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    projects = db.query(Project).filter(Project.org_id == user.org_id).all()
    pids = [p.id for p in projects]
    names = {p.id: p.name for p in projects}

    def execq():
        q = db.query(Execution)
        return q.filter(Execution.project_id.in_(pids)) if pids else q.filter(False)

    total = execq().count()
    by_status = dict(
        execq().with_entities(Execution.status, func.count())
        .group_by(Execution.status).all()
    )
    success = by_status.get("success", 0)
    error = by_status.get("error", 0)
    running = by_status.get("running", 0) + by_status.get("queued", 0)
    finished = success + error
    success_rate = round(success / finished * 100, 1) if finished else 0.0

    # avg duration (seconds) of finished executions
    durs = (
        execq().filter(Execution.finished_at.isnot(None))
        .with_entities(Execution.started_at, Execution.finished_at).all()
    )
    avg_seconds = round(
        sum((f - s).total_seconds() for s, f in durs) / len(durs), 1
    ) if durs else 0.0

    # 7-day timeline (zero-filled on the frontend)
    rows = (
        execq().with_entities(
            func.date(Execution.started_at).label("d"),
            Execution.status,
            func.count(),
        ).group_by("d", Execution.status).all()
    )
    timeline: dict[str, dict] = {}
    for d, status, n in rows:
        day = timeline.setdefault(str(d), {"date": str(d), "success": 0, "error": 0, "total": 0})
        day["total"] += n
        if status == "success":
            day["success"] += n
        elif status == "error":
            day["error"] += n

    # per-project health
    by_project = []
    for p in projects:
        pq = db.query(Execution).filter(Execution.project_id == p.id)
        pe = pq.count()
        perr = pq.filter(Execution.status == "error").count()
        last = pq.order_by(Execution.started_at.desc()).first()
        by_project.append({
            "id": p.id,
            "name": p.name,
            "status": p.status,
            "subdomain": p.subdomain,
            "executions": pe,
            "errors": perr,
            "last_run": last.started_at.isoformat() if last else None,
        })
    by_project.sort(key=lambda x: x["executions"], reverse=True)

    recent_errors = [
        {
            "id": e.id,
            "project_id": e.project_id,
            "project_name": names.get(e.project_id, ""),
            "stage_name": e.stage_name,
            "started_at": e.started_at.isoformat(),
            "stderr": (e.stderr or "")[-300:],
        }
        for e in execq().filter(Execution.status == "error")
        .order_by(Execution.started_at.desc()).limit(8).all()
    ]
    recent = [
        {
            "id": e.id,
            "project_id": e.project_id,
            "project_name": names.get(e.project_id, ""),
            "stage_name": e.stage_name,
            "stage_type": e.stage_type,
            "status": e.status,
            "started_at": e.started_at.isoformat(),
        }
        for e in execq().order_by(Execution.started_at.desc()).limit(10).all()
    ]

    return {
        "kpis": {
            "projects": len(projects),
            "live": sum(1 for p in projects if p.status == "live"),
            "draft": sum(1 for p in projects if p.status == "draft"),
            "executions": total,
            "success": success,
            "error": error,
            "running": running,
            "success_rate": success_rate,
            "avg_seconds": avg_seconds,
        },
        "timeline": sorted(timeline.values(), key=lambda x: x["date"]),
        "by_project": by_project,
        "recent_errors": recent_errors,
        "recent_executions": recent,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
