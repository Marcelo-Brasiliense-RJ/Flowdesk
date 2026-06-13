"""Classificação contábil: regras De/Para por projeto + sugestão por IA.

Privacidade (decisão de projeto): para a IA vão APENAS os textos de histórico
dos grupos e a lista de contas candidatas (código + nome). Valores, saldos,
agência/conta e CNPJ nunca saem da máquina.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import DataRow, DataTable, User
from .projects import get_project

router = APIRouter(prefix="/api", tags=["classify"])

REGRAS_TABLE = "regras_classificacao"


def _regras_table(db: Session, project_id: int) -> DataTable:
    t = (
        db.query(DataTable)
        .filter(DataTable.project_id == project_id, DataTable.name == REGRAS_TABLE)
        .first()
    )
    if t is None:
        t = DataTable(project_id=project_id, name=REGRAS_TABLE,
                      columns=["padrao", "conta_codigo", "conta_nome", "origem"])
        db.add(t)
        db.commit()
        db.refresh(t)
    return t


class RegraIn(BaseModel):
    padrao: str
    conta_codigo: str
    conta_nome: str = ""
    origem: str = "revisao"


def salvar_regras_interno(db: Session, project_id: int, regras: list[RegraIn]) -> dict:
    """Upsert por padrão (a correção mais recente vence). Compartilhado com o
    endpoint token-gated do app publicado."""
    t = _regras_table(db, project_id)
    existentes = {r.values.get("padrao"): r for r in
                  db.query(DataRow).filter(DataRow.table_id == t.id)}
    salvas = 0
    for regra in regras:
        padrao = regra.padrao.strip().upper()
        if not padrao or not regra.conta_codigo.strip():
            continue
        values = {"padrao": padrao, "conta_codigo": regra.conta_codigo.strip(),
                  "conta_nome": regra.conta_nome.strip(), "origem": regra.origem}
        if padrao in existentes:
            existentes[padrao].values = values
        else:
            db.add(DataRow(table_id=t.id, values=values))
        salvas += 1
    db.commit()
    return {"ok": True, "salvas": salvas}


@router.get("/projects/{project_id}/regras-classificacao")
def listar_regras(project_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    t = _regras_table(db, project_id)
    rows = db.query(DataRow).filter(DataRow.table_id == t.id).all()
    return [{"id": r.id, **r.values} for r in rows]


@router.post("/projects/{project_id}/regras-classificacao")
def salvar_regras(project_id: int, regras: list[RegraIn],
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    return salvar_regras_interno(db, project_id, regras)


@router.delete("/projects/{project_id}/regras-classificacao/{row_id}")
def excluir_regra(project_id: int, row_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    t = _regras_table(db, project_id)
    row = db.get(DataRow, row_id)
    if row is None or row.table_id != t.id:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    db.delete(row)
    db.commit()
    return {"ok": True}


class GrupoIn(BaseModel):
    padrao: str
    tipo: str = ""  # credito | debito


class ContaIn(BaseModel):
    codigo: str
    nome: str


class SugestaoRequest(BaseModel):
    grupos: list[GrupoIn]
    contas: list[ContaIn]


@router.post("/projects/{project_id}/classificar-grupos")
def classificar_grupos(project_id: int, req: SugestaoRequest,
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Sugere conta contábil por grupo de histórico. Payload mínimo para a IA."""
    get_project(db, project_id, user)
    if not req.grupos:
        return {"sugestoes": []}
    if not settings.ai_enabled:
        # modo simulado: heurística por palavra no nome da conta
        sugestoes = []
        for g in req.grupos:
            alvo = next((c for c in req.contas
                         if any(w in c.nome.upper() for w in g.padrao.split()[:2] if len(w) > 4)), None)
            sugestoes.append({"padrao": g.padrao,
                              "conta_codigo": alvo.codigo if alvo else "",
                              "confianca": 0.3 if alvo else 0.0})
        return {"sugestoes": sugestoes}

    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)
    contas_txt = "\n".join(f"{c.codigo} = {c.nome}" for c in req.contas[:400])
    validos = {c.codigo for c in req.contas}
    sugestoes: list[dict] = []
    # lotes pequenos: medido empiricamente, acima de ~10 grupos por chamada o
    # gpt-4o-mini deixa de copiar o campo "padrao" literalmente e devolve
    # categorias genéricas que não casam com grupo nenhum.
    LOTE = 10
    for ini in range(0, len(req.grupos), LOTE):
        lote = req.grupos[ini:ini + LOTE]
        grupos_txt = "\n".join(f'- padrao: "{g.padrao}" | tipo: {g.tipo}' for g in lote)
        prompt = (
            "Você é um contador brasileiro classificando movimentos de extrato bancário "
            "na contrapartida contábil. O lado banco já está resolvido; sugira APENAS a "
            "contrapartida, escolhendo estritamente um código da lista de contas analíticas.\n"
            "Para tipo credito (entrada no banco) a contrapartida típica é receita/recebimento; "
            "para tipo debito (saída) é despesa/pagamento.\n\n"
            f"CONTAS ANALÍTICAS DISPONÍVEIS:\n{contas_txt}\n\n"
            f"GRUPOS DE HISTÓRICO (um por linha):\n{grupos_txt}\n\n"
            "Responda SÓ JSON, com UMA sugestão para CADA grupo da lista, no formato "
            '{"sugestoes": [{"padrao": "...", "conta_codigo": "...", "confianca": 0.0}]}. '
            'REGRAS: o campo "padrao" deve ser a CÓPIA EXATA, caractere a caractere, do '
            "padrao do grupo (nunca resuma nem categorize); confianca entre 0 e 1; "
            "conta_codigo vazio se não houver conta adequada (NUNCA invente código fora da lista)."
        )
        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        try:
            data = json.loads(resp.choices[0].message.content or "{}")
            parte = data.get("sugestoes", [])
        except json.JSONDecodeError:
            parte = []
        # descarta padrões que o modelo inventou e códigos fora da lista
        padroes_lote = {g.padrao for g in lote}
        for s in parte:
            if s.get("padrao") not in padroes_lote:
                continue
            if str(s.get("conta_codigo", "")) not in validos:
                s["conta_codigo"] = ""
                s["confianca"] = 0.0
            sugestoes.append(s)
    return {"sugestoes": sugestoes}
