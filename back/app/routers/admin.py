"""Painel de controle do admin: panorama completo da plataforma.

O frontend combina este endpoint com /api/dashboard. O dashboard já cobre KPIs
de execução, timeline e saúde por projeto; aqui entregamos o que ele não cobre:
usuários, pedidos do chat (o que foi pesquisado/solicitado à IA), consumo de
máquina e requisições. Métricas de máquina/requisições vêm de app.metrics (em
memória, zeradas a cada reinício do backend).
"""
from __future__ import annotations

import datetime as dt
import os

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import metrics
from ..auth import require_admin
from ..database import get_db
from ..models import ChatMessage, Project, User

try:
    import psutil
except ImportError:  # degradação graciosa se a lib não estiver instalada
    psutil = None

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/overview")
def overview(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    projects = db.query(Project).filter(Project.org_id == user.org_id).all()
    pids = [p.id for p in projects]
    pname = {p.id: p.name for p in projects}

    users_total = db.query(User).filter(User.org_id == user.org_id).count()

    def chatq():
        q = db.query(ChatMessage)
        return q.filter(ChatMessage.project_id.in_(pids)) if pids else q.filter(False)

    chat_total = chatq().count()
    prompts_total = chatq().filter(ChatMessage.role == "user").count()
    recent_prompts = [
        {
            "id": m.id,
            "project_id": m.project_id,
            "project_name": pname.get(m.project_id, ""),
            "content": (m.content or "")[:240],
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in chatq()
        .filter(ChatMessage.role == "user")
        .order_by(ChatMessage.created_at.desc())
        .limit(12)
        .all()
    ]

    system = {"available": psutil is not None}
    if psutil is not None:
        vm = psutil.virtual_memory()
        du = psutil.disk_usage(os.path.abspath("."))
        system.update(
            {
                "cpu_percent": psutil.cpu_percent(interval=0.3),
                "ram_percent": vm.percent,
                "ram_used_gb": round(vm.used / 1e9, 2),
                "ram_total_gb": round(vm.total / 1e9, 2),
                "disk_percent": du.percent,
                "disk_used_gb": round(du.used / 1e9, 2),
                "disk_total_gb": round(du.total / 1e9, 2),
            }
        )

    snap = metrics.snapshot()
    return {
        "users": {
            "total": users_total,
            "active": snap["active_users_count"],
            "active_emails": snap["active_users"],
        },
        "chat": {
            "messages": chat_total,
            "prompts": prompts_total,
            "recent_prompts": recent_prompts,
        },
        "system": system,
        "requests": {
            "total": snap["requests_total"],
            "last_hour": snap["requests_last_hour"],
            "last_minute": snap["requests_last_minute"],
            "by_method": snap["by_method"],
            "uptime_seconds": snap["uptime_seconds"],
        },
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
