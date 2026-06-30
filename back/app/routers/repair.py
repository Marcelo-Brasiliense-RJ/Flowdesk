"""Auto-reparo colaborativo: a IA diagnostica o erro de um teste e propõe a
correção do Script; o usuário aprova antes de aplicar. Reusa o contexto de
arquivos do chat e roda a mesma stack OpenAI do restante do app.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..services import ai_config
from ..database import get_db
from ..models import Execution, SourceFile, Stage, User
from ..schemas import RepairApplyIn, RepairProposeIn, RepairProposeOut
from .chat import _attachment_context
from .projects import get_project

router = APIRouter(prefix="/api", tags=["repair"])

_REPAIR_INSTR = (
    "Você conserta scripts Python de automação do FlowDesk. Recebe o CÓDIGO ATUAL e o "
    "ERRO da última execução. Devolva SOMENTE um JSON com este formato exato: "
    '{"diagnosis": "...", "change_summary": "...", "fixed_code": "..."}. '
    "diagnosis: explique de forma AMIGÁVEL e tranquilizadora o que aconteceu, em linguagem "
    "simples para um usuário de negócio, sem jargão e SEM culpar a pessoa. Use um tom calmo "
    "e gentil, 1 a 2 frases. "
    "change_summary: explique de forma amigável e positiva o que você vai fazer para "
    "resolver, transmitindo segurança, 1 a 2 frases simples. "
    "fixed_code: o script Python COMPLETO corrigido, mantendo a mesma finalidade e o uso "
    "do SDK flowdesk_sdk (get_file/get_input/output_path/set_output). "
    "AMBIENTE: as bibliotecas disponíveis são pandas, openpyxl e o SDK; NÃO importe "
    "bibliotecas não instaladas (PyPDF2, tabula, camelot, pdfminer etc.). "
    "Para ler PDF (editável OU escaneado) ou imagem use SEMPRE "
    "`from flowdesk_sdk import extract_document` e `doc = extract_document(get_file())` "
    "(detecta sozinho e faz OCR local; doc['text'] tem o texto). Quando usar OCR, inclua "
    "no set_output a chave `_ocr_review` = {'text': doc['text'], 'mean_confidence': "
    "doc['mean_confidence'], 'needs_review': doc['needs_review'], 'low_confidence': "
    "[l['text'] for l in doc['low_confidence']]}. Não escreva nada fora do JSON."
)


def _script_stage(db: Session, project_id: int, stage_id: int) -> Stage:
    stage = db.get(Stage, stage_id)
    if stage is None or stage.project_id != project_id or stage.type not in ("script", "agent"):
        raise HTTPException(status_code=404, detail="Etapa de script não encontrada")
    return stage


def _stage_source(db: Session, project_id: int, stage: Stage) -> SourceFile | None:
    if not stage.entry_file:
        return None
    return (
        db.query(SourceFile)
        .filter(SourceFile.project_id == project_id, SourceFile.path == stage.entry_file)
        .first()
    )


def _plan_profile_context(plan: dict, profile: dict) -> str:
    """Bloco de contexto com o plano selado e o perfil contábil, para a correção
    respeitar o contrato original. Vazio quando não há plano nem perfil."""
    parts = []
    if plan:
        parts.append("PLANO SELADO (contrato original):\n" + json.dumps(plan, ensure_ascii=False, indent=2))
    if profile:
        parts.append("PERFIL CONTÁBIL:\n" + json.dumps(profile, ensure_ascii=False, indent=2))
    return "\n\n".join(parts)


@router.post(
    "/projects/{project_id}/stages/{stage_id}/repair/propose",
    response_model=RepairProposeOut,
)
def repair_propose(
    project_id: int,
    stage_id: int,
    body: RepairProposeIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project(db, project_id, user)
    if not settings.ai_enabled:
        raise HTTPException(status_code=400, detail="IA indisponível para reparo.")
    stage = _script_stage(db, project_id, stage_id)
    row = _stage_source(db, project_id, stage)
    code = row.content if row else ""

    execu = db.get(Execution, body.execution_id)
    stderr = (execu.stderr if execu and execu.project_id == project_id else "") or ""
    input_data = (execu.input_data if execu else {}) or {}

    paths = [v for v in input_data.values() if isinstance(v, str) and v]
    ctx = _attachment_context(project_id, paths) if paths else ""

    messages = [{"role": "system", "content": _REPAIR_INSTR}]
    if ctx:
        messages.append({"role": "system", "content": ctx})
    pp_ctx = _plan_profile_context(project.plan, project.accounting_profile)
    if pp_ctx:
        messages.append({"role": "system", "content": pp_ctx})
    user_msg = f"CÓDIGO ATUAL:\n\n{code[:6000]}\n\nERRO:\n\n{stderr[:3000]}"
    if body.hint and body.hint.strip():
        user_msg += f"\n\nDICA DO USUÁRIO: {body.hint.strip()}"
    messages.append({"role": "user", "content": user_msg})

    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        resp = client.chat.completions.create(
            model=ai_config.get_model(),
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Falha ao consultar a IA: {exc}")

    fixed = (data.get("fixed_code") or "").strip()
    has_changes = bool(fixed) and fixed != (code or "").strip()
    return RepairProposeOut(
        diagnosis=(data.get("diagnosis") or "").strip(),
        change_summary=(data.get("change_summary") or "").strip(),
        fixed_code=fixed,
        has_changes=has_changes,
    )


@router.post("/projects/{project_id}/stages/{stage_id}/repair/apply")
def repair_apply(
    project_id: int,
    stage_id: int,
    body: RepairApplyIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project(db, project_id, user)
    stage = _script_stage(db, project_id, stage_id)
    if not body.code.strip():
        raise HTTPException(status_code=400, detail="Código vazio.")
    row = _stage_source(db, project_id, stage)
    if row:
        row.content = body.code
    else:
        db.add(SourceFile(project_id=project_id, path=stage.entry_file, content=body.code))
    db.commit()
    return {"ok": True}
