"""Schema único do PLANO (contrato Planejador -> Construtor) e do PERFIL contábil.

Fonte única de verdade: o Construtor lê o Plan (não a transcrição do chat) e o
Classificador (design e runtime) lê o AccountingProfile.
"""
from __future__ import annotations

from pydantic import BaseModel


class PlanColuna(BaseModel):
    nome: str
    significado: str = ""


class PlanFonte(BaseModel):
    formato: str = ""          # xlsx | csv | pdf | sheets
    descricao: str = ""
    colunas: list[PlanColuna] = []


class PlanSaida(BaseModel):
    formato: str = ""
    contrato: str = ""          # regras do destino (ex.: layout de importação do Domínio)
    colunas: list[PlanColuna] = []
    destino_sistema: str | None = None  # ex.: "Domínio", "SAP"


class Plan(BaseModel):
    fonte: PlanFonte = PlanFonte()
    regra_negocio: str = ""
    saida: PlanSaida = PlanSaida()
    gatilho: str = ""           # manual | agendado | webhook
    tratamento_erros: str = ""
    contabil: bool = False
    notas: str = ""
    selado: bool = False


class ContaContabil(BaseModel):
    codigo: str
    nome: str = ""


class AccountingProfile(BaseModel):
    regime: str | None = None   # simples | presumido | real
    plano_de_contas: list[ContaContabil] = []
    erp_destino: str | None = None
    layout_destino: str | None = None
    regras_fiscais: list[str] = []
    confirmado: bool = False


CAMPOS_CRITICOS = ("fonte.formato", "regra_negocio", "saida.formato", "gatilho")


def _get_path(plan: Plan, dotted: str):
    obj = plan
    for part in dotted.split("."):
        obj = getattr(obj, part)
    return obj


def plan_missing_fields(plan: Plan) -> list[str]:
    return [c for c in CAMPOS_CRITICOS if not str(_get_path(plan, c) or "").strip()]


def plan_is_complete(plan: Plan) -> bool:
    return not plan_missing_fields(plan)
