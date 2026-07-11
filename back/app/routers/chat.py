"""Smart Chat (AI panel), OpenAI streaming + approve/reject pending actions.

Protocol: the model streams natural-language text, then may append a fenced
block:

    ```flowdesk-actions
    {"questions": [...], "actions": [...]}
    ```

`questions` become clarifying radio/input prompts shown in the chat.
`actions` become PendingAction rows the user must Approve before they apply.
"""
from __future__ import annotations

import ast
import json
import queue
import re
import threading

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import SessionLocal, get_db
from ..models import (
    ChatMessage,
    Edge,
    EnvVar,
    PendingAction,
    Project,
    SourceFile,
    Stage,
    User,
)
from ..schemas import ChatMessageOut, ChatSendRequest, PendingActionOut
from ..services import ai_call, ai_config, storage
from ..services.ai_guard import SECURITY_PREAMBLE, guarded, wrap_untrusted
from .projects import get_project, slugify, unsafe_source_path

router = APIRouter(prefix="/api", tags=["chat"])

CONTEXT_WINDOW = 128_000
ACTIONS_RE = re.compile(r"```flowdesk-actions\s*(\{.*?\})\s*```", re.DOTALL)

SYSTEM_PROMPT = """Você é o assistente do FlowDesk, uma plataforma low-code de \
automação com IA. O usuário descreve em linguagem natural o que quer automatizar e \
você ajuda a desenhar o fluxo (forms, scripts) e a escrever o código Python.

PROCESSO OBRIGATÓRIO, ENTREVISTA (DISCOVERY ANTES DE CONSTRUIR):
1. Antes de criar qualquer coisa, levante as perguntas de esclarecimento NECESSÁRIAS \
(de 1 a 5) e devolva TODAS no campo "questions" do bloco flowdesk-actions. A interface \
mostra UMA pergunta por vez ao usuário (com indicador de progresso), então cada \
pergunta deve ser independente e objetiva. Use um tom AMIGÁVEL e acolhedor, em \
linguagem simples e sem jargão técnico, como se conversasse com a pessoa; quando \
ajudar, explique em poucas palavras por que a pergunta importa. NÃO escreva código \
nem inclua "actions" enquanto estiver perguntando.
2. Cada pergunta deve ter "id" único e estável (ex: "fonte", "saida", "gatilho"), de \
2 a 4 opções objetivas e, quando fizer sentido, "recommended" com o texto exato da \
opção recomendada.
3. Pergunte só o que muda a solução, percorrendo a árvore de decisão: fontes/colunas \
dos dados, regra de negócio, formato de saída, gatilho (manual, agendado, webhook), \
tratamento de erros.
4. Antes do bloco, escreva 1 frase curta de contexto. Faça as perguntas SEMPRE pelo \
bloco (campo "questions"), nunca em texto corrido.
5. Ao receber as respostas (mensagem que começa com "Respostas da entrevista") ou se o \
usuário disser "pode montar/criar agora", PARE de perguntar e EMITA IMEDIATAMENTE, na \
MESMA resposta, o bloco flowdesk-actions com as "actions" (create_file com o código \
pronto, create_stage se necessário). NUNCA responda apenas dizendo que "vai criar o \
código agora" sem incluir o bloco de actions, isso deixa o fluxo sem terminar.

PROFUNDIDADE DA ENTREVISTA (REGRA DE OURO, NA DÚVIDA, PERGUNTE):
- Desça até o nível de CONTRATO do resultado: se a saída alimenta outro sistema \
(ex: importação do Domínio, SAP, ERP), pergunte o significado de cada coluna que \
não for óbvia, formatos de data/valor, e regras como numeração de lote. Exemplo \
real: "No Domínio, como funciona a coluna Inicia Lote?", a resposta muda o código \
(lá, o lote reinicia em 1 a cada troca de data).
- SEMPRE ofereça sua recomendação fundamentada junto da pergunta (campo \
"recommended"), mas deixe o usuário decidir. Nunca assuma silenciosamente.
- NARRE o que você fez a cada passo, com números concretos: "Li o extrato: 564 \
lançamentos, 01/04 a 30/04" / "Li o plano de contas: 1.387 contas analíticas". \
O usuário precisa VER o progresso, não confiar às cegas.

CLASSIFICAÇÃO CONTÁBIL E LINHA DO TEMPO (recursos prontos do SDK):
- progress(etapa, detalhe): linha do tempo visível ao usuário durante a execução. \
Emita em TODA etapa relevante de scripts longos (ler arquivo, aplicar regras, gerar \
saída), em linguagem simples.
- get_table("regras_classificacao"): regras De/Para aprendidas do projeto \
(lista de {padrao, conta_codigo}); a regra especial "_CONTA_BANCO" guarda a conta \
do banco. Use em automações de classificação contábil.
- read_table(caminho): lê planilha xlsx/xls/csv com tolerância a xls legado (Domínio).
- Revisão humana de classificação (2 passes): no pass 1 devolva \
set_output({"_classificacao_review": {periodo_detectado, conta_banco, grupos, \
contas, total_lancamentos}}) SEM gerar arquivo; a interface mostra a tela de revisão \
com semáforo. O pass 2 chega com "_classificacao_confirmada" (mapa padrao->conta, \
"IGNORAR" pula o grupo), "_conta_banco" e "_periodo" ({inicio, fim} dd/mm/aaaa) no \
get_input(); aí filtre o período e gere o arquivo. Siga o contrato do modelo \
"extrato-dominio" da galeria.
- EXTRATO BANCÁRIO -> DOMÍNIO: NÃO escreva um classificador do zero. Parta do modelo \
"extrato-dominio" da galeria: read_table para o plano, parse POSICIONAL do PDF via \
pdfplumber (separando colunas por x0/x1, nunca fatiando doc["text"] por espaços), \
get_table("regras_classificacao") + revisão em 2 passes, e as COLUNAS EXATAS do Domínio \
(Data, Cód. Conta Debito, Cód. Conta Credito, Valor, Cód. Histórico, Complemento \
Histórico, Inicia Lote, Código Matriz/Filial, ...). O PLANO DE CONTAS não é tabela \
De/Para: tem cabeçalho DESLOCADO (leia com header=None e localize a linha de cabeçalho) \
e colunas Código/T/Classificação/Nome/Grau, NUNCA uma coluna "Descrição". Jamais \
classifique por substring do nome da conta no histórico.

REGRAS DE CÓDIGO:
- O código deve ser COMPLETO E FUNCIONAL na primeira entrega. É PROIBIDO devolver \
esqueleto, placeholder ou TODO (nada de `dados = []  # adicione sua lógica`, `pass`, \
funções vazias ou comentários do tipo "aqui você implementa"). Implemente de verdade a \
leitura, a transformação e a escrita do resultado, com base na estrutura real do arquivo.
- NUNCA comente nem omita a linha que grava a saída (`df.to_excel(...)` / `ExcelWriter`); \
se a automação gera um arquivo, o código TEM que gravá-lo de fato e só então chamar set_output.
- Scripts Python usam o SDK: `from flowdesk_sdk import get_file, set_output, \
output_path, log, read_table` (get_file() para ler o arquivo de entrada; read_table \
para planilhas).
- `set_output` SEMPRE recebe um DICT, nunca uma string. Ex.: \
`set_output({"arquivo_resultado": str(out), "resumo": {...}})`.
- pandas é 2.x: NÃO use `df.append(...)` (foi removido), use `pd.concat([...])`. \
Para escrever Excel com várias abas use `pd.ExcelWriter(output_path("nome.xlsx"), \
engine="openpyxl")`.
- Use SEMPRE o contexto do projeto e dos arquivos anexados (colunas reais, stages \
existentes). Não invente nomes de colunas nem recrie stages que já existem.
- Responda em português, de forma concisa. Sempre mostre código dentro de blocos \
```python ... ```.

ENTRADA E SAÍDA DE ARQUIVOS (a PLATAFORMA cuida disso):
- Para LER o arquivo de entrada use `get_file()` do SDK (retorna o caminho do arquivo \
enviado no Form, sem depender do nome do campo). Para planilhas (xlsx/xls/csv) use \
SEMPRE `read_table(get_file())` do SDK, NUNCA `pd.read_excel`/`pd.read_csv` direto: \
read_table converte o .xls legado do Domínio (via Excel COM) e evita os erros \
"Expected BOF record" e "utf-8 codec can't decode". Ex.: `df = read_table(get_file())`. \
Para um 2º arquivo: `get_file(1)`. NUNCA peça ao usuário o caminho do arquivo de entrada \
e NUNCA invente uma chave fixa em get_input().
- Os arquivos de SAÍDA devem ser gravados com `output_path("nome.xlsx")` do SDK; o \
download é feito AUTOMATICAMENTE pela plataforma. NÃO existe "caminho local" para salvar, \
NUNCA peça PATH_OUTPUT, diretório, pasta ou caminho de arquivo.

PDF E IMAGEM (OCR com validação):
- Para PDF (editável OU escaneado) ou imagem, use \
`from flowdesk_sdk import extract_document` e `doc = extract_document(get_file())`. Ele \
detecta sozinho: PDF com texto extrai direto; PDF escaneado/imagem usa OCR local. NÃO use \
pd.read_excel num PDF nem tente OCR manual.
- IMPORTANTE para TABELAS/EXTRATOS em PDF (colunas de data, histórico, crédito, débito, \
saldo): o texto puro de `doc["text"]` PERDE o alinhamento das colunas e mistura os valores. \
Nesse caso, em vez de fatiar o texto linear, use `pdfplumber` direto \
(`import pdfplumber; pdf = pdfplumber.open(get_file())`) e separe as colunas pelas POSIÇÕES \
X das palavras (`page.extract_words()` e o campo `x0`/`x1` de cada palavra). É a forma \
confiável de saber qual número é crédito, débito ou saldo.
- `doc` traz: `doc["text"]` (texto), `doc["mean_confidence"]` (0..1 ou None), \
`doc["needs_review"]` (True quando o OCR teve baixa confiança) e `doc["low_confidence"]` \
(linhas duvidosas). SEMPRE que a entrada passar por OCR, inclua no set_output a chave \
`_ocr_review` = {"text": doc["text"], "mean_confidence": doc["mean_confidence"], \
"needs_review": doc["needs_review"], "low_confidence": [l["text"] for l in doc["low_confidence"]]}. \
A plataforma usa isso para mostrar a tela de revisão humana (a pessoa confere os trechos \
destacados antes de confiar no resultado).

DEPENDÊNCIAS DE CONFIGURAÇÃO E SEGREDOS:
- Use `require_env` APENAS quando o usuário pedir EXPLICITAMENTE uma integração externa \
(enviar e-mail, chamar uma API, gravar no Google Sheets, etc.). Se a tarefa só processa \
um arquivo e gera uma planilha de saída, NÃO há segredos, NÃO declare NENHUM require_env \
(nada de SMTP/EMAIL nesse caso).
- Quando houver integração: NUNCA fixe credenciais no código; leia com \
`os.environ["NOME"]` e declare uma action "require_env" com {"key","description","example"} \
(ex.: SMTP_HOST, SMTP_USER, SMTP_PASSWORD, EMAIL_DESTINO para e-mail; API_TOKEN para API). \
Avise no texto que essas variáveis precisam ser preenchidas para testar.

FORMATO DO BLOCO (na entrevista, só "questions"; na criação, só "actions"):
```flowdesk-actions
{"actions": [{"kind": "create_file", "title": "Criar processar.py", \
"path": "processar.py", "content": "from flowdesk_sdk import get_file, set_output, \
output_path\\nimport pandas as pd\\n# ... usa get_file() e output_path() ..."}]}
```

Tipos de ação: create_file, edit_file (path, content), create_stage \
(stage_type form|script, name), install_package (package), \
require_env (key, description, example).

REGRAS DE CÓDIGO PARA TAREFAS CONTÁBEIS/FISCAIS (siga à risca):
- Saída de arquivo: SEMPRE set_output({"arquivo_resultado": str(output_path("nome.xlsx")), ...}). Nunca passe o nome nu.
- Aging / dias de atraso: dias = (data_base - vencimento).days. dias <= 0 é "A vencer". Faixas com limite superior INCLUSIVO e sem sobreposição: "1-30" (1<=dias<=30), "31-60" (31<=dias<=60), "61-90" (61<=dias<=90), "90+" (dias>90). Pergunte a data-base se não vier. Para "por cliente E faixa", use pivot_table(index=cliente, columns=faixa, values=valor, aggfunc="sum").
- Conciliação débito x crédito que zera: pareie por VALOR ABSOLUTO (abs(valor)), tratando crédito negativo. Pareamento 1:1, marcando cada lançamento já usado; com valores repetidos, ordene de forma estável. Mantenha TODOS os registros (Conciliados + Não Conciliados = carregados) e gere resumo com as contagens que fecham.
- Conciliação por valor + data com tolerância: case mesmo valor com diferença de datas <= tolerância (em dias); > tolerância NÃO casa. Casamento 1:1 (não reutilize a mesma linha). Inclua na saída a coluna "dif_dias". Remova não casados por ÍNDICE da linha, nunca por valor de data.
- Antes de declarar sucesso, valide invariantes: somas por categoria fecham com o total carregado; não há divisão por zero; colunas esperadas existem (erro claro em PT-BR se faltar)."""


def _project_context(db: Session, project_id: int) -> str:
    """Always feed the model the current project state so it asks relevant
    questions and does not recreate what already exists."""
    project = db.get(Project, project_id)
    stages = db.query(Stage).filter(Stage.project_id == project_id).all()
    edges = db.query(Edge).filter(Edge.project_id == project_id).all()
    files = db.query(SourceFile).filter(SourceFile.project_id == project_id).all()

    lines = [f"Estado atual do projeto \"{project.name if project else project_id}\":"]
    if stages:
        by_id = {s.id: s for s in stages}
        lines.append(
            "Stages: " + "; ".join(f"{s.name} [{s.type}]" for s in stages)
        )
        if edges:
            flow = " | ".join(
                f"{by_id[e.source_stage_id].name} -> {by_id[e.target_stage_id].name}"
                f" ({e.variable_label})"
                for e in edges
                if e.source_stage_id in by_id and e.target_stage_id in by_id
            )
            lines.append("Conexões: " + flow)
    else:
        lines.append("Nenhum stage criado ainda (projeto vazio).")
    if files:
        lines.append("Arquivos de código: " + ", ".join(f.path for f in files))
    return "\n".join(lines)


def _format_sources(files) -> str:
    """Formata o código atual do projeto para o contexto do Construtor (ajustes).
    Pula diretórios e arquivos vazios; trunca conteúdos longos."""
    parts = []
    for f in files:
        if getattr(f, "is_dir", False):
            continue
        content = f.content or ""
        if not content.strip():
            continue
        parts.append(f"### {f.path}\n{content[:4000]}")
    if not parts:
        return ""
    return (
        "CÓDIGO ATUAL DO PROJETO (para AJUSTAR, edite estes arquivos com edit_file; "
        "não recrie do zero):\n\n" + "\n\n".join(parts)
    )


def _source_context(db: Session, project_id: int) -> str:
    files = db.query(SourceFile).filter(SourceFile.project_id == project_id).all()
    return _format_sources(files)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _attachment_context(project_id: int, paths: list[str]) -> str:
    """Read attached spreadsheets/CSVs and summarize them for the model so its
    questions are grounded in the real data instead of guessing."""
    if not paths:
        return ""
    import pandas as pd

    root = storage.project_root(project_id)
    blocks: list[str] = []
    for rel in paths[:5]:
        try:
            target = storage.safe_join(root, rel)
        except ValueError:
            continue
        if not target.exists() or not target.is_file():
            continue
        suffix = target.suffix.lower()
        try:
            if suffix in (".xlsx", ".xls"):
                xls = pd.ExcelFile(target)
                parts = []
                for sheet in xls.sheet_names[:5]:
                    df = pd.read_excel(target, sheet_name=sheet)
                    sample = df.head(5).to_string(index=False)
                    parts.append(
                        f"  Aba '{sheet}': {len(df)} linha(s), colunas {list(df.columns)}\n"
                        f"  Amostra:\n{sample}"
                    )
                blocks.append(f"Arquivo {rel} (Excel):\n" + "\n".join(parts))
            elif suffix == ".csv":
                df = pd.read_csv(target)
                blocks.append(
                    f"Arquivo {rel} (CSV): {len(df)} linha(s), colunas {list(df.columns)}\n"
                    f"Amostra:\n{df.head(5).to_string(index=False)}"
                )
            else:
                blocks.append(
                    f"Arquivo {rel}: tipo {suffix or 'desconhecido'} (conteúdo não inspecionado)"
                )
        except Exception as exc:  # never break the chat on a bad file
            blocks.append(f"Arquivo {rel}: não foi possível ler ({exc})")
    if not blocks:
        return ""
    body = (
        "O usuário anexou arquivos ao projeto. Abaixo estão os dados REAIS deles. "
        "Baseie suas perguntas e seu código nessas colunas e amostras; NÃO pergunte "
        "informações que já estão visíveis aqui (como nomes de colunas):\n\n"
        + "\n\n".join(blocks)
    )
    # Conteúdo de arquivo enviado pelo usuário é entrada não confiável: uma célula de
    # planilha ou linha de PDF pode conter uma tentativa de prompt injection. Marca
    # como dado externo para os agentes tratarem como dado, nunca como instrução.
    return wrap_untrusted(body, label="arquivos anexados")


def _context_usage(db: Session, project_id: int) -> dict:
    total = (
        db.query(ChatMessage)
        .filter(ChatMessage.project_id == project_id)
        .with_entities(ChatMessage.tokens)
        .all()
    )
    used = sum(t[0] or 0 for t in total)
    return {"used_tokens": used, "context_window": CONTEXT_WINDOW,
            "percent": round(min(100.0, used / CONTEXT_WINDOW * 100), 2)}


_BUILD_VERB = r"(monta|montar|monte|cria|criar|crie|constr[oóu]i?r?|finaliz\w*|implementa\w*|gera|gerar|gere)"


def _is_build_intent(content: str) -> bool:
    c = content.strip().lower()
    if c.startswith("respostas da entrevista"):
        return True
    # comando explícito: verbo de construção no INÍCIO da mensagem...
    if re.match(rf"\s*{_BUILD_VERB}\b", c):
        return True
    # ...ou verbo de construção acompanhado de "agora"
    if re.search(rf"\b{_BUILD_VERB}\b", c) and re.search(r"\bagora\b", c):
        return True
    # ponytail: heurística com teto conhecido. Se algum fluxo legítimo de "só
    # construir" regredir, afrouxar aqui é o ponto único de ajuste.
    return False


@router.get("/projects/{project_id}/chat", response_model=list[ChatMessageOut])
def list_chat(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.project_id == project_id)
        .order_by(ChatMessage.created_at)
        .all()
    )


@router.delete("/projects/{project_id}/chat")
def clear_chat(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    db.query(ChatMessage).filter(ChatMessage.project_id == project_id).delete()
    db.query(PendingAction).filter(PendingAction.project_id == project_id).delete()
    db.commit()
    return {"ok": True}


@router.get("/projects/{project_id}/chat/context")
def context(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    return {**_context_usage(db, project_id), "ai_enabled": settings.ai_enabled}


@router.post("/projects/{project_id}/chat/stream")
def chat_stream(
    project_id: int,
    body: ChatSendRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project(db, project_id, user)

    user_msg = ChatMessage(
        project_id=project_id, role="user", content=body.content,
        tokens=_estimate_tokens(body.content),
    )
    db.add(user_msg)
    db.commit()

    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.project_id == project_id)
        .order_by(ChatMessage.created_at)
        .all()
    )

    # estado de orquestração do projeto (Fase 2)
    project = db.get(Project, project_id)
    stages = db.query(Stage).filter(Stage.project_id == project_id).all()
    has_workflow = any(s.type in ("script", "agent") for s in stages)
    cur_phase = (project.phase if project else "") or ""
    cur_plan = (project.plan if project else {}) or {}
    cur_profile = (project.accounting_profile if project else {}) or {}

    # orquestra só com IA ligada; sem IA, cai no caminho mock (_generate).
    # A orquestração roda DENTRO do stream (thread), emitindo progresso por fase:
    # antes ela bloqueava a resposta inteira (30-90s) sem nenhum feedback ao usuário.
    turn = {"mode": "answer"}
    _run_orchestration = None
    if settings.ai_enabled:
        from .orchestrator import orchestrate_turn, route_intent

        intent = route_intent(body.content, has_workflow)
        user_confirmed = _is_build_intent(body.content)
        _orch_ctx = _project_context(db, project_id)
        # colunas/amostras reais dos arquivos anexados: o Planejador precisa disso
        # para ler as colunas em vez de perguntá-las (senão a entrevista fica genérica).
        _att_ctx = _attachment_context(project_id, body.attachments)
        if _att_ctx:
            _orch_ctx = _orch_ctx + "\n\n" + _att_ctx
        _src_ctx = _source_context(db, project_id)
        if _src_ctx:
            _orch_ctx = _orch_ctx + "\n\n" + _src_ctx
        _orch_history = [{"role": m.role, "content": m.content} for m in history[-20:]]

        def _run_orchestration(progress):
            return orchestrate_turn(
                phase=cur_phase, plan=cur_plan, profile=cur_profile, intent=intent,
                user_confirmed=user_confirmed, history=_orch_history,
                project_context=_orch_ctx, progress=progress,
            )

    # mensagens do caminho "answer" (dúvida / sem IA): igual ao fluxo anterior
    messages = [
        {"role": "system", "content": guarded(ai_config.get_prompt("assistente", SYSTEM_PROMPT))},
        {"role": "system", "content": _project_context(db, project_id)},
    ]
    ctx_block = _attachment_context(project_id, body.attachments)
    if ctx_block:
        # dado não confiável (já delimitado) vai como mensagem do usuário, não do sistema
        messages.append({"role": "user", "content": ctx_block})
    messages += [{"role": m.role, "content": m.content} for m in history[-20:]]

    def event_stream():
        nonlocal turn
        # roda a orquestração numa thread e transmite o progresso por fase enquanto ela
        # trabalha (Planejando / Escrevendo o código / Finalizando). Sem isto o usuário
        # esperava a construção inteira com o indicador "Analisando" congelado.
        if _run_orchestration is not None:
            q: "queue.Queue[str | None]" = queue.Queue()
            box: dict = {}

            def _work():
                try:
                    box["turn"] = _run_orchestration(lambda label: q.put(label))
                except Exception as exc:  # degrada para resposta normal em vez de 500
                    box["error"] = exc
                finally:
                    q.put(None)

            th = threading.Thread(target=_work, daemon=True)
            th.start()
            while True:
                label = q.get()
                if label is None:
                    break
                yield f"data: {json.dumps({'type': 'phase', 'label': label})}\n\n"
            th.join()
            if "turn" in box:
                turn = box["turn"]
            # se orquestração falhou, turn continua {"mode": "answer"} e cai no mock/IA

        if turn.get("mode") == "answer":
            full_text = ""
            for chunk in _generate(messages, body.content):
                full_text += chunk
                yield f"data: {json.dumps({'type': 'token', 'text': chunk})}\n\n"
            clean_text, questions, actions = _parse_actions(full_text)
            for qq in questions:
                if not qq.get("label"):
                    qq["label"] = qq.get("question") or qq.get("text") or ""
            if not questions and not actions:
                clean_text, questions = _parse_prose_questions(clean_text)
            questions = questions[:6]
            new_phase = None
            plan_for_review = None
        else:
            clean_text = turn.get("text") or ""
            questions = (turn.get("questions") or [])[:6]
            actions = turn.get("actions") or []
            new_phase = turn.get("phase")
            plan_for_review = turn.get("plan_for_review")
            full_text = clean_text
            for word in re.findall(r"\S+\s*", clean_text):
                yield f"data: {json.dumps({'type': 'token', 'text': word})}\n\n"

        # filtros de ação (iguais ao fluxo anterior)
        actions = [a for a in actions if not _is_pathlike_env(a)]
        convo = body.content + " " + " ".join(m.content for m in history)
        if not _INTEGRATION_INTENT.search(convo):
            actions = [a for a in actions if a.get("kind") != "require_env"]
        if questions:
            actions = []

        s = SessionLocal()
        try:
            if turn.get("mode") != "answer":
                from .orchestrator import name_is_placeholder

                proj = s.get(Project, project_id)
                if proj is not None:
                    if new_phase:
                        proj.phase = new_phase
                    proj.plan = turn.get("plan") or {}
                    proj.accounting_profile = turn.get("profile") or {}
                    sug_name = (turn.get("suggested_name") or "").strip()
                    sug_desc = (turn.get("suggested_desc") or "").strip()
                    if sug_name and name_is_placeholder(proj.name, proj.description):
                        proj.name = sug_name[:80]
                        proj.description = sug_desc[:240]
                        # a URL foi congelada do nome inicial (o prompt cru, virando um
                        # slug enorme). Enquanto não publicou, alinha ao nome curto.
                        if proj.status != "live":
                            from .projects import unique_subdomain

                            proj.subdomain = unique_subdomain(s, sug_name, exclude_id=proj.id)
                    s.commit()

            assistant = ChatMessage(
                project_id=project_id, role="assistant", content=clean_text,
                meta={"questions": questions, "phase": new_phase, "plan": plan_for_review},
                tokens=_estimate_tokens(full_text),
            )
            s.add(assistant)
            s.commit()
            created = []
            for a in actions:
                pa = PendingAction(
                    project_id=project_id,
                    kind=a.get("kind", "edit_file"),
                    title=a.get("title", a.get("kind", "Ação")),
                    payload=a,
                )
                s.add(pa)
                s.commit()
                s.refresh(pa)
                created.append(PendingActionOut.model_validate(pa).model_dump(mode="json"))
            usage = _context_usage(s, project_id)
        finally:
            s.close()

        yield "data: " + json.dumps(
            {"type": "done", "questions": questions, "actions": created,
             "context": usage, "phase": new_phase, "plan": plan_for_review}
        ) + "\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _generate_build(messages: list[dict]):
    """Build turn: força JSON estruturado {message, actions} (sem depender de bloco
    solto no texto). Garante que o fluxo termina com ações concretas."""
    # preâmbulo de segurança à frente de tudo (independe do que o chamador montou)
    messages = [{"role": "system", "content": SECURITY_PREAMBLE}] + list(messages)
    instr = {
        "role": "system",
        "content": (
            "Responda SOMENTE em JSON válido: "
            '{"message": "explicação curta e amigável, em português simples e sem jargão '
            'técnico, do que a automação vai fazer (1 a 2 frases, pensando num usuário não '
            'técnico)", "project_name": "nome curto e claro para a automação (3 a 6 '
            'palavras, ex: Total de Vendas por Produto)", "actions": [...]}. '
            "Tipos de action: create_file {kind,title,path,content}, "
            "create_stage {kind,title,stage_type,name}, "
            "require_env {kind,title,key,description,example}. "
            "Inclua SEMPRE pelo menos um create_file com o script Python completo, "
            "usando o SDK (get_file() para ler entrada, output_path() e set_output(DICT) "
            "para saída), pandas 2.x (NÃO use df.append; use pd.concat). "
            "O código deve ser COMPLETO E FUNCIONAL: PROIBIDO placeholder, esqueleto ou TODO "
            "(nada de 'dados = []  # adicione sua lógica', pass ou funções vazias), e NUNCA "
            "comente a linha que grava o arquivo (df.to_excel deve rodar de fato). "
            "Para TABELAS/EXTRATOS em PDF (colunas crédito/débito/saldo), o texto puro perde o "
            "alinhamento: use pdfplumber direto (pdfplumber.open(get_file()), page.extract_words()) "
            "e separe as colunas pelas posições x das palavras. "
            "Se a entrada for PDF ou imagem, use `from flowdesk_sdk import extract_document` "
            "e `doc = extract_document(get_file())` (NÃO use pd.read_excel num PDF); quando "
            "doc vier de OCR, inclua no set_output a chave `_ocr_review` = {'text': doc['text'], "
            "'mean_confidence': doc['mean_confidence'], 'needs_review': doc['needs_review'], "
            "'low_confidence': [l['text'] for l in doc['low_confidence']]} para a tela de revisão. "
            "Quando gerar arquivo, grave com output_path('nome.xlsx') e devolva "
            "set_output({'arquivo_resultado': str(caminho), 'resumo': {...números...}}); "
            "inclua SEMPRE a chave 'resumo' com os principais números. "
            "Use chaves simples { } em dicionários Python; NUNCA escreva chaves "
            "duplicadas {{ }} (isso quebra o código). "
            "Não peça caminhos de arquivo. Só use require_env se houver integração "
            "externa real (e-mail/API)."
        ),
    }
    if not settings.ai_enabled:
        return ("Fluxo gerado (modo simulado).", [
            {"kind": "create_file", "title": "Criar processar.py", "path": "processar.py",
             "content": "from flowdesk_sdk import get_file, set_output\nimport pandas as pd\n\n"
                        "df = pd.read_excel(get_file())\nset_output({'linhas': len(df)})\n"}
        ], "")
    try:
        raw = ai_call.complete(
            ai_config.get_model(),
            messages + [instr],
            temperature=0.2,
            json_mode=True,
        )
        data = ai_call.parse_json(raw)
        return (
            data.get("message") or "Fluxo gerado.",
            data.get("actions") or [],
            (data.get("project_name") or "").strip(),
        )
    except Exception as exc:
        return f"[IA indisponível: {exc}]", [], ""


def _generate(messages: list[dict], last_user: str):
    """Yield text chunks. Real OpenAI streaming when configured, else a mock."""
    if settings.ai_enabled:
        try:
            yield from ai_call.stream_text(ai_config.get_model(), messages)
            return
        except Exception as exc:  # fall back to mock on any API error
            yield f"[IA indisponível: {exc}. Usando modo simulado.]\n\n"

    yield from _mock_generate(last_user)


def _mock_generate(last_user: str):
    text = (
        "Entendi seu pedido. Antes de escrever o código, preciso confirmar alguns "
        "pontos sobre a automação.\n\n"
        "Posso preparar um script Python inicial usando o SDK do FlowDesk.\n\n"
        "```flowdesk-actions\n"
        + json.dumps(
            {
                "questions": [
                    {
                        "id": "formato",
                        "label": "Qual o formato dos arquivos de entrada?",
                        "options": ["Excel (.xlsx)", "CSV", "Outro"],
                    }
                ],
                "actions": [
                    {
                        "kind": "create_file",
                        "title": "Criar processar.py",
                        "path": "processar.py",
                        "content": (
                            "from flowdesk_sdk import get_input, set_output, log\n\n"
                            "def main():\n"
                            "    data = get_input()\n"
                            "    log('entrada', data)\n"
                            "    set_output({'ok': True})\n\n"
                            "if __name__ == '__main__':\n    main()\n"
                        ),
                    }
                ],
            },
            ensure_ascii=False,
        )
        + "\n```"
    )
    # stream word-by-word to simulate tokens
    for word in re.findall(r"\S+\s*", text):
        yield word


_PATHLIKE_ENV = re.compile(r"path|caminho|arquiv|file|diret|pasta|sa[ií]da|output", re.I)
# require_env só faz sentido quando a conversa fala de integração externa real
_INTEGRATION_INTENT = re.compile(
    r"e-?mail|smtp|\bapi\b|slack|google\s*sheets|planilha\s*google|webhook|https?://|token|"
    r"credencial|oauth|integra|enviar para|notific|gmail|outlook|sendgrid|mailgun|teams|whatsapp",
    re.I,
)


def _is_pathlike_env(action: dict) -> bool:
    """require_env asking for a file path / output location is invalid, the
    platform handles input (Form) and output (output_path + auto-download)."""
    if action.get("kind") != "require_env":
        return False
    blob = f"{action.get('key', '')} {action.get('description', '')}"
    return bool(_PATHLIKE_ENV.search(blob))


_NUM_RE = re.compile(r"^\s*(\d+)[\.\)]\s*(.+)$")
_BULLET_RE = re.compile(r"^\s*[-*•]\s*(.+)$")


def _parse_prose_questions(text: str):
    """Fallback: if the model wrote the discovery as a numbered prose list with
    bullet options (instead of the structured block), turn it into interactive
    questions. Returns (clean_text_without_the_list, questions)."""
    lines = text.split("\n")
    questions = []
    cur = None
    first_q = None
    for i, line in enumerate(lines):
        m = _NUM_RE.match(line)
        if m:
            if first_q is None:
                first_q = i
            if cur and len(cur["options"]) >= 2:
                questions.append(cur)
            label = re.sub(r"\*\*|`", "", m.group(2)).strip().rstrip(":")
            cur = {"id": f"q{m.group(1)}", "label": label, "options": [], "recommended": None}
            continue
        if cur is not None:
            low = line.lower()
            if "recomendad" in low:
                parts = line.split(":", 1)
                if len(parts) > 1:
                    cur["recommended"] = re.sub(r"\*\*|`", "", parts[1]).strip()
                continue
            b = _BULLET_RE.match(line)
            if b:
                cur["options"].append(re.sub(r"\*\*|`", "", b.group(1)).strip())
    if cur and len(cur["options"]) >= 2:
        questions.append(cur)
    questions = [q for q in questions if len(q["options"]) >= 2][:6]
    if not questions:
        return text, []
    clean = "\n".join(lines[:first_q]).strip() if first_q else ""
    return clean, questions


def _parse_actions(text: str):
    match = ACTIONS_RE.search(text)
    questions, actions = [], []
    if match:
        try:
            data = json.loads(match.group(1))
            questions = data.get("questions", [])
            actions = data.get("actions", [])
        except json.JSONDecodeError:
            pass
    clean = ACTIONS_RE.sub("", text).strip()
    return clean, questions, actions


@router.get("/projects/{project_id}/pending-actions", response_model=list[PendingActionOut])
def list_pending(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    return (
        db.query(PendingAction)
        .filter(PendingAction.project_id == project_id, PendingAction.status == "pending")
        .order_by(PendingAction.created_at)
        .all()
    )


@router.post("/projects/{project_id}/pending-actions/{action_id}/approve")
def approve_action(
    project_id: int, action_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    get_project(db, project_id, user)
    action = db.get(PendingAction, action_id)
    if action is None or action.project_id != project_id:
        raise HTTPException(status_code=404, detail="Ação não encontrada")
    if action.status != "pending":
        return {"ok": True, "status": action.status}
    _apply_action(db, project_id, action)
    # auto-monta um fluxo executável quando o chat gera um script e o projeto
    # ainda não tem workflow (senão o usuário recebe só um .py que não roda).
    workflow_created = False
    if action.kind in ("create_file", "edit_file"):
        p = action.payload or {}
        path = p.get("path", "")
        if path.endswith(".py") and "set_output" in (p.get("content") or ""):
            workflow_created = _ensure_runnable_workflow(db, project_id, path)
            # workflow ja existia: o Form nao e recriado, entao re-sincroniza os campos
            # de arquivo com o script editado (ex.: passou a ler um 2o/3o arquivo).
            if not workflow_created:
                _sync_input_file_fields(db, project_id, path)
    action.status = "approved"
    # mensagem de fechamento: sem isto a conversa "morre" após aprovar (parece
    # travada). Confirma o que foi feito e aponta o próximo passo.
    if action.kind in ("create_file", "edit_file"):
        if workflow_created:
            closing = (
                "**Tudo pronto!** Sua automação foi criada e já está montada em três etapas:\n\n"
                "1. **Entrada**, a pessoa envia o arquivo (a planilha).\n"
                "2. **Processamento**, o sistema lê os dados e gera o resultado que você pediu.\n"
                "3. **Resultado**, a planilha final fica disponível para baixar.\n\n"
                "**Próximo passo:** clique em **Testar agora** (logo abaixo, aqui no chat) para "
                "rodar com um arquivo de exemplo e conferir o resultado, ou em **Abrir no editor** "
                "para ver e ajustar cada etapa. Se algo não ficar como você esperava, é só me dizer "
                "o que mudar."
            )
        else:
            closing = (
                "**Pronto!** Apliquei as alterações no seu projeto. Clique em **Testar agora** "
                "(aqui no chat) para conferir o resultado, ou me diga o que você quer ajustar."
            )
        db.add(
            ChatMessage(
                project_id=project_id, role="assistant", content=closing,
                meta={}, tokens=0,
            )
        )
    db.commit()
    return {"ok": True, "status": "approved", "workflow_created": workflow_created}


@router.post("/projects/{project_id}/pending-actions/{action_id}/reject")
def reject_action(
    project_id: int, action_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    get_project(db, project_id, user)
    action = db.get(PendingAction, action_id)
    if action is None or action.project_id != project_id:
        raise HTTPException(status_code=404, detail="Ação não encontrada")
    action.status = "rejected"
    db.commit()
    return {"ok": True, "status": "rejected"}


def _input_files_from_code(code: str) -> dict[int, str | None]:
    """Analisa o script por AST e devolve {indice_do_arquivo: rotulo_ou_None}. Robusto
    a como o modelo escreve: get_file(0)/get_file() direto (mesmo aninhado em
    pd.read_excel(...)), ou um helper que repassa um parametro a get_file e e chamado
    com indices literais, com ou sem argumentos extras (ex.: ler_arquivo(1, 'razao')).
    O rotulo, quando da, vem do nome da variavel que recebe o arquivo. Regex nao da
    conta da variedade de chamadas; o AST le a aridade real de cada chamada."""
    try:
        tree = ast.parse(code or "")
    except SyntaxError:
        # codigo invalido nao deveria chegar aqui (o script e materializado e roda);
        # degrada para "1 arquivo se ha get_file, senao nenhum".
        return {0: None} if re.search(r"get_file\(", code or "") else {}

    # helpers que repassam um parametro para get_file: nome -> posicao do parametro.
    readers: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            params = [a.arg for a in node.args.args]
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                        and sub.func.id == "get_file" and sub.args
                        and isinstance(sub.args[0], ast.Name) and sub.args[0].id in params):
                    readers[node.name] = params.index(sub.args[0].id)
                    break

    def _arg_int(call: ast.Call, pos: int) -> int | None:
        if 0 <= pos < len(call.args):
            a = call.args[pos]
            if isinstance(a, ast.Constant) and isinstance(a.value, int):
                return a.value
        return None

    files: dict[int, str | None] = {}

    def _record(i: int, label: str | None) -> None:
        if i not in files or (files[i] is None and label):
            files[i] = label

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.label: str | None = None

        def visit_Assign(self, node: ast.Assign) -> None:
            # rotulo herdado da variavel alvo, mesmo com get_file aninhado no valor
            # (ex.: `extrato = pd.read_excel(get_file(0))`).
            prev = self.label
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                self.label = _humanize_var(node.targets[0].id)
            self.visit(node.value)
            self.label = prev

        def visit_Call(self, node: ast.Call) -> None:
            fn = node.func.id if isinstance(node.func, ast.Name) else None
            if fn == "get_file":
                _record(_arg_int(node, 0) or 0, self.label)
            elif fn in readers:
                _record(_arg_int(node, readers[fn]) or 0, self.label)
            self.generic_visit(node)  # desce nos argumentos (get_file aninhado)

    _Visitor().visit(tree)
    return files


def _count_input_files(code: str) -> int:
    """Quantos arquivos de entrada o script usa, para montar N campos de arquivo no
    Form de entrada. Teto de seguranca de 5 para nao explodir com codigo estranho."""
    files = _input_files_from_code(code)
    return min(max(files) + 1, 5) if files else 1


_GENERIC_VARS = {
    "df", "data", "arquivo", "arq", "f", "file", "entrada", "input",
    "x", "tmp", "temp", "path", "caminho", "src", "planilha", "tabela",
}


def _humanize_var(var: str) -> str | None:
    """Nome de variavel -> rotulo humano ('df_extrato' -> 'Extrato'). None quando o
    nome e generico e nao ajuda o usuario (df, data, arquivo...)."""
    v = (var or "").strip().lower()
    for pre in ("df_", "arquivo_", "arq_", "planilha_", "tabela_", "file_"):
        if v.startswith(pre):
            v = v[len(pre):]
            break
    v = v.strip("_")
    if not v or v in _GENERIC_VARS:
        return None
    return v.replace("_", " ").title()


def _file_labels_from_code(code: str, n: int) -> list[str | None]:
    """Rotulo por indice a partir da variavel que recebe cada arquivo no codigo.
    Ex.: `extrato = pd.read_excel(get_file(0))` -> 'Extrato'. O Construtor ja escreve
    variaveis com nome de negocio, entao isso da rotulos uteis sem outra chamada de IA."""
    files = _input_files_from_code(code)
    return [files.get(i) for i in range(n)]


def _input_file_fields(n: int, code: str = "", plan_files: list[dict] | None = None) -> list[dict]:
    """Campos de arquivo do Form. O rotulo vem, na ordem: do papel do plano do
    analyze (plan_files), senao da variavel que recebe get_file(i) no codigo, senao
    'Arquivo N'. Um so campo mantem o nome 'arquivo' (compatibilidade); dois ou mais
    viram 'arquivo1', 'arquivo2', ..., na ordem que get_file(i) espera."""
    plan_files = plan_files or []
    code_labels = _file_labels_from_code(code, n)

    def _label(i: int) -> str | None:
        if i < len(plan_files):
            rot = (plan_files[i].get("label") or plan_files[i].get("role") or "").strip()
            if rot:
                return rot
        return code_labels[i] if i < len(code_labels) else None

    if n <= 1:
        return [{"name": "arquivo", "label": _label(0) or "Arquivo", "type": "file"}]
    return [
        {"name": f"arquivo{i + 1}", "label": _label(i) or f"Arquivo {i + 1}", "type": "file"}
        for i in range(n)
    ]


def _ensure_input_form_for_script(
    db: Session, project_id: int, script_path: str, stages: list
) -> bool:
    """Cria o Form de entrada (com campos de arquivo) para um script que usa get_file
    quando NENHUM Form de entrada existe. Fecha o buraco em que um script avulso ficava
    sem entrada, deixando a automação como 'não recebe entrada' e o teste falhando com
    'arquivo de entrada não foi encontrado'. Devolve True se criou."""
    src = (
        db.query(SourceFile)
        .filter(SourceFile.project_id == project_id, SourceFile.path == script_path)
        .first()
    )
    code = src.content if src else ""
    if not re.search(r"get_file\(", code or ""):
        return False  # script não lê arquivos: não precisa de upload
    has_input = any(
        (s.config or {}).get("mode") == "input" for s in stages if s.type == "form"
    )
    if has_input:
        return False  # já há entrada; _sync_input_file_fields reconcilia os campos
    script = next(
        (s for s in stages if s.type == "script" and s.entry_file == script_path),
        next((s for s in stages if s.type == "script"), None),
    )
    if script is None:
        return False
    used = {s.key for s in stages}
    base, key, n = "entrada", "entrada", 1
    while key in used:
        n += 1
        key = f"{base}-{n}"
    form_in = Stage(
        project_id=project_id, type="form", name="Entrada", key=key,
        config={
            "title": "Enviar arquivo",
            "mode": "input",
            "submit_label": "Executar",
            "fields": _input_file_fields(_count_input_files(code), code),
        },
        pos_x=40, pos_y=120,
    )
    db.add(form_in)
    db.flush()
    db.add(
        Edge(project_id=project_id, source_stage_id=form_in.id,
             target_stage_id=script.id, variable_label="entrada")
    )
    db.flush()
    return True


def _ensure_runnable_workflow(db: Session, project_id: int, script_path: str) -> None:
    """Garante Form(entrada) -> Script -> Form(resultado) para um script gerado,
    quando o projeto ainda não tem nenhum nó executável. Sem isso, o Chat entrega
    só o código e nada roda pela interface. O Form de entrada ganha tantos campos de
    arquivo quantos o script usa (get_file(0), get_file(1), ...)."""
    stages = db.query(Stage).filter(Stage.project_id == project_id).all()
    if any(s.type == "script" for s in stages):
        # já existe workflow; não duplica. Mas garante que um script que LÊ arquivos
        # tenha um Form de entrada: sem ele o teste falha com "arquivo não encontrado"
        # e a automação aparece como "não recebe entrada". Cobre projetos cujo Form de
        # entrada nunca foi criado (ex.: script veio de um create_stage avulso).
        _ensure_input_form_for_script(db, project_id, script_path, stages)
        return False

    src = (
        db.query(SourceFile)
        .filter(SourceFile.project_id == project_id, SourceFile.path == script_path)
        .first()
    )
    code = src.content if src else ""
    fields = _input_file_fields(_count_input_files(code), code)

    used = {s.key for s in stages}

    def uk(base: str) -> str:
        k, n = base, 1
        while k in used:
            n += 1
            k = f"{base}-{n}"
        used.add(k)
        return k

    form_in = Stage(
        project_id=project_id, type="form", name="Entrada", key=uk("entrada"),
        config={
            "title": "Enviar arquivo",
            "mode": "input",
            "submit_label": "Executar",
            "fields": fields,
        },
        pos_x=40, pos_y=120,
    )
    script = Stage(
        project_id=project_id, type="script", name="Processamento", key=uk("processamento"),
        entry_file=script_path, config={}, pos_x=360, pos_y=120,
    )
    form_out = Stage(
        project_id=project_id, type="form", name="Resultado", key=uk("resultado"),
        config={
            "title": "Resultado",
            "mode": "result",
            "summary_key": "resumo",
            "result_file_key": "arquivo_resultado",
        },
        pos_x=680, pos_y=120,
    )
    db.add_all([form_in, script, form_out])
    db.flush()
    db.add_all([
        Edge(project_id=project_id, source_stage_id=form_in.id,
             target_stage_id=script.id, variable_label="entrada"),
        Edge(project_id=project_id, source_stage_id=script.id,
             target_stage_id=form_out.id, variable_label="resultado"),
    ])
    db.flush()
    return True


def _reconciled_input_fields(old_fields: list[dict], code: str) -> list[dict] | None:
    """Novos campos do Form de entrada apos uma edicao de script, ou None se nada muda.
    Preserva os campos que NAO sao de arquivo e so recalcula os type=file a partir do
    codigo (get_file(0), get_file(1), ...). Retorna None quando o script nao le arquivos
    (para nao injetar upload num form de campos de texto) ou quando os campos ja batem."""
    if not re.search(r"get_file\(", code or ""):
        return None
    non_file = [f for f in old_fields if f.get("type") != "file"]
    new_fields = _input_file_fields(_count_input_files(code), code) + non_file
    return new_fields if new_fields != old_fields else None


def _sync_input_file_fields(db: Session, project_id: int, script_path: str) -> bool:
    """Reconcilia os campos de arquivo do Form de entrada com o que o script usa. O Form
    e montado uma unica vez em _ensure_runnable_workflow; sem esta sincronia, editar o
    script para ler mais (ou menos) arquivos deixaria o Form defasado, com campos de
    upload de menos, e testar/publicar com N arquivos ficaria impossivel."""
    form_in = next(
        (s for s in db.query(Stage).filter(Stage.project_id == project_id, Stage.type == "form").all()
         if (s.config or {}).get("mode") == "input"),
        None,
    )
    if form_in is None:
        return False
    src = (
        db.query(SourceFile)
        .filter(SourceFile.project_id == project_id, SourceFile.path == script_path)
        .first()
    )
    new_fields = _reconciled_input_fields(
        list((form_in.config or {}).get("fields") or []), src.content if src else ""
    )
    if new_fields is None:
        return False
    form_in.config = {**(form_in.config or {}), "fields": new_fields}  # novo dict: SQLAlchemy detecta a mudanca
    db.flush()
    return True


def _apply_action(db: Session, project_id: int, action: PendingAction) -> None:
    p = action.payload or {}
    kind = action.kind
    if kind in ("create_file", "edit_file"):
        path = p.get("path", "novo_arquivo.py")
        if unsafe_source_path(path):
            return  # ignore traversal/absolute paths proposed by the AI
        content = p.get("content", "")
        existing = (
            db.query(SourceFile)
            .filter(SourceFile.project_id == project_id, SourceFile.path == path)
            .first()
        )
        if existing:
            existing.content = content
        else:
            db.add(SourceFile(project_id=project_id, path=path, content=content))
    elif kind == "install_package":
        pkg = p.get("package", "").strip()
        req = (
            db.query(SourceFile)
            .filter(SourceFile.project_id == project_id, SourceFile.path == "requirements.txt")
            .first()
        )
        if req and pkg and pkg not in req.content:
            req.content = (req.content.rstrip() + f"\n{pkg}\n")
    elif kind == "require_env":
        key = (p.get("key") or "").strip()
        if key:
            exists = (
                db.query(EnvVar)
                .filter(EnvVar.project_id == project_id, EnvVar.key == key)
                .first()
            )
            if not exists:
                db.add(
                    EnvVar(
                        project_id=project_id,
                        key=key,
                        value=p.get("value", ""),
                        secret=True,
                    )
                )
    elif kind == "create_stage":
        stype = p.get("stage_type", "script")
        name = p.get("name", "Novo nó")
        key = slugify(name)
        entry = f"{key}.py" if stype in ("script", "job", "agent") else ""
        db.add(
            Stage(
                project_id=project_id, type=stype, name=name, key=key,
                entry_file=entry, config={},
            )
        )
    db.flush()
