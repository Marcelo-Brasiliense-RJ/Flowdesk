"""Assistente (wizard) — monta o grafo de nós deterministicamente a partir de
`project.wizard_state` e gera o código do Script reaproveitando a geração do chat.

O frontend é dono da estrutura das 4 etapas (Gatilho, Entrada, Processamento,
Resultado). Este endpoint traduz essa intenção para o modelo canônico do FlowDesk
(Stage/Edge/SourceFile), de forma IDEMPOTENTE: cada nó gerenciado pelo wizard é
marcado em `config["_wizard_role"]`, então reconstruir atualiza em vez de duplicar.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import Edge, SourceFile, Stage, User
from ..schemas import WizardBuildOut
from .chat import (
    SYSTEM_PROMPT,
    _attachment_context,
    _generate_build,
    _project_context,
)
from .projects import get_project, slugify

router = APIRouter(prefix="/api", tags=["wizard"])

ROLE = "_wizard_role"  # marca de idempotência nos config dos nós do wizard

_FALLBACK_SCRIPT = (
    "from flowdesk_sdk import get_file, set_output, output_path\n"
    "import pandas as pd\n\n"
    "df = pd.read_excel(get_file())\n"
    "out = output_path('resultado.xlsx')\n"
    "df.to_excel(out, index=False)\n"
    "set_output({'arquivo_resultado': str(out), 'resumo': {'linhas': len(df)}})\n"
)


def _wizard_stage(stages: list[Stage], role: str) -> Stage | None:
    for s in stages:
        if (s.config or {}).get(ROLE) == role:
            return s
    return None


def _unique_key(db: Session, project_id: int, base: str, ignore_id: int | None) -> str:
    key, n = base, 1
    while True:
        clash = (
            db.query(Stage)
            .filter(Stage.project_id == project_id, Stage.key == key)
            .first()
        )
        if clash is None or clash.id == ignore_id:
            return key
        n += 1
        key = f"{base}-{n}"


def _upsert_stage(
    db: Session,
    project_id: int,
    role: str,
    *,
    stype: str,
    name: str,
    config: dict,
    pos_x: float,
    pos_y: float,
    existing: list[Stage],
) -> Stage:
    """Cria ou atualiza um nó gerenciado pelo wizard (idempotente por role)."""
    config = {**config, ROLE: role}
    stage = _wizard_stage(existing, role)
    if stage is not None:
        stage.type = stype
        stage.name = name
        stage.config = config
        stage.pos_x = pos_x
        stage.pos_y = pos_y
        if stype in ("script", "job", "agent") and not stage.entry_file:
            stage.entry_file = f"{stage.key}.py"
        db.flush()
        return stage
    key = _unique_key(db, project_id, slugify(name) or role, None)
    entry = f"{key}.py" if stype in ("script", "job", "agent") else ""
    stage = Stage(
        project_id=project_id,
        type=stype,
        name=name,
        key=key,
        config=config,
        entry_file=entry,
        pos_x=pos_x,
        pos_y=pos_y,
    )
    db.add(stage)
    db.flush()
    return stage


def _write_source(db: Session, project_id: int, path: str, content: str) -> None:
    row = (
        db.query(SourceFile)
        .filter(SourceFile.project_id == project_id, SourceFile.path == path)
        .first()
    )
    if row:
        row.content = content
    else:
        db.add(SourceFile(project_id=project_id, path=path, content=content))
    db.flush()


def _input_fields(inp: dict) -> list[dict]:
    kind = inp.get("kind")
    if kind == "file":
        return [{"name": "arquivo", "label": "Arquivo", "type": "file"}]
    if kind == "fields":
        out = []
        for i, f in enumerate(inp.get("fields") or []):
            label = (f.get("label") or "").strip() or f"Campo {i + 1}"
            out.append(
                {"name": slugify(label) or f"campo_{i + 1}", "label": label,
                 "type": f.get("type", "text")}
            )
        return out
    return []


def _generate_script(db: Session, project_id: int, ws: dict) -> tuple[str, str]:
    """Gera o código do Script via a geração estruturada do chat. Retorna
    (explicação, código)."""
    process = (ws.get("process") or {}).get("description", "").strip()
    inp = ws.get("input") or {}
    out = ws.get("output") or {}
    out_kind = out.get("kind", "download")
    intent = (
        f"Monte agora a automação. Tarefa: {process}. "
        f"Entrada: {inp.get('kind', 'nenhuma')}. "
        f"Saída desejada: "
        + ("um arquivo para download (use output_path e set_output com "
           "'arquivo_resultado' e 'resumo')." if out_kind == "download"
           else "um resumo na tela (set_output com a chave 'resumo').")
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": _project_context(db, project_id)},
    ]
    sample = inp.get("sample_file")
    if sample:
        ctx = _attachment_context(project_id, [sample])
        if ctx:
            messages.append({"role": "system", "content": ctx})
    messages.append({"role": "user", "content": intent})

    explanation, actions = _generate_build(messages)
    code = ""
    for a in actions:
        if a.get("kind") in ("create_file", "edit_file") and a.get("content"):
            code = a["content"]
            break
    if not code:
        code = _FALLBACK_SCRIPT
    return explanation or "Fluxo gerado.", code


@router.post("/projects/{project_id}/wizard/build", response_model=WizardBuildOut)
def build_from_wizard(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Monta (ou re-monta) o fluxo a partir do rascunho salvo do assistente."""
    project = get_project(db, project_id, user)
    ws = dict(project.wizard_state or {})
    if not (ws.get("process") or {}).get("description", "").strip():
        raise HTTPException(
            status_code=400,
            detail="Descreva o processamento (etapa 3) antes de montar a automação.",
        )

    existing = db.query(Stage).filter(Stage.project_id == project_id).all()
    inp = ws.get("input") or {}
    out = ws.get("output") or {}
    trig = ws.get("trigger") or {}
    out_kind = out.get("kind", "download")

    stage_ids: dict[str, int] = {}

    # ---- Entrada (Form) ----
    input_stage = None
    if inp.get("kind") in ("file", "fields"):
        input_stage = _upsert_stage(
            db, project_id, "input", stype="form", name="Entrada",
            config={
                "title": "Entrada de dados",
                "mode": "input",
                "submit_label": "Executar",
                "fields": _input_fields(inp),
            },
            pos_x=40, pos_y=120, existing=existing,
        )
        stage_ids["input"] = input_stage.id

    # ---- Processamento (Script) + código gerado ----
    explanation, code = _generate_script(db, project_id, ws)
    script_stage = _upsert_stage(
        db, project_id, "script", stype="script", name="Processamento",
        config={"description": (ws.get("process") or {}).get("description", "")[:200]},
        pos_x=360, pos_y=120, existing=existing,
    )
    _write_source(db, project_id, script_stage.entry_file, code)
    stage_ids["script"] = script_stage.id

    # ---- Resultado (Form em modo result) ----
    result_config = {
        "title": "Resultado",
        "mode": "result",
        "summary_key": "resumo",
    }
    if out_kind == "download":
        result_config["result_file_key"] = "arquivo_resultado"
    result_stage = _upsert_stage(
        db, project_id, "result", stype="form", name="Resultado",
        config=result_config, pos_x=680, pos_y=120, existing=existing,
    )
    stage_ids["result"] = result_stage.id

    # ---- Gatilho (Job agendado ou Hook webhook) ----
    trigger_stage = None
    if trig.get("kind") == "schedule":
        trigger_stage = _upsert_stage(
            db, project_id, "trigger", stype="job", name="Agendamento",
            config={
                "enabled": True,
                "schedule": {
                    "type": "interval",
                    "every": int(trig.get("every", 1)),
                    "unit": trig.get("unit", "hours"),
                },
            },
            pos_x=360, pos_y=-40, existing=existing,
        )
        stage_ids["trigger"] = trigger_stage.id
    elif trig.get("kind") == "webhook":
        import uuid

        trigger_stage = _upsert_stage(
            db, project_id, "trigger", stype="hook", name="Webhook",
            config={"webhook_id": uuid.uuid4().hex, "method": "POST"},
            pos_x=360, pos_y=-40, existing=existing,
        )
        stage_ids["trigger"] = trigger_stage.id

    # ---- Edges (reconstrói as conexões do grafo do wizard) ----
    managed_ids = {s.id for s in (input_stage, script_stage, result_stage, trigger_stage) if s}
    db.query(Edge).filter(
        Edge.project_id == project_id,
        Edge.source_stage_id.in_(managed_ids),
    ).delete(synchronize_session=False)

    def link(src: Stage, dst: Stage, label: str) -> None:
        db.add(Edge(project_id=project_id, source_stage_id=src.id,
                    target_stage_id=dst.id, variable_label=label))

    if input_stage:
        link(input_stage, script_stage, "entrada")
    if trigger_stage:
        link(trigger_stage, script_stage, "gatilho")
    link(script_stage, result_stage, "resultado")

    # marca que o rascunho está em dia com o que foi montado
    ws["_built"] = True
    ws["_stage_ids"] = stage_ids
    project.wizard_state = ws
    project.wizard_dirty = False
    db.commit()

    return WizardBuildOut(
        explanation=explanation,
        script_file=script_stage.entry_file,
        stage_ids=stage_ids,
        ai_enabled=settings.ai_enabled,
    )
