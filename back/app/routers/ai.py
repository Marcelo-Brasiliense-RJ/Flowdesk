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
from ..services.treinador import TREINADOR_PROMPT
from .chat import SYSTEM_PROMPT
from .orchestrator import PLANEJADOR_PROMPT, CONSTRUTOR_PROMPT, NOMEADOR_PROMPT, CLASSIFICADOR_PROMPT
from .repair import _REPAIR_INSTR

router = APIRouter(prefix="/api/ai", tags=["ai"])

# Modelos realmente utilizáveis pela chave configurada (confirmados em
# client.models.list()). Curadoria enxuta da série GPT-5, do econômico ao topo.
# Todos são de raciocínio: o roteamento para a Responses API fica em ai_call, para
# que qualquer um deles funcione em todos os fluxos (chat, wizard, reparo, etc.).
MODEL_CATALOG = [
    {"value": "gpt-5-nano", "provider": "OpenAI", "note": "Econômico"},
    {"value": "gpt-5-mini", "provider": "OpenAI", "note": "Rápido"},
    {"value": "gpt-5", "provider": "OpenAI", "note": "Equilibrado"},
    {"value": "gpt-5.5", "provider": "OpenAI", "note": "Mais capaz"},
    {"value": "gpt-5.5-pro", "provider": "OpenAI", "note": "Raciocínio"},
    {"value": "gpt-5.3-codex", "provider": "OpenAI", "note": "Geração de código"},
]

# Estado real de aplicação no pipeline (após a Fase 2, o motor de orquestração
# lê prompt/modelo/temperatura do grafo e roda os agentes encadeados).
APPLIED = {"assistant_prompt": True, "shared_model": True, "orchestration": True}

# Agentes-semente, a equipe pretendida (espelha as funções reais, com papéis
# mais completos). Ligações: Assistente orquestra todos.
_AGENTS = [
    {"id": "assistente", "name": "Assistente (Smart Chat)", "role": "Recebe o pedido e orquestra",
     "level": 1, "parent": None, "temp": "padrão",
     "tools": ["Recebe a mensagem", "Roteia", "Streaming", "Contexto do projeto"],
     "desc": "Porta de entrada: recebe a mensagem do usuário em linguagem natural, entende a intenção e orquestra os demais agentes (planejar, construir, nomear/descrever, reparar, classificar). Fala com o usuário sem jargão técnico.",
     "where": "chat.py · _generate / SYSTEM_PROMPT"},
    {"id": "planejador", "name": "Planejador", "role": "Planeja e entrevista (grill-me)",
     "level": 2, "parent": "assistente", "temp": "0.2",
     "tools": ["Entrevista", "Árvore de decisão", "Plano de execução"],
     "desc": "Antes de construir, escreve, planeja e questiona: faz a entrevista de descoberta no estilo grill-me, uma pergunta por vez, resolvendo cada ramo da árvore de decisão (fontes, colunas, regra, saída, gatilho, erros). Só libera o Construtor quando o plano está sem ambiguidades.",
     "where": "orchestrator.py · run_planejador"},
    {"id": "construtor", "name": "Construtor", "role": "Especialista em Python, escreve os scripts",
     "level": 2, "parent": "assistente", "temp": "0.2",
     "tools": ["Python", "pandas", "create_file", "create_stage", "require_env"],
     "desc": "Especialista em Python: a partir do plano, escreve TODOS os scripts da automação, completos e funcionais (sem placeholder/TODO), com o SDK do FlowDesk e pandas, e monta as ações (create_file/create_stage) e os require_env quando há integração externa.",
     "where": "orchestrator.py · run_construtor"},
    {"id": "nomeador", "name": "Nomeador", "role": "Nomeia e descreve a automação",
     "level": 2, "parent": "assistente", "temp": "0.3",
     "tools": ["Título curto", "Descrição amigável", "Cards do wizard"],
     "desc": "Dá um nome curto e claro à automação e escreve a descrição amigável que aparece nos cards do wizard ('o que esta automação faz'), em linguagem simples para o usuário não técnico.",
     "where": "orchestrator.py · run_nomeador"},
    {"id": "reparador", "name": "Reparador / QA", "role": "Corrige erros de execução",
     "level": 2, "parent": "assistente", "temp": "0.1",
     "tools": ["Diagnóstico", "Correção de código", "Reteste"],
     "desc": "Quando um teste falha, lê o erro e o código, diagnostica a causa em linguagem simples e propõe uma correção concreta para reteste, sem expor stack trace cru. Tenta de novo até passar ou esgotar as tentativas.",
     "where": "repair.py · repair_propose"},
    {"id": "classificador", "name": "Classificador contábil", "role": "Sugere contas (De/Para)",
     "level": 2, "parent": "assistente", "temp": "0.0",
     "tools": ["Plano de contas", "Lotes", "Regras De/Para"],
     "desc": "Especialista contábil: para cada grupo de histórico do extrato, sugere a contrapartida escolhendo estritamente um código do plano de contas analítico (receita p/ crédito, despesa p/ débito), em lotes pequenos para não inventar categorias.",
     "where": "classify.py · classificar_grupos"},
    {"id": "treinador", "name": "Treinador", "role": "Aprende do validado e melhora os agentes",
     "level": 3, "parent": None, "temp": "0.2",
     "tools": ["Colhe exemplos", "Anonimiza", "Destila prompt", "Propõe melhorias"],
     "desc": "Camada de auto-evolução: colhe automações publicadas e validadas, guarda o plano anonimizado e o código como exemplos, e propõe melhorias de prompt para os agentes de build. Nunca roda no fluxo de execução/publish, só no ciclo de treino.",
     "where": "services/treinador.py"},
]

# Prompts-semente por agente. O board mostra os prompts REAIS que o orquestrador
# usa em runtime (fonte única em orchestrator.py); Assistente e Reparador usam as
# constantes reais dos seus fluxos (SYSTEM_PROMPT e _REPAIR_INSTR).
_DEFAULT_PROMPTS = {
    "assistente": SYSTEM_PROMPT,
    "planejador": PLANEJADOR_PROMPT,
    "construtor": CONSTRUTOR_PROMPT,
    "nomeador": NOMEADOR_PROMPT,
    "reparador": _REPAIR_INSTR,
    "classificador": CLASSIFICADOR_PROMPT,
    "treinador": TREINADOR_PROMPT,
}


# Cores por agente embutido (apenas visual).
_COLORS = {
    "assistente": ["#155489", "#18b1a8"],
    "construtor": ["#0f8f88", "#2dd4c4"],
    "planejador": ["#1f6fb2", "#4a80c2"],
    "reparador": ["#7c3aed", "#a78bfa"],
    "classificador": ["#c98a00", "#e0b15a"],
    "nomeador": ["#155489", "#4a80c2"],
    "treinador": ["#0d9488", "#5eead4"],
}

# Layout do canvas do builder (px). Pipeline honesto + camada meta (Treinador).
_CANVAS_W = 760

# Posições fixas por agente (x, y). Pipeline no meio, apoio nas laterais,
# Treinador na base como camada de aprendizado.
_POS = {
    "assistente":   (380, 60),
    "planejador":   (150, 210),
    "construtor":   (380, 210),
    "nomeador":     (610, 210),
    "classificador":(210, 330),
    "reparador":    (560, 330),
    "treinador":    (380, 450),
}

# Fluxo real (arestas visuais). kind="learn" => tracejada (camada meta).
_FLOW_EDGES = [
    ("assistente", "planejador"),     # roteia a intenção "nova" para a entrevista
    ("planejador", "construtor"),     # plano selado -> código
    ("construtor", "nomeador"),       # código -> nome/descrição
    ("classificador", "construtor"),  # enriquece o plano contábil antes do build
    ("reparador", "construtor"),      # laço de volta: conserta o código na falha
]
_LEARN_EDGES = [
    ("treinador", "planejador"),
    ("treinador", "construtor"),
    ("treinador", "nomeador"),
    ("treinador", "reparador"),
    ("treinador", "classificador"),
]


def _default_graph() -> dict:
    """Grafo-semente: os 7 agentes reais num pipeline honesto (Assistente roteia →
    Planejador → Construtor → Nomeador), com Classificador e Reparador como apoio e
    o Treinador como camada meta (arestas tracejadas 'learn' para todos os de build).
    É o que aparece antes de o usuário customizar pelo builder."""
    model = ai_config.get_model()
    agents = []
    for a in _AGENTS:
        c1, c2 = _COLORS.get(a["id"], ["#155489", "#18b1a8"])
        x, y = _POS.get(a["id"], (_CANVAS_W // 2, 240))
        agents.append({
            "id": a["id"], "name": a["name"], "role": a["role"], "level": a["level"],
            "desc": a["desc"], "tools": list(a["tools"]), "temp": a["temp"], "where": a["where"],
            "model": model, "prompt": _DEFAULT_PROMPTS.get(a["id"]),
            "x": x, "y": y, "c1": c1, "c2": c2,
            "builtin": True, "kind": a["id"],
            "editablePrompt": True,
        })
    known = {a["id"] for a in _AGENTS}
    edges = []
    for i, (frm, to) in enumerate(_FLOW_EDGES):
        if frm in known and to in known:
            edges.append({"id": f"f{i}", "from": frm, "to": to})
    for i, (frm, to) in enumerate(_LEARN_EDGES):
        if frm in known and to in known:
            edges.append({"id": f"l{i}", "from": frm, "to": to, "kind": "learn"})
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
        "applied": APPLIED,
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
