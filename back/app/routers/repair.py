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
from ..models import ChatMessage, Execution, PendingAction, SourceFile, Stage, User
from ..schemas import (
    ChatMessageOut,
    PendingActionOut,
    ReportRepairIn,
    ReportSeedIn,
    RepairApplyIn,
    RepairProposeIn,
    RepairProposeOut,
)
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


def _execution_context(execu) -> str:
    """Bloco com o ERRO (stderr) e o RESULTADO (output_data) da execução. Em falso
    sucesso não há stderr, então o resultado é o único sinal do que ficou errado."""
    parts = []
    stderr = (getattr(execu, "stderr", "") or "").strip()
    if stderr:
        parts.append("ERRO (stderr):\n" + stderr[:3000])
    output = getattr(execu, "output_data", None) or {}
    if output:
        resumo = output.get("resumo")
        if isinstance(resumo, str) and resumo.strip():
            parts.append("RESUMO DO RESULTADO:\n" + resumo[:1500])
        outras = {k: v for k, v in output.items() if k not in ("resumo",) and not str(k).startswith("_")}
        if outras:
            parts.append("SAÍDA (chaves):\n" + json.dumps(outras, ensure_ascii=False, default=str)[:1500])
    return "\n\n".join(parts)


def _execution_report_snapshot(execu) -> dict:
    """Resumo da execucao para fixar no chat (card). So nomes de arquivo, sem caminhos."""
    output = (getattr(execu, "output_data", None) or {})
    stderr = (getattr(execu, "stderr", "") or "").strip()
    input_data = (getattr(execu, "input_data", None) or {})
    files = [v.replace("\\", "/").split("/")[-1] for v in input_data.values() if isinstance(v, str) and ("/" in v or "\\" in v)]
    return {
        "execution_id": execu.id,
        "status": execu.status,
        "resumo": output.get("resumo") if isinstance(output.get("resumo"), str) else None,
        "output_keys": [k for k in output.keys() if not str(k).startswith("_")],
        "stderr_excerpt": stderr[:600] or None,
        "input_files": files,
    }


def run_repair(db: Session, project, stage: Stage, execution_id: str, hint: str | None) -> RepairProposeOut:
    """Núcleo do reparador: monta o contexto (código + execução + plano + anexos),
    chama a IA e devolve a proposta. Reusado pelo endpoint /repair/propose e pelo
    fluxo de reporte no chat."""
    row = _stage_source(db, project.id, stage)
    code = row.content if row else ""

    execu = db.get(Execution, execution_id)
    if execu is not None and execu.project_id != project.id:
        execu = None
    exec_ctx = _execution_context(execu) if execu is not None else ""
    input_data = (execu.input_data if execu else {}) or {}

    paths = [v for v in input_data.values() if isinstance(v, str) and v]
    ctx = _attachment_context(project.id, paths) if paths else ""

    messages = [{"role": "system", "content": _REPAIR_INSTR}]
    if ctx:
        messages.append({"role": "system", "content": ctx})
    pp_ctx = _plan_profile_context(project.plan, project.accounting_profile)
    if pp_ctx:
        messages.append({"role": "system", "content": pp_ctx})
    user_msg = f"CÓDIGO ATUAL:\n\n{code[:6000]}\n\n{exec_ctx}"
    if hint and hint.strip():
        user_msg += f"\n\nO QUE O USUÁRIO DIZ QUE ESTÁ ERRADO: {hint.strip()}"
    messages.append({"role": "user", "content": user_msg})

    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model=ai_config.get_model(),
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    data = json.loads(resp.choices[0].message.content or "{}")
    fixed = (data.get("fixed_code") or "").strip()
    return RepairProposeOut(
        diagnosis=(data.get("diagnosis") or "").strip(),
        change_summary=(data.get("change_summary") or "").strip(),
        fixed_code=fixed,
        has_changes=bool(fixed) and fixed != (code or "").strip(),
    )


def _repair_action_payload(entry_file: str, proposal: RepairProposeOut) -> dict | None:
    """Payload da PendingAction de correção, ou None quando a IA não propôs mudança."""
    if not proposal.has_changes:
        return None
    return {"path": entry_file, "content": proposal.fixed_code}


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
    try:
        return run_repair(db, project, stage, body.execution_id, body.hint)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Falha ao consultar a IA: {exc}")


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


@router.post("/projects/{project_id}/chat/report", response_model=ChatMessageOut)
def chat_report(
    project_id: int,
    body: ReportSeedIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project(db, project_id, user)
    execu = db.get(Execution, body.execution_id)
    if execu is None or execu.project_id != project_id:
        raise HTTPException(status_code=404, detail="Execução não encontrada")
    msg = ChatMessage(
        project_id=project_id,
        role="assistant",
        content="Vi o resultado desta execução. Me diga o que ficou errado que eu ajusto a automação.",
        meta={"execution_report": _execution_report_snapshot(execu)},
        tokens=0,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


@router.post("/projects/{project_id}/chat/report-repair")
def chat_report_repair(
    project_id: int,
    body: ReportRepairIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project(db, project_id, user)
    if not settings.ai_enabled:
        raise HTTPException(status_code=400, detail="IA indisponível para reparo.")
    execu = db.get(Execution, body.execution_id)
    if execu is None or execu.project_id != project_id:
        raise HTTPException(status_code=404, detail="Execução não encontrada")
    stage = _script_stage(db, project_id, execu.stage_id)

    db.add(ChatMessage(
        project_id=project_id, role="user",
        content=body.message, meta={"execution_id": body.execution_id}, tokens=0,
    ))
    try:
        proposal = run_repair(db, project, stage, body.execution_id, body.message)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Falha ao consultar a IA: {exc}")

    texto = proposal.diagnosis
    if proposal.change_summary:
        texto = (texto + "\n\n" + proposal.change_summary).strip()
    if not proposal.has_changes:
        texto = (texto or "Não encontrei uma correção automática.") + (
            "\n\nSe puder, detalhe melhor o que ficou errado no resultado."
        )
    assistant = ChatMessage(project_id=project_id, role="assistant", content=texto, meta={}, tokens=0)
    db.add(assistant)

    action = None
    payload = _repair_action_payload(stage.entry_file, proposal)
    if payload is not None:
        action = PendingAction(
            project_id=project_id,
            kind="edit_file",
            title="Correção da automação",
            payload=payload,
        )
        db.add(action)
    db.commit()
    db.refresh(assistant)
    out_action = None
    if action is not None:
        db.refresh(action)
        out_action = PendingActionOut.model_validate(action).model_dump(mode="json")
    return {
        "message": ChatMessageOut.model_validate(assistant).model_dump(mode="json"),
        "action": out_action,
    }
