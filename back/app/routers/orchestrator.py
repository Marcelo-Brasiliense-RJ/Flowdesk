"""Orquestrador determinístico dos agentes (Fase 2).

FSM por projeto (Project.phase) + roteador de intenção. Cada agente é uma chamada
de IA separada, com prompt/modelo/temperatura lidos do grafo do builder (ai_config).
"""
from __future__ import annotations

import json
import re

from ..config import settings
from ..services import ai_config
from ..services.plan_schema import Plan, plan_is_complete, plan_missing_fields


ROUTER_PROMPT = (
    "Você é a porta de entrada do FlowDesk. Classifique a intenção da última "
    'mensagem do usuário em JSON {"intent": "nova|ajuste|duvida"}: '
    "nova = criar uma automação nova; ajuste = mudar uma automação existente; "
    "duvida = pergunta ou conversa que não pede mudança. Responda só o JSON."
)
_EDIT_VERB = re.compile(
    r"\b(mud\w*|alter\w*|ajust\w*|troc\w*|corrig\w*|renome\w*|adicion\w*|remov\w*)\b", re.I
)
_QUESTION = re.compile(r"\?\s*$|^\s*(o que|como|por ?que|qual|quando|quem)\b", re.I)


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


def route_intent(last_user: str, has_workflow: bool) -> str:
    """Roteador determinístico: nova automação, ajuste de existente, ou dúvida.

    Heurística primeiro; IA só quando há workflow e a intenção é ambígua."""
    import json
    from .chat import _is_build_intent  # import local: evita ciclo com chat.py

    c = (last_user or "").strip().lower()
    is_question = bool(_QUESTION.search(c))
    if not has_workflow:
        return "duvida" if (is_question and not _is_build_intent(c)) else "nova"
    if _EDIT_VERB.search(c):
        return "ajuste"
    if is_question:
        return "duvida"
    if not settings.ai_enabled:
        return "ajuste"
    raw = call_agent("assistente", ROUTER_PROMPT, [{"role": "user", "content": last_user}], json_mode=True)
    try:
        intent = (json.loads(raw or "{}").get("intent") or "").strip()
    except Exception:
        intent = ""
    return intent if intent in ("nova", "ajuste", "duvida") else "ajuste"


PLANEJADOR_PROMPT = (
    "Você é o Planejador do FlowDesk. ANTES de qualquer código, conduza a "
    "entrevista de descoberta no estilo grill-me: uma pergunta por vez, objetiva e "
    "acolhedora, resolvendo cada ramo da árvore de decisão (fonte e formato dos "
    "dados, significado das colunas, regra de negócio, contrato de saída, gatilho, "
    "tratamento de erros). Sempre ofereça uma recomendação, mas deixe o usuário "
    "decidir; nunca assuma em silêncio. Se a tarefa for contábil ou fiscal, faça "
    "também as perguntas de perfil (regime, plano de contas, ERP destino). "
    "Responda SOMENTE em JSON: "
    '{"questions": [{"id": "...", "label": "...", "options": ["..."], "recommended": "..."}], '
    '"plan": {<campos do plano preenchidos ATÉ AQUI: fonte{formato,descricao,colunas[]}, '
    'regra_negocio, saida{formato,contrato,colunas[],destino_sistema}, gatilho, '
    'tratamento_erros, contabil, notas>}, "contabil": <bool>, '
    '"perfil_perguntas": [{"id": "...", "label": "...", "options": ["..."]}]}. '
    "Devolva o plano COMPLETO acumulado a cada turno (não só o delta). Não escreva código."
)


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base or {})
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def run_planejador(messages: list[dict], plan: dict) -> dict:
    """Conduz a entrevista e acumula o plano. Devolve perguntas, plano mesclado e
    validado, campos críticos faltando, flag contábil e perguntas de perfil."""
    raw = call_agent("planejador", PLANEJADOR_PROMPT, messages, json_mode=True)
    try:
        data = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        data = {}
    merged = _deep_merge(plan or {}, data.get("plan") or {})
    try:
        validated = Plan(**merged).model_dump()
    except Exception:
        validated = merged
    missing = plan_missing_fields(Plan(**validated)) if isinstance(validated, dict) else []
    return {
        "questions": data.get("questions") or [],
        "plan": validated,
        "missing": missing,
        "contabil": bool(data.get("contabil")),
        "profile_questions": data.get("perfil_perguntas") or [],
    }


def next_phase(current: str, intent: str, plan: Plan, user_confirmed: bool) -> str:
    """FSM pura de fases. As transições building, naming, done são feitas
    pelos call-sites (Construtor, Nomeador), não aqui."""
    if intent == "duvida":
        return current
    if intent == "ajuste":
        return "building"
    if intent == "nova" and current in ("", "done", "naming"):
        return "planning"
    if current == "planning":
        return "building" if (plan_is_complete(plan) and user_confirmed) else "planning"
    return current
