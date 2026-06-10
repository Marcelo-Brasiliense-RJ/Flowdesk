"""Smart Chat (AI panel) — OpenAI streaming + approve/reject pending actions.

Protocol: the model streams natural-language text, then may append a fenced
block:

    ```flowdesk-actions
    {"questions": [...], "actions": [...]}
    ```

`questions` become clarifying radio/input prompts shown in the chat.
`actions` become PendingAction rows the user must Approve before they apply.
"""
from __future__ import annotations

import json
import re

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
from ..services import storage
from .projects import get_project, slugify, unsafe_source_path

router = APIRouter(prefix="/api", tags=["chat"])

CONTEXT_WINDOW = 128_000
ACTIONS_RE = re.compile(r"```flowdesk-actions\s*(\{.*?\})\s*```", re.DOTALL)

SYSTEM_PROMPT = """Você é o assistente do FlowDesk, uma plataforma low-code de \
automação com IA. O usuário descreve em linguagem natural o que quer automatizar e \
você ajuda a desenhar o fluxo (forms, scripts) e a escrever o código Python.

PROCESSO OBRIGATÓRIO — ENTREVISTA (DISCOVERY ANTES DE CONSTRUIR):
1. Antes de criar qualquer coisa, levante as perguntas de esclarecimento NECESSÁRIAS \
(de 1 a 5) e devolva TODAS no campo "questions" do bloco flowdesk-actions. A interface \
mostra UMA pergunta por vez ao usuário (com indicador de progresso), então cada \
pergunta deve ser independente e objetiva. NÃO escreva código nem inclua "actions" \
enquanto estiver perguntando.
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
código agora" sem incluir o bloco de actions — isso deixa o fluxo sem terminar.

REGRAS DE CÓDIGO:
- Scripts Python usam o SDK: `from flowdesk_sdk import get_file, set_output, \
output_path, log` (get_file() para ler o arquivo de entrada).
- `set_output` SEMPRE recebe um DICT, nunca uma string. Ex.: \
`set_output({"arquivo_resultado": str(out), "resumo": {...}})`.
- pandas é 2.x: NÃO use `df.append(...)` (foi removido) — use `pd.concat([...])`. \
Para escrever Excel com várias abas use `pd.ExcelWriter(output_path("nome.xlsx"), \
engine="openpyxl")`.
- Use SEMPRE o contexto do projeto e dos arquivos anexados (colunas reais, stages \
existentes). Não invente nomes de colunas nem recrie stages que já existem.
- Responda em português, de forma concisa. Sempre mostre código dentro de blocos \
```python ... ```.

ENTRADA E SAÍDA DE ARQUIVOS (a PLATAFORMA cuida disso):
- Para LER o arquivo de entrada use `get_file()` do SDK (retorna o caminho do arquivo \
enviado no Form, sem depender do nome do campo). Ex.: `df = pd.read_excel(get_file())`. \
Para um 2º arquivo: `get_file(1)`. NUNCA peça ao usuário o caminho do arquivo de entrada \
e NUNCA invente uma chave fixa em get_input().
- Os arquivos de SAÍDA devem ser gravados com `output_path("nome.xlsx")` do SDK; o \
download é feito AUTOMATICAMENTE pela plataforma. NÃO existe "caminho local" para salvar \
— NUNCA peça PATH_OUTPUT, diretório, pasta ou caminho de arquivo.

DEPENDÊNCIAS DE CONFIGURAÇÃO E SEGREDOS:
- Use `require_env` APENAS quando o usuário pedir EXPLICITAMENTE uma integração externa \
(enviar e-mail, chamar uma API, gravar no Google Sheets, etc.). Se a tarefa só processa \
um arquivo e gera uma planilha de saída, NÃO há segredos — NÃO declare NENHUM require_env \
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
require_env (key, description, example)."""


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
    return (
        "O usuário anexou arquivos ao projeto. Abaixo estão os dados REAIS deles. "
        "Baseie suas perguntas e seu código nessas colunas e amostras; NÃO pergunte "
        "informações que já estão visíveis aqui (como nomes de colunas):\n\n"
        + "\n\n".join(blocks)
    )


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
    build_intent = body.content.strip().lower().startswith("respostas da entrevista") or bool(
        re.search(
            r"\b(monta|montar|monte|cria|criar|crie|gera|gerar|gere|constr|finaliz|implementa)",
            body.content,
            re.IGNORECASE,
        )
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": _project_context(db, project_id)},
    ]
    ctx_block = _attachment_context(project_id, body.attachments)
    if ctx_block:
        messages.append({"role": "system", "content": ctx_block})
    if build_intent:
        messages.append(
            {
                "role": "system",
                "content": (
                    "O usuário pediu para CONSTRUIR AGORA. NÃO faça mais perguntas "
                    "(sem 'questions'). Gere imediatamente as 'actions': use "
                    "'require_env' para cada segredo/credencial e 'create_file'/"
                    "'create_stage' com o código pronto. Assuma padrões razoáveis "
                    "para o que faltar."
                ),
            }
        )
    # sliding window: só as últimas mensagens p/ não estourar o contexto/custo
    messages += [{"role": m.role, "content": m.content} for m in history[-20:]]

    def event_stream():
        if build_intent:
            # turno de construção: chamada estruturada (JSON) que SEMPRE traz ações
            clean_text, actions = _generate_build(messages)
            questions = []
            full_text = clean_text
            for word in re.findall(r"\S+\s*", clean_text):
                yield f"data: {json.dumps({'type': 'token', 'text': word})}\n\n"
        else:
            full_text = ""
            for chunk in _generate(messages, body.content):
                full_text += chunk
                yield f"data: {json.dumps({'type': 'token', 'text': chunk})}\n\n"
            clean_text, questions, actions = _parse_actions(full_text)
            for qq in questions:
                if not qq.get("label"):
                    qq["label"] = qq.get("question") or qq.get("text") or ""
            # fallback: model wrote discovery as prose list -> make it interactive
            if not questions and not actions:
                clean_text, questions = _parse_prose_questions(clean_text)
            questions = questions[:6]

        # drop nonsensical require_env asking for file paths (platform handles I/O)
        actions = [a for a in actions if not _is_pathlike_env(a)]
        # require_env só com integração externa; sem isso, é alucinação -> descarta
        convo = body.content + " " + " ".join(m.content for m in history)
        if not _INTEGRATION_INTENT.search(convo):
            actions = [a for a in actions if a.get("kind") != "require_env"]
        if questions:
            actions = []

        # persist in a fresh session (generator runs outside request scope)
        s = SessionLocal()
        try:
            assistant = ChatMessage(
                project_id=project_id, role="assistant", content=clean_text,
                meta={"questions": questions}, tokens=_estimate_tokens(full_text),
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
            {"type": "done", "questions": questions, "actions": created, "context": usage}
        ) + "\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _generate_build(messages: list[dict]):
    """Build turn: força JSON estruturado {message, actions} (sem depender de bloco
    solto no texto). Garante que o fluxo termina com ações concretas."""
    instr = {
        "role": "system",
        "content": (
            "Responda SOMENTE em JSON válido: "
            '{"message": "frase curta de resumo", "actions": [...]}. '
            "Tipos de action: create_file {kind,title,path,content}, "
            "create_stage {kind,title,stage_type,name}, "
            "require_env {kind,title,key,description,example}. "
            "Inclua SEMPRE pelo menos um create_file com o script Python completo, "
            "usando o SDK (get_file() para ler entrada, output_path() e set_output(DICT) "
            "para saída), pandas 2.x (NÃO use df.append; use pd.concat). "
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
        ])
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=messages + [instr],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        return data.get("message") or "Fluxo gerado.", data.get("actions") or []
    except Exception as exc:
        return f"[IA indisponível: {exc}]", []


def _generate(messages: list[dict], last_user: str):
    """Yield text chunks. Real OpenAI streaming when configured, else a mock."""
    if settings.ai_enabled:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=settings.openai_api_key)
            stream = client.chat.completions.create(
                model=settings.openai_model, messages=messages, stream=True,
            )
            for event in stream:
                delta = event.choices[0].delta.content if event.choices else None
                if delta:
                    yield delta
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
    """require_env asking for a file path / output location is invalid — the
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
    if action.kind in ("create_file", "edit_file"):
        p = action.payload or {}
        path = p.get("path", "")
        if path.endswith(".py") and "set_output" in (p.get("content") or ""):
            _ensure_runnable_workflow(db, project_id, path)
    action.status = "approved"
    db.commit()
    return {"ok": True, "status": "approved"}


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


def _ensure_runnable_workflow(db: Session, project_id: int, script_path: str) -> None:
    """Garante Form(entrada) -> Script -> Form(resultado) para um script gerado,
    quando o projeto ainda não tem nenhum nó executável. Sem isso, o Chat entrega
    só o código e nada roda pela interface."""
    stages = db.query(Stage).filter(Stage.project_id == project_id).all()
    if any(s.type == "script" for s in stages):
        return  # já existe workflow; não duplica

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
            "fields": [{"name": "arquivo", "label": "Arquivo", "type": "file"}],
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
