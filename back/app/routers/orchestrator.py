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
    "Você é o Planejador do FlowDesk. Seu trabalho é montar um PLANO de automação "
    "conversando com o usuário, uma pergunta por vez, e só então liberar a "
    "construção. Seja decidido, não burocrático.\n"
    "LEIA o contexto dos arquivos anexados (colunas e amostras). NUNCA pergunte o que "
    "já está visível ali: se as colunas aparecem, registre-as no plano (fonte.colunas) "
    "e siga em frente. Só pergunte o que a informação disponível NÃO resolve: uma "
    "regra de negócio ambígua, uma tolerância, o formato de saída quando não óbvio. "
    "Uma pergunta por vez, com 2 a 4 opções e uma recomendação. Pergunte apenas o "
    "essencial (idealmente 0 a 2 perguntas quando o pedido e os arquivos já são "
    "claros). Só faça perguntas de perfil contábil (regime, plano de contas, ERP "
    "destino) quando a tarefa REALMENTE for contábil/fiscal e isso mudar o resultado.\n"
    "Preencha os campos críticos do plano assim que possível: fonte.formato, "
    "regra_negocio, saida.formato, gatilho (assuma 'manual' se o usuário não indicar "
    "outro). Quando esses quatro estiverem preenchidos, PARE a descoberta e faça UMA "
    "única pergunta de confirmação, com id 'confirmar', label resumindo o que a "
    "automação vai fazer e perguntando se pode montar, options ['Sim, pode montar', "
    "'Quero ajustar algo'].\n"
    "Responda SOMENTE em JSON: "
    '{"message": "1 a 2 frases curtas e amigáveis narrando o que você entendeu e o '
    'próximo passo (sempre preencha, nunca vazio)", '
    '"questions": [{"id": "...", "label": "...", "options": ["..."], "recommended": "..."}], '
    '"plan": {fonte:{formato,descricao,colunas:[{nome,significado}]}, regra_negocio, '
    "saida:{formato,contrato,colunas:[],destino_sistema}, gatilho, tratamento_erros, "
    'contabil, notas}, "contabil": <bool>, '
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


def run_planejador(messages: list[dict], plan: dict, context: str = "") -> dict:
    """Conduz a entrevista e acumula o plano. Recebe o contexto dos arquivos/projeto
    (`context`) para que o Planejador leia as colunas reais em vez de perguntá-las.
    Devolve mensagem, perguntas, plano mesclado e validado, campos críticos faltando,
    flag contábil e perguntas de perfil."""
    msgs = ([{"role": "system", "content": context}] if context else []) + list(messages)
    raw = call_agent("planejador", PLANEJADOR_PROMPT, msgs, json_mode=True)
    try:
        data = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        data = {}
    merged = _deep_merge(plan or {}, data.get("plan") or {})
    # saída do modelo é fronteira de confiança: se vier com tipo errado num campo,
    # Plan(**merged) lança. Instanciamos uma vez e caímos para um Plan vazio em vez
    # de propagar a exceção (o modelo devolve o plano completo a cada turno).
    try:
        plan_obj = Plan(**merged)
    except Exception:
        plan_obj = Plan()
    validated = plan_obj.model_dump()
    missing = plan_missing_fields(plan_obj)
    return {
        "message": (data.get("message") or "").strip(),
        "questions": data.get("questions") or [],
        "plan": validated,
        "missing": missing,
        "contabil": bool(data.get("contabil")),
        "profile_questions": data.get("perfil_perguntas") or [],
    }


CONSTRUTOR_PROMPT = (
    "Você é o Construtor do FlowDesk, especialista em Python. A partir do PLANO "
    "selado (não da conversa), escreva TODOS os scripts da automação, completos e "
    "funcionais. É PROIBIDO placeholder, esqueleto, TODO ou função vazia: implemente "
    "de verdade a leitura, a transformação e a escrita do resultado. Use o SDK do "
    "FlowDesk (get_file() para a entrada, output_path('nome.xlsx') para a saída, "
    "set_output({...}) com a chave 'resumo' e 'arquivo_resultado' quando gerar "
    "arquivo). Use pandas 2.x (NUNCA df.append; use pd.concat) e NUNCA omita a linha "
    "que grava o arquivo. Para PDF/imagem use extract_document; para tabelas em PDF "
    "use pdfplumber pela posição das palavras. Só use require_env quando o plano "
    "indicar integração externa real (e-mail/API). Quando o plano for contábil, "
    "respeite o perfil contábil fornecido (plano de contas, regime, layout do ERP "
    "destino). Responda SOMENTE em JSON: {\"message\": \"explicação curta e amigável, "
    "em português simples, do que a automação faz\", \"actions\": [{\"kind\": "
    "\"create_file|edit_file|create_stage|require_env\", ...}]}. Inclua SEMPRE ao "
    "menos um create_file com o script Python completo."
)


def run_construtor(plan: dict, profile: dict, project_context: str) -> dict:
    """Gera o código a partir do PLANO selado (e do perfil contábil quando aplicável).
    Devolve {message, actions} no formato que chat._apply_action consome."""
    blocks = [
        "PLANO SELADO (contrato a implementar):\n"
        + json.dumps(plan or {}, ensure_ascii=False, indent=2)
    ]
    if (plan or {}).get("contabil") and profile:
        blocks.append(
            "PERFIL CONTÁBIL DO PROJETO:\n" + json.dumps(profile, ensure_ascii=False, indent=2)
        )
    if project_context:
        blocks.append(project_context)
    messages = [{"role": "user", "content": "\n\n".join(blocks)}]
    raw = call_agent("construtor", CONSTRUTOR_PROMPT, messages, json_mode=True)
    try:
        data = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        data = {}
    return {"message": data.get("message") or "", "actions": data.get("actions") or []}


NOMEADOR_PROMPT = (
    "Você é o Nomeador do FlowDesk. A partir do plano e do código da automação "
    "recém-criada, faça duas coisas: 1) um NOME curto e claro, de 3 a 6 palavras, "
    "estilo título, sem aspas e sem jargão (ex.: 'Conciliação de Razão', 'Totais de "
    "Vendas por Produto'); 2) uma DESCRIÇÃO amigável em 1 a 3 frases, em português "
    "simples, dizendo o que a automação recebe, o que faz e o que entrega, pensando "
    "num usuário não técnico. Responda SOMENTE em JSON: "
    '{"name": "...", "description": "..."}.'
)

_PLACEHOLDER_DESC = "Criado pelo Chat"


def run_nomeador(plan: dict, code: str) -> dict:
    """Gera nome curto e descrição amigável da automação. A gravação no projeto
    (respeitando nome definido pelo usuário) é feita na fiação, via name_is_placeholder."""
    blocks = [
        "PLANO:\n" + json.dumps(plan or {}, ensure_ascii=False, indent=2),
        "CÓDIGO:\n" + (code or "")[:4000],
    ]
    raw = call_agent("nomeador", NOMEADOR_PROMPT, [{"role": "user", "content": "\n\n".join(blocks)}], json_mode=True)
    try:
        data = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        data = {}
    return {"name": (data.get("name") or "").strip(), "description": (data.get("description") or "").strip()}


def name_is_placeholder(name: str, description: str) -> bool:
    """True quando é seguro o Nomeador sobrescrever nome/descrição (nunca sobrescreve
    um nome definido de propósito pelo usuário)."""
    return (description or "").strip() == _PLACEHOLDER_DESC or len((name or "").strip()) < 3


CLASSIFICADOR_PROMPT = (
    "Você é o cérebro contábil e fiscal do FlowDesk, um contador brasileiro. Dado o "
    "plano de uma automação contábil e o perfil contábil do projeto (regime, plano de "
    "contas, ERP destino), enriqueça o plano com o contexto que o Construtor precisa "
    "respeitar: layout do ERP destino (ex.: regras de importação do Domínio como "
    "numeração de lote), formato de contas e histórico, e regras fiscais aplicáveis. "
    "Proponha atualizações de perfil quando descobrir algo, mas NUNCA confirme o "
    "regime sozinho. Responda SOMENTE em JSON: {\"plan_patch\": {<campos do plano a "
    "mesclar>}, \"perfil_updates\": {<campos do perfil a propor>}, \"avisos_fiscais\": "
    "[\"...\"]}."
)


def enrich_accounting(plan: dict, profile: dict) -> dict:
    """Cérebro contábil em tempo de design: enriquece o plano e propõe atualizações
    de perfil quando a tarefa é contábil. Nunca auto-confirma o perfil."""
    if not (plan or {}).get("contabil"):
        return {"plan": plan, "profile": profile, "avisos": []}
    blocks = [
        "PLANO:\n" + json.dumps(plan or {}, ensure_ascii=False, indent=2),
        "PERFIL CONTÁBIL ATUAL:\n" + json.dumps(profile or {}, ensure_ascii=False, indent=2),
    ]
    raw = call_agent("classificador", CLASSIFICADOR_PROMPT,
                     [{"role": "user", "content": "\n\n".join(blocks)}], json_mode=True)
    try:
        data = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        data = {}
    perfil_updates = dict(data.get("perfil_updates") or {})
    perfil_updates.pop("confirmado", None)   # o modelo nunca auto-confirma
    return {
        "plan": _deep_merge(plan or {}, data.get("plan_patch") or {}),
        "profile": _deep_merge(profile or {}, perfil_updates),
        "avisos": data.get("avisos_fiscais") or [],
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


def _build_turn(plan: dict, profile: dict, project_context: str) -> dict:
    """Roda o Construtor (com enriquecimento contábil quando aplicável) e o Nomeador,
    devolvendo o turno de construção. Reusado pelo build explícito e pela convergência
    da entrevista."""
    plan2 = plan or {}
    profile2 = profile or {}
    if plan2.get("contabil"):
        en = enrich_accounting(plan2, profile2)
        plan2, profile2 = en["plan"], en["profile"]
    cons = run_construtor(plan2, profile2, project_context)
    actions = cons.get("actions") or []
    code = next(
        (a.get("content", "") for a in actions
         if a.get("kind") in ("create_file", "edit_file") and (a.get("path") or "").endswith(".py")),
        "",
    )
    nm = run_nomeador(plan2, code)
    return {
        "mode": "building", "text": cons.get("message") or "", "questions": [],
        "actions": actions, "phase": "done", "plan": plan2, "profile": profile2,
        "suggested_name": nm.get("name") or "", "suggested_desc": nm.get("description") or "",
        "plan_for_review": plan2,
    }


def orchestrate_turn(*, phase: str, plan: dict, profile: dict, intent: str,
                     user_confirmed: bool, history: list[dict], project_context: str) -> dict:
    """Dispatch determinístico de um turno do chat. Decide a próxima fase e roda o
    agente da vez. mode='answer' significa: responda normalmente, sem orquestrar."""
    try:
        plan_obj = Plan(**(plan or {}))
    except Exception:
        plan_obj = Plan()
    new_phase = next_phase(phase or "", intent, plan_obj, user_confirmed)

    if intent == "duvida":
        return {"mode": "answer", "phase": phase or "", "plan": plan or {}, "profile": profile or {}}

    if new_phase == "planning":
        pj = run_planejador(history, plan or {}, project_context)
        questions = list(pj.get("questions") or []) + list(pj.get("profile_questions") or [])
        pj_plan = pj.get("plan") or {}
        # sela quando o usuário confirma E o plano (recém-atualizado neste turno) já
        # está completo, mesmo que a completude só tenha ocorrido agora. Sem isso, a
        # entrevista entraria em loop esperando um estado persistido que nunca chega.
        if user_confirmed and not (pj.get("missing") or []):
            return _build_turn(pj_plan, profile, project_context)
        return {
            "mode": "planning", "text": pj.get("message") or "", "questions": questions,
            "actions": [], "phase": "planning", "plan": pj_plan, "profile": profile or {},
            "missing": pj.get("missing") or [],
        }

    if new_phase == "building":
        return _build_turn(plan or {}, profile, project_context)

    return {"mode": "answer", "phase": phase or "", "plan": plan or {}, "profile": profile or {}}
