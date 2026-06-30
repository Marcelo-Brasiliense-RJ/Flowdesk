"""Configuração de IA (override de modelo e de system prompts).

Persistida em arquivo JSON em STORAGE_DIR para funcionar igual em SQLite e
Postgres, sem migração de schema. O FlowDesk opera como uma única organização
(IRKO), então a config é global; pode ser estendida por chave se um dia for
multi-organização.

Princípio de integridade: estes valores são REALMENTE aplicados pelo backend
(ver wiring em chat.py / repair.py / classify.py / wizard.py / projects.py).
Nada aqui é cosmético.
"""
from __future__ import annotations

import json
import threading

from ..config import STORAGE_DIR, settings

_PATH = STORAGE_DIR / "ai_config.json"
_lock = threading.Lock()


def _load() -> dict:
    try:
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    with _lock:
        _PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _graph_agent(agent_id: str) -> dict | None:
    """Agente do grafo salvo (builder), se existir."""
    g = _load().get("graph")
    if not isinstance(g, dict):
        return None
    for a in g.get("agents") or []:
        if isinstance(a, dict) and a.get("id") == agent_id:
            return a
    return None


def get_model() -> str:
    """Modelo efetivo (compartilhado pelo pipeline fixo).

    Fonte, em ordem: modelo do nó 'assistente' no grafo do builder → override
    simples salvo → default do servidor (env).
    """
    a = _graph_agent("assistente")
    if a and isinstance(a.get("model"), str) and a["model"].strip():
        return a["model"].strip()
    return (_load().get("model") or "").strip() or settings.openai_model


def set_model(model: str) -> None:
    data = _load()
    data["model"] = (model or "").strip()
    _save(data)


def get_prompt(agent_id: str, default: str) -> str:
    """System prompt efetivo de um agente.

    Fonte, em ordem: prompt do agente no grafo do builder → override simples
    salvo → default do código.
    """
    a = _graph_agent(agent_id)
    if a and isinstance(a.get("prompt"), str) and a["prompt"].strip():
        return a["prompt"]
    val = (_load().get("prompts") or {}).get(agent_id)
    return val if isinstance(val, str) and val.strip() else default


def get_graph() -> dict | None:
    """Grafo de agentes salvo pelo builder (None se ainda não há override)."""
    g = _load().get("graph")
    return g if isinstance(g, dict) else None


def set_graph(graph: dict) -> None:
    data = _load()
    data["graph"] = graph
    _save(data)


def clear_graph() -> None:
    data = _load()
    data.pop("graph", None)
    _save(data)


def set_prompt(agent_id: str, prompt: str) -> None:
    data = _load()
    prompts = dict(data.get("prompts") or {})
    prompts[agent_id] = prompt
    data["prompts"] = prompts
    _save(data)


def clear_prompt(agent_id: str) -> None:
    data = _load()
    prompts = dict(data.get("prompts") or {})
    prompts.pop(agent_id, None)
    data["prompts"] = prompts
    _save(data)


def get_temp(agent_id: str, default: float = 0.2) -> float:
    """Temperatura efetiva do agente (lida do grafo; 'padrão'/inválido -> default)."""
    a = _graph_agent(agent_id)
    raw = (a or {}).get("temp")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def get_agent_model(agent_id: str) -> str:
    """Modelo efetivo do agente: modelo do nó no grafo -> modelo compartilhado."""
    a = _graph_agent(agent_id)
    if a and isinstance(a.get("model"), str) and a["model"].strip():
        return a["model"].strip()
    return get_model()
