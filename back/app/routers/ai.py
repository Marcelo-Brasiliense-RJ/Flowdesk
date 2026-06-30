"""Agentes: espelho real das funções de IA do FlowDesk + configuração aplicada.

Reflete os agentes que existem DE FATO no backend (não uma hierarquia fictícia):
um Assistente (Smart Chat) que orquestra a conversa e funções especializadas que
os fluxos acionam. Editável de verdade (persistido + aplicado): o system prompt do
Assistente e o modelo compartilhado. Os demais agentes têm prompt definido no
código (dinâmico) e aparecem como somente leitura, com modelo/temperatura reais.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

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


# Cores por agente embutido (apenas visual).
_COLORS = {
    "assistente": ["#155489", "#18b1a8"],
    "construtor": ["#0f8f88", "#2dd4c4"],
    "descritor": ["#1f6fb2", "#4a80c2"],
    "reparador": ["#7c3aed", "#a78bfa"],
    "classificador": ["#c98a00", "#e0b15a"],
    "nomeador": ["#155489", "#4a80c2"],
}

# Layout do canvas do builder (px).
_CANVAS_W = 760


def _default_graph() -> dict:
    """Grafo-semente: os 6 agentes reais, com posições e cores, e as ligações
    de fluxo reais (Assistente → especialistas). É o que aparece antes de o
    usuário customizar pelo builder."""
    model = ai_config.get_model()
    specialists = [a for a in _AGENTS if a["level"] != 1]
    n = len(specialists)
    left, right = 110, _CANVAS_W - 110
    agents = []
    for a in _AGENTS:
        c1, c2 = _COLORS.get(a["id"], ["#155489", "#18b1a8"])
        if a["level"] == 1:
            x, y = _CANVAS_W // 2, 70
        else:
            i = specialists.index(a)
            x = _CANVAS_W // 2 if n <= 1 else round(left + (right - left) * i / (n - 1))
            y = 320
        agents.append({
            "id": a["id"], "name": a["name"], "role": a["role"], "level": a["level"],
            "desc": a["desc"], "tools": list(a["tools"]), "temp": a["temp"], "where": a["where"],
            "model": model, "prompt": _DEFAULT_PROMPTS.get(a["id"]),
            "x": x, "y": y, "c1": c1, "c2": c2,
            "builtin": True, "kind": a["id"],
            "editablePrompt": a["id"] in _EDITABLE,
        })
    edges = []
    for i, a in enumerate(x for x in _AGENTS if x["parent"]):
        edges.append({"id": f"e{i}", "from": a["parent"], "to": a["id"]})
    return {"agents": agents, "edges": edges}


def _require_admin(user: User) -> None:
    is_admin = user.role == "admin" or (user.email or "").lower() in settings.admin_email_set
    if not is_admin:
        raise HTTPException(status_code=403, detail="Apenas administradores podem alterar a configuração de IA.")


@router.get("/agents")
def list_agents(user: User = Depends(get_current_user)):
    graph = ai_config.get_graph() or _default_graph()
    return {
        "agents": graph.get("agents", []),
        "edges": graph.get("edges", []),
        "model": ai_config.get_model(),
        "model_default": settings.openai_model,
        "model_catalog": MODEL_CATALOG,
        "ai_enabled": settings.ai_enabled,
        "custom": ai_config.get_graph() is not None,
        # Fase 1: aplicado de verdade no pipeline fixo. Agentes/ligações extras
        # ficam salvos como configuração até o motor de orquestração (Fase 2).
        "applied": {"assistant_prompt": True, "shared_model": True, "orchestration": False},
    }


@router.put("/graph")
def save_graph(body: dict, user: User = Depends(get_current_user)):
    _require_admin(user)
    agents = body.get("agents")
    if not isinstance(agents, list) or not agents:
        raise HTTPException(status_code=400, detail="Grafo inválido: 'agents' é obrigatório.")
    edges = body.get("edges")
    ai_config.set_graph({"agents": agents, "edges": edges if isinstance(edges, list) else []})
    return {"ok": True}


@router.delete("/graph")
def reset_graph(user: User = Depends(get_current_user)):
    """Restaura o grafo-semente (os 6 agentes reais)."""
    _require_admin(user)
    ai_config.clear_graph()
    return {"ok": True}
