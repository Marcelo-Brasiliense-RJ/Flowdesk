"""Orquestrador determinístico dos agentes (Fase 2).

FSM por projeto (Project.phase) + roteador de intenção. Cada agente é uma chamada
de IA separada, com prompt/modelo/temperatura lidos do grafo do builder (ai_config).
"""
from __future__ import annotations

from ..config import settings
from ..services import ai_config


def _client():
    from openai import OpenAI

    return OpenAI(api_key=settings.openai_api_key)


def call_agent(
    agent_id: str,
    default_prompt: str,
    messages: list[dict],
    *,
    json_mode: bool = False,
) -> str:
    """Chama um agente lendo prompt/modelo/temperatura do grafo (ai_config).

    Retorna o texto da resposta. Com settings.ai_enabled desligado, retorna ""
    (cada call-site decide o comportamento de fallback/mock)."""
    if not settings.ai_enabled:
        return ""
    prompt = ai_config.get_prompt(agent_id, default_prompt)
    kw = {
        "model": ai_config.get_agent_model(agent_id),
        "temperature": ai_config.get_temp(agent_id),
        "messages": [{"role": "system", "content": prompt}, *messages],
    }
    if json_mode:
        kw["response_format"] = {"type": "json_object"}
    resp = _client().chat.completions.create(**kw)
    return resp.choices[0].message.content or ""
