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


def get_model() -> str:
    """Modelo efetivo: override salvo ou o default do servidor (env)."""
    return (_load().get("model") or "").strip() or settings.openai_model


def set_model(model: str) -> None:
    data = _load()
    data["model"] = (model or "").strip()
    _save(data)


def get_prompt(agent_id: str, default: str) -> str:
    """System prompt efetivo de um agente: override salvo ou o default do código."""
    val = (_load().get("prompts") or {}).get(agent_id)
    return val if isinstance(val, str) and val.strip() else default


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
