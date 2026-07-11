"""Published application runtime (what the end user accesses).

A published project is reachable at /app/{subdomain}. Login is gated by the
project's access policy (domain SSO or whitelist). Submitting a Form persists
uploads, enqueues the downstream Script and the published app advances along
the workflow edges automatically.
"""
from __future__ import annotations

import datetime as dt
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from ..auth import ALGORITHM, verify_password
from ..config import settings
from ..database import get_db
from ..models import Edge, Execution, Project, ProjectMember, Stage, User
from ..ratelimit import _client_ip, enforce
from ..runtime.runner import runtime
from ..services import storage

router = APIRouter(prefix="/api/app", tags=["published"])


def _get_live_project(db: Session, subdomain: str) -> Project:
    project = db.query(Project).filter(Project.subdomain == subdomain).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Aplicação não encontrada")
    return project


def _access_allowed(db: Session, project: Project, email: str) -> bool:
    email = email.lower().strip()
    if project.access_mode == "domain":
        domain = project.allowed_domain.lstrip("@").lower()
        return bool(domain) and email.endswith("@" + domain)
    member = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project.id, ProjectMember.email == email)
        .first()
    )
    return member is not None


def _published_token(email: str, subdomain: str) -> str:
    expire = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=12)
    payload = {"sub": email, "app": subdomain, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def _require_app_user(db: Session, subdomain: str, token: str | None) -> str:
    # modo aberto (temporário): app publicado sem login
    if settings.public_apps_open:
        return "anonimo@aberto"
    if not token:
        raise HTTPException(status_code=401, detail="Login necessário")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Sessão inválida")
    if payload.get("app") != subdomain:
        raise HTTPException(status_code=401, detail="Token inválido para esta aplicação")
    return payload["sub"]


def _entry_stage(stages: list[Stage], edges: list[Edge]) -> Stage | None:
    targets = {e.target_stage_id for e in edges}
    starters = [s for s in stages if s.id not in targets and s.type in ("form", "hook")]
    return starters[0] if starters else (stages[0] if stages else None)


def _next_stage(db: Session, project_id: int, stage_id: int) -> Stage | None:
    edge = (
        db.query(Edge)
        .filter(Edge.project_id == project_id, Edge.source_stage_id == stage_id)
        .first()
    )
    return db.get(Stage, edge.target_stage_id) if edge else None


def _stage_dict(s: Stage) -> dict:
    return {"id": s.id, "type": s.type, "name": s.name, "key": s.key, "config": s.config}


@router.get("/{subdomain}/info")
def app_info(subdomain: str, db: Session = Depends(get_db)):
    project = _get_live_project(db, subdomain)
    return {
        "project_id": project.id,
        "name": project.name,
        "subdomain": project.subdomain,
        "status": project.status,
        "access_mode": project.access_mode,
        "allowed_domain": project.allowed_domain,
        "open": settings.public_apps_open,
    }


@router.post("/{subdomain}/login")
def app_login(
    subdomain: str,
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    # Anti brute-force do app publicado: por conta e teto por IP (ver auth.login).
    _email = (email or "").strip().lower()
    enforce(f"applogin:email:{_email}", 10, 300, context=f"ip={_client_ip(request)}")
    enforce(f"applogin:ip:{_client_ip(request)}", 50, 300)
    project = _get_live_project(db, subdomain)
    # authenticate the identity against a real user account (credential required)
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if user is None or not user.is_active or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")
    # then authorize against the project's access policy
    if not _access_allowed(db, project, email):
        raise HTTPException(status_code=403, detail="Acesso não autorizado para este e-mail")
    return {"access_token": _published_token(email, subdomain), "email": email}


@router.get("/{subdomain}/flow")
def app_flow(subdomain: str, token: str | None = None, db: Session = Depends(get_db)):
    project = _get_live_project(db, subdomain)
    _require_app_user(db, subdomain, token)
    stages = db.query(Stage).filter(Stage.project_id == project.id).all()
    edges = db.query(Edge).filter(Edge.project_id == project.id).all()
    entry = _entry_stage(stages, edges)
    return {
        "project": {"name": project.name, "subdomain": project.subdomain},
        "stages": [_stage_dict(s) for s in stages],
        "entry_stage_id": entry.id if entry else None,
    }


@router.get("/{subdomain}/stages/{stage_id}")
def app_stage(subdomain: str, stage_id: int, token: str | None = None, db: Session = Depends(get_db)):
    project = _get_live_project(db, subdomain)
    _require_app_user(db, subdomain, token)
    stage = db.get(Stage, stage_id)
    if stage is None or stage.project_id != project.id:
        raise HTTPException(status_code=404, detail="Etapa não encontrada")
    return _stage_dict(stage)


@router.post("/{subdomain}/stages/{stage_id}/submit")
async def app_submit(
    subdomain: str,
    stage_id: int,
    token: str | None = Form(None),
    payload: str | None = Form(None),
    file_fields: str | None = Form(None),
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    import json

    project = _get_live_project(db, subdomain)
    _require_app_user(db, subdomain, token)
    stage = db.get(Stage, stage_id)
    if stage is None or stage.project_id != project.id:
        raise HTTPException(status_code=404, detail="Etapa não encontrada")

    root = storage.ensure_project_dirs(project)
    session_id = uuid.uuid4().hex
    upload_dir = root / "_uploads" / session_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    values: dict = json.loads(payload) if payload else {}
    field_names: list[str] = json.loads(file_fields) if file_fields else []
    from pathlib import PurePath

    for idx, f in enumerate(files):
        if not f.filename:
            continue
        if f.size and f.size > 50 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Arquivo muito grande (máx. 50 MB)")
        # use only the basename to prevent path traversal via the multipart filename
        safe_name = PurePath(f.filename).name or "arquivo"
        dest = upload_dir / safe_name
        with dest.open("wb") as fh:
            fh.write(await f.read())
        field = field_names[idx] if idx < len(field_names) else safe_name
        values[field] = str(dest)
        values.setdefault("arquivo", str(dest))

    nxt = _next_stage(db, project.id, stage.id)
    if nxt is None:
        return {"status": "done", "values": values}

    if nxt.type in ("script", "job", "agent"):
        execu = Execution(
            id=str(uuid.uuid4()),
            project_id=project.id,
            stage_id=nxt.id,
            stage_name=nxt.name,
            stage_type=nxt.type,
            status="queued",
            input_data=values,
        )
        db.add(execu)
        db.commit()
        runtime.submit(execu.id)
        result_stage = _next_stage(db, project.id, nxt.id)
        return {
            "status": "processing",
            "execution_id": execu.id,
            "script_stage_id": nxt.id,
            "result_stage_id": result_stage.id if result_stage else None,
        }

    return {"status": "next_form", "next_stage_id": nxt.id, "values": values}


def _execution_public_view(execu, progress) -> dict:
    """Resposta do app PUBLICADO: nunca expõe o traceback cru (S2) nem o input_data
    com caminhos do servidor (S4). Erro vira mensagem amigável; o traceback completo
    fica só nos logs internos."""
    erro = ""
    if execu.status == "error":
        from ..runtime.runner import _last_error_line
        erro = (execu.output_data or {}).get("erro") or _last_error_line(execu.stderr or "")
    return {
        "id": execu.id,
        "status": execu.status,
        "output": execu.output_data,
        "progress": progress,
        "erro": erro,
        "stderr": erro,  # compat de front: só a mensagem amigável, sem traceback/paths
    }


@router.get("/{subdomain}/executions/{execution_id}")
def app_execution(subdomain: str, execution_id: str, token: str | None = None, db: Session = Depends(get_db)):
    project = _get_live_project(db, subdomain)
    _require_app_user(db, subdomain, token)
    execu = db.get(Execution, execution_id)
    if execu is None or execu.project_id != project.id:
        raise HTTPException(status_code=404, detail="Execução não encontrada")
    return _execution_public_view(execu, storage.read_progress(project.id, execution_id))


@router.post("/{subdomain}/regras-classificacao")
def app_salvar_regras(subdomain: str, body: dict, token: str | None = None,
                      db: Session = Depends(get_db)):
    """Correções feitas na revisão do app publicado viram regras De/Para."""
    project = _get_live_project(db, subdomain)
    _require_app_user(db, subdomain, token)
    from .classify import RegraIn, salvar_regras_interno

    regras = [RegraIn(**r) for r in body.get("regras", [])]
    return salvar_regras_interno(db, project.id, regras)


def _resolve_download_target(root: Path, output_folder_name: str, path: str) -> Path | None:
    candidate = Path(path)
    # B4: rejeita traversal explícito na entrada (defense-in-depth; a validação de
    # parents no app_download também cobre). Absoluto sob a raiz continua válido
    # (é o arquivo_resultado, gerado por output_path()).
    if ".." in candidate.parts:
        return None
    target = (candidate if candidate.is_absolute() else (root / path)).resolve()
    # scripts às vezes gravam só o nome do arquivo; o real vive na pasta de saída
    if not target.exists() and not candidate.is_absolute():
        alt = (root / output_folder_name / path).resolve()
        if alt.exists():
            return alt
    return target


@router.get("/{subdomain}/download")
def app_download(subdomain: str, path: str, token: str | None = None, db: Session = Depends(get_db)):
    project = _get_live_project(db, subdomain)
    _require_app_user(db, subdomain, token)
    root = storage.ensure_project_dirs(project)

    target = _resolve_download_target(root, project.output_folder_name, path)
    root_r = root.resolve()
    if target is None or (root_r not in target.parents and target != root_r):
        raise HTTPException(status_code=400, detail="Caminho inválido")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    return FileResponse(str(target), filename=target.name)
