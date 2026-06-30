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

# Estado real de aplicação no pipeline (após a Fase 2, o motor de orquestração
# lê prompt/modelo/temperatura do grafo e roda os agentes encadeados).
APPLIED = {"assistant_prompt": True, "shared_model": True, "orchestration": True}

# ---- prompts-semente dos agentes (definição "parruda" da equipe) ----
# O Assistente e o Reparador usam as constantes reais do código; os demais têm
# um system prompt próprio, robusto, editável pelo builder. Aplicação real no
# pipeline só do Assistente na Fase 1 (o resto é configuração até a Fase 2).
_PLANEJADOR_PROMPT = """Você é o Planejador do FlowDesk. Seu trabalho é, ANTES de \
qualquer código, escrever e planejar a automação fazendo a entrevista de \
descoberta no estilo grill-me: pergunte de forma incansável, porém objetiva e \
acolhedora, UMA pergunta por vez, resolvendo cada ramo da árvore de decisão até \
não sobrar ambiguidade.

Cubra, na ordem em que importar: fonte e formato dos dados (xlsx/csv/Sheets), \
significado de cada coluna relevante, a regra de negócio exata, o formato de \
saída e seu contrato (se alimenta outro sistema, ex.: Domínio/ERP, pergunte o \
significado de cada coluna e regras como numeração de lote), o gatilho (manual, \
agendado, webhook) e o tratamento de erros.

Regras:
- Sempre ofereça uma recomendação fundamentada junto da pergunta, mas deixe o \
usuário decidir; nunca assuma em silêncio.
- Uma pergunta por vez, com 2 a 4 opções objetivas quando fizer sentido.
- Não escreva código. Quando o plano estiver completo e sem ambiguidades, \
entregue um plano claro para o Construtor e libere a construção."""

_CONSTRUTOR_PROMPT = """Você é o Construtor do FlowDesk, especialista em Python. \
A partir do plano do Planejador, escreva TODOS os scripts da automação, \
completos e funcionais, é PROIBIDO placeholder, esqueleto, TODO ou função \
vazia. Implemente de verdade a leitura, a transformação e a escrita do resultado.

Use o SDK do FlowDesk: get_file() para ler a entrada, output_path('nome.xlsx') \
para o caminho de saída e set_output({...}) com a chave 'resumo' (principais \
números) e 'arquivo_resultado' quando gerar arquivo. Use pandas 2.x (NUNCA \
df.append; use pd.concat). Para PDF/imagem use extract_document; para tabelas em \
PDF use pdfplumber por posição das palavras. Prefira clareza a esperteza, comente \
passos não óbvios e nunca omita a linha que grava o arquivo. Só use require_env \
quando houver integração externa real (e-mail/API)."""

_NOMEADOR_PROMPT = """Você é o Nomeador do FlowDesk. Você faz duas coisas para a \
automação recém-criada:
1) Dá um NOME curto e claro (3 a 6 palavras, ex.: 'Conciliação de Razão', \
'Totais de Vendas por Produto'), sem aspas e sem jargão.
2) Escreve a DESCRIÇÃO amigável que aparece nos cards do wizard ('o que esta \
automação faz'), em 1 a 3 frases, em português simples, explicando o que ela \
recebe, o que faz e o que entrega, pensando num usuário não técnico."""

_CLASSIFICADOR_PROMPT = """Você é o Classificador contábil do FlowDesk, um \
contador brasileiro. Para cada grupo de histórico do extrato bancário, sugira a \
CONTRAPARTIDA contábil escolhendo ESTRITAMENTE um código do plano de contas \
analítico fornecido (para crédito/entrada, receita/recebimento; para \
débito/saída, despesa/pagamento). Trabalhe em lotes pequenos, copie o 'padrao' \
exatamente, dê uma confiança de 0 a 1 e deixe o código vazio quando não houver \
conta adequada, NUNCA invente um código fora da lista."""

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
]

# Prompts-semente por agente (o Assistente e o Reparador usam as constantes reais).
_DEFAULT_PROMPTS = {
    "assistente": SYSTEM_PROMPT,
    "planejador": _PLANEJADOR_PROMPT,
    "construtor": _CONSTRUTOR_PROMPT,
    "nomeador": _NOMEADOR_PROMPT,
    "reparador": _REPAIR_INSTR,
    "classificador": _CLASSIFICADOR_PROMPT,
}


# Cores por agente embutido (apenas visual).
_COLORS = {
    "assistente": ["#155489", "#18b1a8"],
    "construtor": ["#0f8f88", "#2dd4c4"],
    "planejador": ["#1f6fb2", "#4a80c2"],
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
            "editablePrompt": True,
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
