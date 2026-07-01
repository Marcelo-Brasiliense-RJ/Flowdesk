"""Treinador: agente de auto-evolução (fora do caminho crítico).

Colhe automações publicadas e validadas, guarda plano anonimizado + código como
exemplos few-shot, registra eventos de reparo, e destila propostas de melhoria de
prompt para os agentes de build. Persiste em JSON no STORAGE_DIR, espelhando
services/ai_config.py (zero migração). NADA aqui roda no caminho crítico de
execução/publish: é chamado por hooks best-effort e por endpoints de admin.
"""
from __future__ import annotations

import hashlib
import json
import threading

from ..config import STORAGE_DIR

_DIR = STORAGE_DIR / "treinador"
_lock = threading.Lock()

# arquivos do store
def _examples_path():
    return _DIR / "examples.json"

def _proposals_path():
    return _DIR / "proposals.json"

def _repairs_path():
    return _DIR / "repairs.json"

def _meta_path():
    return _DIR / "meta.json"


def _load(path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(path, data: dict) -> None:
    with _lock:
        _DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _examples() -> list[dict]:
    return _load(_examples_path()).get("items", [])


def _proposals() -> list[dict]:
    return _load(_proposals_path()).get("items", [])


def _repairs() -> list[dict]:
    return _load(_repairs_path()).get("items", [])


TREINADOR_PROMPT = (
    "Você é o Treinador do FlowDesk. Seu trabalho é analisar automações que foram "
    "publicadas e validadas (rodaram em produção sem erro) e os ajustes feitos até "
    "elas irem ao ar, para melhorar os agentes que constroem automações. Você tem "
    "duas tarefas, indicadas em cada chamada:\n"
    "1) ANONIMIZAR: dado um PLANO de automação, remova ou generalize qualquer dado "
    "que identifique um cliente/empresa específico (razões sociais, nomes próprios, "
    "CNPJ, nomes de contas específicas, nomes de colunas com identificadores), "
    "mantendo intacto o PADRÃO estrutural (formatos, tipos de regra, tipo de saída). "
    "Responda SOMENTE o JSON do plano anonimizado.\n"
    "2) DESTILAR: dado um conjunto de exemplos validados e ajustes (reparos, "
    "rejeições), e o system prompt ATUAL de um agente, proponha um system prompt "
    "MELHOR que evite os erros observados e reforce os padrões que deram certo. "
    "Não invente regras não sustentadas pelos exemplos. Responda SOMENTE em JSON "
    '{"proposed_prompt": "...", "rationale": "1 a 3 frases do que muda e por quê"}.'
)
