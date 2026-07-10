"""A1: os três prompts centrais devem ser genéricos, sem conhecimento contábil.

O conhecimento do caso extrato-Domínio vive no reference do template
(templates.py), injetado sob demanda, não hardcoded nos prompts do núcleo.
"""
import sys
import unicodedata
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

from app.routers import chat, orchestrator

# Marcadores contábeis que NÃO podem aparecer nos prompts centrais (o dossiê A1
# lista Domínio / Inicia Lote / aging / conciliação; incluímos crédito/débito e
# os artefatos do De/Para contábil).
MARKERS = [
    "dominio", "inicia lote", "aging", "conciliac", "extrato",
    "credito", "debito", "plano de contas", "regras_classificacao",
    "_classificacao", "_conta_banco",
]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _assert_generico(nome: str, texto: str):
    n = _norm(texto)
    achados = [m for m in MARKERS if m in n]
    assert not achados, f"{nome} ainda tem conteúdo contábil: {achados}"


def test_system_prompt_generico():
    _assert_generico("SYSTEM_PROMPT", chat.SYSTEM_PROMPT)


def test_construtor_prompt_generico():
    _assert_generico("CONSTRUTOR_PROMPT", orchestrator.CONSTRUTOR_PROMPT)
