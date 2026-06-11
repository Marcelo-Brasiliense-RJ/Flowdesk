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

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import metrics
from ..auth import hash_password, require_admin
from ..database import get_db
from ..models import ChatMessage, Project, User
from ..schemas import AdminUserCreate, AdminUserOut, AdminUserUpdate

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

    # uso de IA: tokens estimados das conversas (total + top projetos)
    tokens_total = (
        chatq().with_entities(func.coalesce(func.sum(ChatMessage.tokens), 0)).scalar() or 0
    )
    tokens_rows = (
        db.query(ChatMessage.project_id, func.sum(ChatMessage.tokens).label("t"))
        .filter(ChatMessage.project_id.in_(pids) if pids else False)
        .group_by(ChatMessage.project_id)
        .order_by(func.sum(ChatMessage.tokens).desc())
        .limit(5)
        .all()
    )
    ai_usage = {
        "tokens_total": int(tokens_total),
        "top_projects": [
            {"project_id": r[0], "project_name": pname.get(r[0], ""), "tokens": int(r[1] or 0)}
            for r in tokens_rows
        ],
    }

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
        "ai_usage": ai_usage,
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


# ---- gestão de usuários (papéis administráveis pela UI, sem mexer em env) ----

_VALID_ROLES = ("admin", "dev", "user")


@router.get("/users", response_model=list[AdminUserOut])
def list_users(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return (
        db.query(User)
        .filter(User.org_id == user.org_id)
        .order_by(User.email)
        .all()
    )


@router.post("/users", response_model=AdminUserOut)
def create_user(
    body: AdminUserCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    if body.role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail="Papel inválido (admin, dev ou user)")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Senha deve ter ao menos 8 caracteres")
    email = body.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Já existe um usuário com este e-mail")
    novo = User(
        org_id=user.org_id,
        email=email,
        name=body.name.strip(),
        hashed_password=hash_password(body.password),
        role=body.role,
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_user(
    user_id: int,
    body: AdminUserUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    alvo = db.get(User, user_id)
    if alvo is None or alvo.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    if body.role is not None:
        if body.role not in _VALID_ROLES:
            raise HTTPException(status_code=400, detail="Papel inválido (admin, dev ou user)")
        if alvo.id == user.id and body.role != "admin":
            raise HTTPException(status_code=400, detail="Você não pode remover seu próprio papel de admin")
        alvo.role = body.role
    if body.is_active is not None:
        if alvo.id == user.id and not body.is_active:
            raise HTTPException(status_code=400, detail="Você não pode desativar a si mesmo")
        alvo.is_active = body.is_active
    if body.name is not None:
        alvo.name = body.name.strip()
    if body.password:
        if len(body.password) < 8:
            raise HTTPException(status_code=400, detail="Senha deve ter ao menos 8 caracteres")
        alvo.hashed_password = hash_password(body.password)
    db.commit()
    db.refresh(alvo)
    return alvo
