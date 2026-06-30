"""Agentes: espelho real das funções de IA do FlowDesk + configuração aplicada.

Reflete os agentes que existem DE FATO no backend (não uma hierarquia fictícia):
um Assistente (Smart Chat) que orquestra a conversa e funções especializadas que
os fluxos acionam. Editável de verdade (persistido + aplicado): o system prompt do
Assistente e o modelo compartilhado. Os demais agentes têm prompt definido no
código (dinâmico) e aparecem como somente leitura, com modelo/temperatura reais.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user
from ..config import settings
from ..models import User
from ..services import ai_config
from .chat import SYSTEM_PROMPT
from .repair import _REPAIR_INSTR

router = APIRouter(prefix="/api/ai", tags=["ai"])

# Modelos realmente utilizáveis pelo provedor configurado (cliente OpenAI-
# compatível). Não listamos modelos de outros provedores que o backend não chama.
MODEL_CATALOG = [
    {"value": "gpt-4o-mini", "provider": "OpenAI", "note": "Econômico"},
    {"value": "gpt-4o", "provider": "OpenAI", "note": "Equilibrado"},
    {"value": "gpt-4.1", "provider": "OpenAI", "note": "Mais capaz"},
    {"value": "gpt-4.1-mini", "provider": "OpenAI", "note": "Rápido"},
    {"value": "o3-mini", "provider": "OpenAI", "note": "Raciocínio"},
]

# Agentes reais — cada um é uma função de IA distinta no código.
_AGENTS = [
    {"id": "assistente", "name": "Assistente (Smart Chat)", "role": "Conversa e descoberta",
     "level": 1, "parent": None, "temp": "padrão",
     "tools": ["Entrevista", "Streaming", "Contexto do projeto"],
     "desc": "Conversa com o usuário, faz a entrevista de descoberta (perguntas) e conduz a criação da automação.",
     "where": "chat.py · _generate / SYSTEM_PROMPT"},
    {"id": "construtor", "name": "Construtor", "role": "Gera código e ações",
     "level": 2, "parent": "assistente", "temp": "0.2",
     "tools": ["create_file", "create_stage", "require_env"],
     "desc": "A partir do pedido, gera o script Python completo e as ações (criar arquivo/etapa).",
     "where": "chat.py · _generate_build"},
    {"id": "descritor", "name": "Descritor", "role": "Descreve a automação",
     "level": 2, "parent": "assistente", "temp": "0.2",
     "tools": ["Resumo em linguagem simples"],
     "desc": "Escreve a explicação 'o que esta automação faz' exibida no Pedido.",
     "where": "wizard.py · _describe_automation"},
    {"id": "reparador", "name": "Reparador / QA", "role": "Corrige erros de execução",
     "level": 2, "parent": "assistente", "temp": "0.1",
     "tools": ["Diagnóstico", "Correção de código"],
     "desc": "Diagnostica erros de execução do script e propõe uma correção para reteste.",
     "where": "repair.py · repair_propose"},
    {"id": "classificador", "name": "Classificador contábil", "role": "Sugere contas (De/Para)",
     "level": 2, "parent": "assistente", "temp": "0.0",
     "tools": ["Plano de contas", "Lotes"],
     "desc": "Sugere a conta contábil de cada grupo de histórico do extrato (contrapartida).",
     "where": "classify.py · classificar_grupos"},
    {"id": "nomeador", "name": "Nomeador", "role": "Nomeia a automação",
     "level": 2, "parent": "assistente", "temp": "0.3",
     "tools": ["Título curto"],
     "desc": "Gera um nome curto e claro para a automação criada pelo Chat.",
     "where": "projects.py · auto_name"},
]

# Prompts reais que conseguimos expor como texto (constantes limpas do código).
_DEFAULT_PROMPTS = {"assistente": SYSTEM_PROMPT, "reparador": _REPAIR_INSTR}
# Só o Assistente é editável+aplicado com segurança (system prompt limpo). Os
# demais têm prompt dinâmico embutido no código (alterar quebraria o contrato).
_EDITABLE = {"assistente"}


class ModelBody(BaseModel):
    model: str


class PromptBody(BaseModel):
    prompt: str


def _require_admin(user: User) -> None:
    is_admin = user.role == "admin" or (user.email or "").lower() in settings.admin_email_set
    if not is_admin:
        raise HTTPException(status_code=403, detail="Apenas administradores podem alterar a configuração de IA.")


@router.get("/agents")
def list_agents(user: User = Depends(get_current_user)):
    model = ai_config.get_model()
    agents = []
    for a in _AGENTS:
        default_prompt = _DEFAULT_PROMPTS.get(a["id"])
        editable = a["id"] in _EDITABLE
        prompt = ai_config.get_prompt(a["id"], default_prompt) if default_prompt is not None else None
        agents.append({
            **a,
            "model": model,
            "editable": editable,
            "prompt": prompt,
            "prompt_overridden": bool(editable and default_prompt is not None and prompt != default_prompt),
        })
    edges = [{"from": a["parent"], "to": a["id"]} for a in _AGENTS if a["parent"]]
    return {
        "agents": agents,
        "edges": edges,
        "model": model,
        "model_default": settings.openai_model,
        "model_catalog": MODEL_CATALOG,
        "ai_enabled": settings.ai_enabled,
    }


@router.put("/model")
def update_model(body: ModelBody, user: User = Depends(get_current_user)):
    _require_admin(user)
    ai_config.set_model(body.model)
    return {"model": ai_config.get_model()}


@router.put("/agents/{agent_id}/prompt")
def update_agent_prompt(agent_id: str, body: PromptBody, user: User = Depends(get_current_user)):
    _require_admin(user)
    if agent_id not in _EDITABLE:
        raise HTTPException(
            status_code=400,
            detail="Este agente tem o prompt definido no código (somente leitura).",
        )
    ai_config.set_prompt(agent_id, body.prompt)
    return {"ok": True}


@router.delete("/agents/{agent_id}/prompt")
def reset_agent_prompt(agent_id: str, user: User = Depends(get_current_user)):
    _require_admin(user)
    ai_config.clear_prompt(agent_id)
    return {"ok": True}
