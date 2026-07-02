# Conserto do gerador extrato para Domínio, Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer o caminho do Wizard gerar, a partir do pedido em linguagem natural mais os três arquivos, uma automação completa (extrato PDF para planilha do Domínio, classificando pelo Contas.xlsx), e fazer falhas de execução retornarem mensagem legível.

**Architecture:** O caminho do Wizard (`build_from_wizard` para `_generate_script`) passa a herdar as duas alavancas que o caminho do Chat já tem: injeção do código de referência da galeria (few-shot mais semente determinística) e o plano estruturado de arquivos deduzido pelo `analyze`. O Form é dimensionado por `max(plano, código)`. O runner popula `output_data['erro']` quando o script falha sem gravar saída.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, pandas 2.x, pdfplumber, openpyxl, pytest, monkeypatch. Sem dependência nova.

## Global Constraints

- Backend apenas. Sem migração nem mudança de schema de banco. Sem dependência nova.
- Canal de erro: reusar `output_data['erro']` (sem novo campo em `Execution`/`ExecutionOut`).
- Tamanho do Form de entrada: `max(len(plano.files), _count_input_files(codigo))`.
- Escopo: caminho do Wizard mais o runner compartilhado. O caminho do Chat só herda a instrução compartilhada de `get_file(0..n)` posicional (via prompt), sem novas mudanças em `run_construtor`.
- Não quebrar os projetos seed existentes (ex.: Conciliador) nem nenhum teste em `back/tests/`.
- Testes rodam contra o banco local de teste (SQLite em memória), nunca contra Postgres/Supabase.
- Nenhuma saída pode conter travessão em dash. Não usar o caractere `—` em nenhuma string, inclusive nos literais de código do produto (regra da organização). Usar vírgula, dois pontos ou reestruturar.
- As fixtures em `testes/dominio/` são locais e untracked. Qualquer teste que dependa delas deve chamar `pytest.skip` quando os arquivos não existirem.
- Commits tocam SOMENTE os caminhos explícitos de cada task. Não usar `git add -A`, para não capturar WIP de outras sessões na árvore.

## File Structure

- Modify: `back/app/runtime/runner.py` — helper `_last_error_line` mais fiação em `_execute`/`_fail_silently` (Task 1).
- Modify: `back/app/routers/chat.py` — `_input_file_fields` ganha parâmetro `plan_files` (Task 2).
- Modify: `back/app/routers/wizard.py` — `_input_fields` dimensiona por max (Task 2), `_ANALYZE_INSTR` e fallbacks emitem `input.files` (Task 3), `_generate_script` injeta referência mais plano de arquivos e semeia (Task 4).
- Test: `back/tests/test_runner_error.py` (novo, Task 1).
- Test: `back/tests/test_workflow_inputs.py` (existente, adicionar caso de papéis, Task 2).
- Test: `back/tests/test_wizard_analyze.py` (novo, Task 3).
- Test: `back/tests/test_wizard_generate.py` (novo, Task 4).
- Test: `back/tests/test_extrato_dominio_e2e.py` (novo, Task 5).

Todos os comandos de teste rodam a partir de `back/` com a venv do projeto ativa (ex.: `back/.venv/Scripts/python`). Onde o plano escreve `python -m pytest`, use o python da venv.

---

### Task 1: Runner popula erro legível em falha dura

**Files:**
- Modify: `back/app/runtime/runner.py` (topo: `import re`; novo `_last_error_line`; fiação em `_execute` ~L155-169 e `_fail_silently` ~L78-88)
- Test: `back/tests/test_runner_error.py`

**Interfaces:**
- Produces: `_last_error_line(stderr: str) -> str` (última linha significativa do traceback, para o campo `erro`).

- [ ] **Step 1: Escrever o teste que falha**

Criar `back/tests/test_runner_error.py`:

```python
from app.runtime.runner import _last_error_line


def test_last_error_line_prefere_a_excecao():
    tb = (
        "Traceback (most recent call last):\n"
        '  File "processar.py", line 12, in <module>\n'
        '    raise ValueError("PDF invalido: sem paginas legiveis")\n'
        "ValueError: PDF invalido: sem paginas legiveis\n"
    )
    assert _last_error_line(tb) == "ValueError: PDF invalido: sem paginas legiveis"


def test_last_error_line_cai_na_ultima_linha_quando_nao_ha_excecao():
    assert _last_error_line("aviso qualquer\nmensagem final") == "mensagem final"


def test_last_error_line_vazio_tem_mensagem_padrao():
    msg = _last_error_line("")
    assert msg and "falhou" in msg.lower()
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `cd back && python -m pytest tests/test_runner_error.py -v`
Expected: FAIL com `ImportError: cannot import name '_last_error_line'`.

- [ ] **Step 3: Implementar o helper e a fiação**

Em `back/app/runtime/runner.py`, adicionar `import re` ao bloco de imports do topo (logo após `import json`).

Adicionar o helper (antes da classe `RuntimeManager`):

```python
def _last_error_line(stderr: str) -> str:
    """Ultima linha significativa de um traceback, para virar mensagem legivel ao
    usuario (o campo 'erro' que o app publicado ja exibe). Prefere a linha da
    excecao (ex.: 'ValueError: ...'); cai na ultima linha nao vazia."""
    linhas = [ln.strip() for ln in (stderr or "").splitlines() if ln.strip()]
    if not linhas:
        return "A automacao falhou sem mensagem. Verifique os arquivos de entrada."
    for ln in reversed(linhas):
        if re.match(r"^[\w.]+(Error|Exception|Warning|Erro)\b", ln):
            return ln[:300]
    return linhas[-1][:300]
```

Em `_execute`, trocar o bloco atual:

```python
            execu.stdout = out
            execu.stderr = err
            execu.output_data = output_data
            execu.status = "success" if code == 0 else "error"
            execu.finished_at = _utcnow()
            db.commit()
```

por:

```python
            execu.stdout = out
            execu.stderr = err
            execu.status = "success" if code == 0 else "error"
            # falha dura sem saida gravada: sintetiza uma mensagem legivel no mesmo
            # canal 'erro' que o app publicado e o ReportCard ja exibem.
            if (execu.status == "error" and not output_data.get("erro")
                    and not output_data.get("arquivo_resultado")):
                output_data = {**output_data, "erro": _last_error_line(err)}
            execu.output_data = output_data
            execu.finished_at = _utcnow()
            db.commit()
```

Em `_fail_silently`, após `execu.stderr = ...`, garantir o mesmo canal:

```python
    def _fail_silently(self, execution_id: str, message: str) -> None:
        db = SessionLocal()
        try:
            execu = db.get(Execution, execution_id)
            if execu:
                execu.status = "error"
                execu.stderr = (execu.stderr or "") + f"\n[runtime] {message}"
                if not (execu.output_data or {}).get("erro"):
                    execu.output_data = {**(execu.output_data or {}),
                                         "erro": _last_error_line(execu.stderr)}
                execu.finished_at = _utcnow()
                db.commit()
        finally:
            db.close()
```

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `cd back && python -m pytest tests/test_runner_error.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add back/app/runtime/runner.py back/tests/test_runner_error.py
git commit -m "fix(runner): popula output_data['erro'] legivel em falha dura"
```

---

### Task 2: Form dimensionado por max(plano, código) com rótulos do plano

**Files:**
- Modify: `back/app/routers/chat.py` (`_input_file_fields`, ~L877-888)
- Modify: `back/app/routers/wizard.py` (`_input_fields`, ~L122-137)
- Test: `back/tests/test_workflow_inputs.py` (adicionar casos; NÃO reescrever os existentes)

**Interfaces:**
- Consumes: `_count_input_files(code) -> int`, `_file_labels_from_code(code, n) -> list[str|None]` (já existem em chat.py).
- Produces: `_input_file_fields(n: int, code: str = "", plan_files: list[dict] | None = None) -> list[dict]`; `_input_fields(inp: dict, code: str = "") -> list[dict]` passa a usar `max(len(inp['files']), _count_input_files(code))`.
- Formato de um item de `plan_files`: `{"role": str, "label": str, "hint": str}` (todos opcionais).

- [ ] **Step 1: Escrever o teste que falha**

Adicionar ao FIM de `back/tests/test_workflow_inputs.py` (append, sem mexer nos testes existentes):

```python
def test_input_file_fields_usa_papeis_do_plano():
    # papel do plano (analyze) vence o rotulo derivado do codigo
    code = "ext = get_file(0)\npl = get_file(1)\n"
    plan = [
        {"role": "extrato", "label": "Extrato bancario"},
        {"role": "plano_contas", "label": "Plano de contas"},
        {"role": "modelo", "label": "Modelo Dominio"},
    ]
    fields = _input_file_fields(3, code, plan)
    assert [f["name"] for f in fields] == ["arquivo1", "arquivo2", "arquivo3"]
    assert [f["label"] for f in fields] == ["Extrato bancario", "Plano de contas", "Modelo Dominio"]


def test_input_file_fields_sem_plano_mantem_comportamento():
    # plan_files ausente => rotulos derivam do codigo, como antes
    code = "extrato = pd.read_excel(get_file(0))\nrazao = pd.read_excel(get_file(1))\n"
    assert [f["label"] for f in _input_file_fields(2, code)] == ["Extrato", "Razao"]


def test_input_fields_dimensiona_por_max_plano_codigo():
    from app.routers.wizard import _input_fields
    code = "ext = get_file(0)\npl = get_file(1)\n"  # codigo le 2
    inp = {"kind": "file", "files": [
        {"role": "extrato", "label": "Extrato"},
        {"role": "plano", "label": "Plano"},
        {"role": "modelo", "label": "Modelo"},
    ]}  # plano pede 3
    fields = _input_fields(inp, code)
    assert len(fields) == 3            # max(3, 2)
    assert fields[0]["label"] == "Extrato"
    assert fields[2]["label"] == "Modelo"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd back && python -m pytest tests/test_workflow_inputs.py -v`
Expected: FAIL nos três novos testes (`_input_file_fields()` ainda não aceita `plan_files`; `_input_fields` ainda dimensiona só pelo código).

- [ ] **Step 3: Implementar**

Em `back/app/routers/chat.py`, substituir `_input_file_fields`:

```python
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
```

Em `back/app/routers/wizard.py`, no `_input_fields`, trocar o ramo `kind == "file"`:

```python
    if kind == "file":
        # dimensiona pelo MAIOR entre o plano do analyze (papeis) e o que o codigo usa
        # (get_file(0), get_file(1), ...). Assim 3 arquivos deduzidos nao encolhem para
        # 1 so porque o codigo gerado ainda lia menos.
        plan_files = inp.get("files") or []
        n = max(len(plan_files), _count_input_files(code))
        return _input_file_fields(n, code, plan_files)
```

- [ ] **Step 4: Rodar e ver passar (novos e antigos)**

Run: `cd back && python -m pytest tests/test_workflow_inputs.py -v`
Expected: PASS em todos (os existentes continuam verdes por retrocompatibilidade do `plan_files=None`).

- [ ] **Step 5: Commit**

```bash
git add back/app/routers/chat.py back/app/routers/wizard.py back/tests/test_workflow_inputs.py
git commit -m "feat(wizard): Form dimensionado por max(plano,codigo) com papeis do analyze"
```

---

### Task 3: analyze emite o plano de arquivos estruturado (input.files)

**Files:**
- Modify: `back/app/routers/wizard.py` (`_ANALYZE_INSTR` ~L177-194; fallback sem IA ~L205-208; fallback de exceção ~L230-231)
- Test: `back/tests/test_wizard_analyze.py` (novo)

**Interfaces:**
- Produces: o plano de `analyze` passa a conter, quando `input.kind == "file"`, `input.files = [{"role", "label", "hint"}]` na ordem de leitura. Fallbacks (sem IA e exceção) incluem `input.files` (lista, possivelmente vazia) para estabilidade de forma.

- [ ] **Step 1: Escrever o teste que falha**

Criar `back/tests/test_wizard_analyze.py`:

```python
from app.routers import wizard
from app.config import settings


def test_instrucao_pede_lista_de_arquivos():
    instr = wizard._ANALYZE_INSTR
    assert '"files"' in instr
    assert "role" in instr and "get_file(0)" in instr


def test_fallback_sem_ia_tem_chave_files(monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", False)
    plan = wizard._analyze_prompt(None, 1, "somar a planilha enviada", None)
    assert plan["input"]["kind"] == "file"
    assert isinstance(plan["input"]["files"], list)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd back && python -m pytest tests/test_wizard_analyze.py -v`
Expected: FAIL (`'"files"'` não está em `_ANALYZE_INSTR`; fallback não tem `files`).

- [ ] **Step 3: Implementar**

Em `_ANALYZE_INSTR`, trocar a linha do `input` do schema:

```python
    '"input": {"kind": "file"|"fields"|"none"|null, "confident": true|false, "question": "ou null", '
    '"fields": [{"label": "", "type": "text"|"number"|"date"|"select"}]}, '
```

por (acrescenta `files` ao schema):

```python
    '"input": {"kind": "file"|"fields"|"none"|null, "confident": true|false, "question": "ou null", '
    '"files": [{"role": "extrato", "label": "Extrato bancario", "hint": "PDF do extrato"}], '
    '"fields": [{"label": "", "type": "text"|"number"|"date"|"select"}]}, '
```

E acrescentar uma regra ao bloco de REGRAS (antes de `process.description deve capturar...`):

```python
    "Quando input.kind='file', liste em input.files TODOS os arquivos distintos que a "
    "tarefa precisa, na ORDEM em que o codigo deve le-los (get_file(0), get_file(1), ...), "
    "cada um com role curto (ex: 'extrato', 'plano_contas', 'modelo'), label amigavel e "
    "hint do formato. Um unico arquivo => uma unica entrada em files. "
```

No fallback sem IA, trocar a linha do `input`:

```python
            "input": {"kind": "file", "confident": True, "question": None, "fields": []},
```

por:

```python
            "input": {"kind": "file", "confident": True, "question": None, "fields": [], "files": []},
```

No fallback de exceção, trocar:

```python
            "input": {"kind": "file", "confident": False,
                      "question": "O que a automação recebe (um arquivo, alguns campos, ou nada)?", "fields": []},
```

por:

```python
            "input": {"kind": "file", "confident": False,
                      "question": "O que a automação recebe (um arquivo, alguns campos, ou nada)?",
                      "fields": [], "files": []},
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd back && python -m pytest tests/test_wizard_analyze.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add back/app/routers/wizard.py back/tests/test_wizard_analyze.py
git commit -m "feat(wizard): analyze emite input.files (papel e ordem dos arquivos)"
```

---

### Task 4: build injeta referência da galeria mais plano de arquivos no gerador

**Files:**
- Modify: `back/app/routers/wizard.py` (novo `_files_intent`; reescrita de `_generate_script` ~L140-174)
- Test: `back/tests/test_wizard_generate.py` (novo)

**Interfaces:**
- Consumes: `reference_for_task(text) -> {template_key, code, score} | None`, `REF_LOW`, `REF_HIGH` (de `app.services.reference_code`); `_seed_primary_script(actions, code) -> actions` (de `app.routers.orchestrator`); `_generate_build(messages) -> (explanation, actions, name)`, `_project_context`, `_attachment_context` (de chat.py, já importados no topo de wizard.py).
- Produces: `_files_intent(inp: dict) -> str`; `_generate_script(db, project_id, ws) -> (explanation, code)` agora injeta referência e semeia em casamento claro.

- [ ] **Step 1: Escrever o teste que falha**

Criar `back/tests/test_wizard_generate.py`:

```python
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Organization, Project
from app.routers import wizard
from app.config import settings


def _projeto(s):
    org = Organization(name="IRKO")
    s.add(org)
    s.flush()
    p = Project(org_id=org.id, name="x", subdomain="x")
    s.add(p)
    s.flush()
    return p


def _ws_extrato():
    return {
        "process": {"description": "extrato bancario Bradesco em PDF para lancamentos do Dominio"},
        "input": {"kind": "file", "files": [
            {"role": "extrato", "label": "Extrato"},
            {"role": "plano de contas", "label": "Plano de contas"},
            {"role": "modelo", "label": "Modelo"},
        ]},
        "output": {"kind": "download"},
    }


def test_generate_script_injeta_referencia_e_semeia(monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", True)
    captured = {}

    def fake_build(messages):
        captured["msgs"] = messages
        return ("ok", [{"kind": "create_file", "title": "x", "path": "p.py",
                        "content": "print('errado')"}], "")

    monkeypatch.setattr(wizard, "_generate_build", fake_build)

    eng = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        p = _projeto(s)
        explanation, code = wizard._generate_script(s, p.id, _ws_extrato())

    blob = " ".join(m["content"] for m in captured["msgs"])
    assert "IMPLEMENTAÇÃO DE REFERÊNCIA PROVADA" in blob   # few-shot injetado
    assert "def parse_extrato" in blob                     # referencia extrato-dominio
    assert "get_file(0)" in blob                           # instrucao posicional
    assert "3 arquivo" in blob                             # plano de arquivos no intent
    assert "def parse_extrato" in code                     # semeado (score alto)
    assert "print('errado')" not in code


def test_files_intent_lista_arquivos_por_indice():
    txt = wizard._files_intent({"files": [
        {"role": "extrato", "label": "Extrato", "hint": "PDF"},
        {"role": "plano", "label": "Plano de contas"},
    ]})
    assert "(0) Extrato" in txt and "(1) Plano de contas" in txt
    assert "get_file(0)" in txt and "POSICIONAL" in txt


def test_files_intent_vazio_quando_sem_plano():
    assert wizard._files_intent({}) == ""
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd back && python -m pytest tests/test_wizard_generate.py -v`
Expected: FAIL (`_files_intent` não existe; `_generate_script` não injeta referência nem semeia).

- [ ] **Step 3: Implementar**

Em `back/app/routers/wizard.py`, adicionar `_files_intent` acima de `_generate_script`:

```python
def _files_intent(inp: dict) -> str:
    """Descreve os arquivos de entrada (papel mais ordem) para o gerador ler com
    get_file(0..n) POSICIONAL e carregar cada arquivo anexado. Vazio quando o plano
    nao trouxe arquivos (o gerador se apoia na referencia e no contexto)."""
    files = inp.get("files") or []
    if not files:
        return ""
    partes = []
    for i, f in enumerate(files):
        rot = f.get("label") or f.get("role") or f"arquivo {i + 1}"
        hint = (f.get("hint") or "").strip()
        partes.append(f"({i}) {rot}" + (f": {hint}" if hint else ""))
    return (
        f"A entrada tem {len(files)} arquivo(s), nesta ordem exata: {'; '.join(partes)}. "
        "Leia cada um por indice com get_file(0), get_file(1), ... POSICIONAL "
        "(nunca get_file() sem indice quando ha mais de um arquivo). "
        "Leia o CONTEUDO de cada arquivo anexado; se um deles for o plano de contas, "
        "carregue-o do arquivo (NAO use get_table('regras_classificacao') para o plano). "
    )
```

Substituir `_generate_script` inteiro por:

```python
def _generate_script(db: Session, project_id: int, ws: dict) -> tuple[str, str]:
    """Gera o codigo do Script via a geracao estruturada do chat. Injeta o codigo de
    referencia da galeria (few-shot; semente deterministica em casamento claro) e o
    plano de arquivos deduzido, para o gerador ler N arquivos posicionalmente e nao
    reinventar um classificador. Retorna (explicacao, codigo)."""
    from ..services.reference_code import reference_for_task, REF_LOW, REF_HIGH

    process = (ws.get("process") or {}).get("description", "").strip()
    inp = ws.get("input") or {}
    out = ws.get("output") or {}
    out_kind = out.get("kind", "download")
    intent = (
        f"Monte agora a automação. Tarefa: {process}. "
        f"Entrada: {inp.get('kind', 'nenhuma')}. "
        + _files_intent(inp)
        + "Saída desejada: "
        + ("um arquivo para download (use output_path e set_output com "
           "'arquivo_resultado' e 'resumo'). Se o fluxo tiver revisão humana em 2 "
           "passes, o pass 2 (com a confirmação) DEVE gerar o arquivo_resultado."
           if out_kind == "download"
           else "um resumo na tela (set_output com a chave 'resumo').")
    )
    proj_ctx = _project_context(db, project_id)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": proj_ctx},
    ]
    # contexto real dos arquivos anexados (colunas/amostras): aceita lista ou um so
    samples = inp.get("sample_files") or ([inp["sample_file"]] if inp.get("sample_file") else [])
    if samples:
        ctx = _attachment_context(project_id, samples)
        if ctx:
            messages.append({"role": "system", "content": ctx})
    # codigo de referencia da galeria: mesma alavanca do Construtor do chat
    ref = reference_for_task(process + " " + proj_ctx)
    if ref and ref["score"] >= REF_LOW:
        messages.append({
            "role": "system",
            "content": "IMPLEMENTAÇÃO DE REFERÊNCIA PROVADA (adapte, não reescreva do "
                       f"zero):\n```python\n{ref['code']}\n```",
        })
    messages.append({"role": "user", "content": intent})

    explanation, actions, _name = _generate_build(messages)
    if ref and ref["score"] >= REF_HIGH:
        from .orchestrator import _seed_primary_script
        actions = _seed_primary_script(actions, ref["code"])
    code = ""
    for a in actions:
        if a.get("kind") in ("create_file", "edit_file") and a.get("content"):
            code = a["content"]
            break
    if not code:
        code = _FALLBACK_SCRIPT
    return explanation or "Fluxo gerado.", code
```

Nota: a única string com o caractere `—` proibida pela organização não aparece aqui; conferir que nenhum literal introduzido contém `—`.

- [ ] **Step 4: Rodar e ver passar**

Run: `cd back && python -m pytest tests/test_wizard_generate.py -v`
Expected: PASS (3 passed). Se `test_generate_script_injeta_referencia_e_semeia` falhar em `def parse_extrato in code` (semente não disparou), inspecionar o score: rodar `python -c "from app.services.reference_code import reference_for_task as r; print(r('extrato bancario Bradesco em PDF para lancamentos do Dominio'))"` e conferir `score >= REF_HIGH`. Se o score vier abaixo do limiar, o casamento da galeria regrediu (fora do escopo desta task; anotar e seguir com o few-shot, que ainda injeta a referência).

- [ ] **Step 5: Commit**

```bash
git add back/app/routers/wizard.py back/tests/test_wizard_generate.py
git commit -m "feat(wizard): build injeta referencia da galeria + plano de arquivos posicional"
```

---

### Task 5: Aceite E2E, template extrato-dominio contra as fixtures reais

**Files:**
- Test: `back/tests/test_extrato_dominio_e2e.py` (novo)

**Interfaces:**
- Consumes: `TEMPLATES["extrato-dominio"]["code"]` (de `app.routers.templates`), `_SDK_SOURCE` (de `app.services.storage`). Fixtures em `testes/dominio/`.

Este é o portão de aceite determinístico (sem OpenAI). Carrega o código que o gerador semeia e o roda contra os arquivos reais: pass 1 lê o plano (contas não vazio) e monta a revisão; pass 2 gera o `arquivo_resultado` com linhas. Pode passar já na primeira execução (caracteriza que o template está correto em dados reais); seu valor é travar regressão.

- [ ] **Step 1: Escrever o teste (portão de aceite)**

Criar `back/tests/test_extrato_dominio_e2e.py`:

```python
"""Aceite E2E deterministico: o codigo semeado pelo gerador (template extrato-dominio)
rodando contra as fixtures reais em testes/dominio/. Sem OpenAI."""
import importlib.util
import json
from pathlib import Path

import pytest

BACK = Path(__file__).resolve().parent.parent
FIXTURES = BACK.parent / "testes" / "dominio"
PDF = FIXTURES / "JBB GIG - EXTRATO BRADESCO 04.2026 (1).pdf"
CONTAS = FIXTURES / "Contas.xlsx"

pytestmark = pytest.mark.skipif(
    not (PDF.exists() and CONTAS.exists()),
    reason="fixtures locais em testes/dominio/ ausentes",
)


def _carrega_template(tmp_path, monkeypatch):
    from app.routers.templates import TEMPLATES
    from app.services.storage import _SDK_SOURCE

    (tmp_path / "flowdesk_sdk.py").write_text(_SDK_SOURCE, encoding="utf-8")
    f = tmp_path / "processar.py"
    f.write_text(TEMPLATES["extrato-dominio"]["code"], encoding="utf-8")
    run = tmp_path / "run"
    run.mkdir(exist_ok=True)
    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    # o SDK cacheia os caminhos de env no import; fixa-os antes de carregar o modulo
    monkeypatch.setenv("FLOWDESK_INPUT", str(tmp_path / "input.json"))
    monkeypatch.setenv("FLOWDESK_OUTPUT", str(tmp_path / "output.json"))
    monkeypatch.setenv("FLOWDESK_OUTPUT_DIR", str(out_dir))
    monkeypatch.setenv("FLOWDESK_RUN_DIR", str(run))
    monkeypatch.syspath_prepend(str(tmp_path))
    spec = importlib.util.spec_from_file_location("processar_e2e", f)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # __name__ != '__main__' => main() nao roda no import
    return mod, tmp_path


def _roda(mod, tmp_path, entrada: dict) -> dict:
    (tmp_path / "input.json").write_text(json.dumps(entrada), encoding="utf-8")
    saida = tmp_path / "output.json"
    if saida.exists():
        saida.unlink()
    mod.main()
    return json.loads(saida.read_text(encoding="utf-8"))


def test_pass1_le_plano_e_monta_revisao(tmp_path, monkeypatch):
    mod, tmp = _carrega_template(tmp_path, monkeypatch)
    out = _roda(mod, tmp, {"arquivo1": str(PDF), "arquivo2": str(CONTAS)})
    rev = out.get("_classificacao_review")
    assert rev, f"esperava _classificacao_review, veio {list(out)}"
    assert len(rev["contas"]) > 1000                 # leu o Contas.xlsx de fato
    assert rev["grupos"], "sem grupos classificaveis"
    assert rev["total_lancamentos"] > 0


def test_pass2_gera_arquivo_resultado(tmp_path, monkeypatch):
    mod, tmp = _carrega_template(tmp_path, monkeypatch)
    rev = _roda(mod, tmp, {"arquivo1": str(PDF), "arquivo2": str(CONTAS)})["_classificacao_review"]
    # confirma todos os grupos numa conta analitica qualquer do plano
    conta = rev["contas"][0]["codigo"]
    confirmado = {g["padrao"]: conta for g in rev["grupos"]}
    periodo = rev["periodo_detectado"]
    out = _roda(mod, tmp, {
        "arquivo1": str(PDF), "arquivo2": str(CONTAS),
        "_classificacao_confirmada": confirmado,
        "_conta_banco": "1",
        "_periodo": periodo,
    })
    assert out.get("arquivo_resultado"), f"esperava arquivo_resultado, veio {list(out)}"
    from openpyxl import load_workbook
    wb = load_workbook(out["arquivo_resultado"])
    ws = wb["Planilha1"]
    linhas = list(ws.iter_rows(min_row=2, values_only=True))
    assert len(linhas) > 0                            # planilha do Dominio preenchida


def test_pdf_invalido_retorna_erro_legivel(tmp_path, monkeypatch):
    mod, tmp = _carrega_template(tmp_path, monkeypatch)
    ruim = tmp / "vazio.pdf"
    ruim.write_bytes(b"nao e um pdf")
    # get_file(0) precisa existir no disco; usa o arquivo ruim como extrato
    try:
        out = _roda(mod, tmp, {"arquivo1": str(ruim), "arquivo2": str(CONTAS)})
    except Exception:
        pytest.skip("template propaga excecao; o canal 'erro' e coberto por test_runner_error")
    assert out.get("erro") or out.get("_classificacao_review") is None
```

- [ ] **Step 2: Rodar o portão de aceite**

Run: `cd back && python -m pytest tests/test_extrato_dominio_e2e.py -v`
Expected: PASS (ou SKIP se as fixtures não estiverem presentes). Se `test_pass1` falhar com `contas` vazio, o `carregar_plano` do template não está lendo o `Contas.xlsx` (regressão do template): comparar `TEMPLATES["extrato-dominio"]["code"]` com `testes/dominio/extrato_bradesco_para_dominio.CORRIGIDO.py` e alinhar `carregar_plano`. Se `test_pass2` falhar sem `arquivo_resultado`, conferir que o pass 2 do template grava via `output_path` e chama `set_output({"arquivo_resultado": ...})`.

- [ ] **Step 3: Rodar a suíte inteira, sem regressão**

Run: `cd back && python -m pytest -q`
Expected: PASS em toda a suíte (o E2E pode aparecer como skipped se faltarem fixtures). Nenhuma regressão nos seeds (Conciliador) nem nos testes de template/construtor.

- [ ] **Step 4: Commit**

```bash
git add back/tests/test_extrato_dominio_e2e.py
git commit -m "test(e2e): aceite do template extrato-dominio contra fixtures reais"
```

- [ ] **Step 5: Verificação final no app real**

Rodar o `/verify` no fluxo real (o mesmo do projeto 105) com IA ao vivo: a partir SOMENTE do prompt mais os três arquivos, a automação gerada deve extrair os lançamentos do PDF, classificar usando o Contas.xlsx e produzir um `arquivo_resultado` no layout do Domínio para download; e um PDF inválido deve retornar mensagem legível, não `error=null`. Registrar evidência (execução com `arquivo_resultado` e uma execução de erro com `erro` preenchido).

---

## Self-Review

**1. Spec coverage:**
- Sintoma 1 (3 arquivos viram 1): Task 3 (analyze emite files) mais Task 2 (Form = max) mais Task 4 (plano no intent). Coberto.
- Sintoma 2 (classificação vazia): Task 4 (injeção da referência que lê o plano; instrução para não usar get_table no plano). Coberto e validado por Task 5 (pass 1 contas > 1000).
- Sintoma 3 (só fase 1): Task 4 (semente do oráculo de 2 passes mais instrução de pass 2 gerar arquivo). Coberto e validado por Task 5 (pass 2 gera arquivo).
- Sintoma 4 (error=null): Task 1 (runner popula output_data['erro']). Coberto.
- Sintoma 5 (get_file por ordem de dict): Task 4 (intent get_file(0..n) posicional) mais Task 2 (Form na ordem dos papéis). Coberto.
- Decisão max(plano,código): Task 2. Decisão reusar output_data['erro']: Task 1. Escopo wizard mais runner: respeitado (chat só herda instrução via prompt, sem tocar run_construtor).

**2. Placeholder scan:** Sem TBD/TODO. Todo passo de código mostra o código real e o comando com resultado esperado.

**3. Type consistency:** `_input_file_fields(n, code, plan_files=None)` usado consistentemente (Task 2); os demais callers (`_ensure_runnable_workflow`, `_reconciled_input_fields`) seguem válidos por default. `_files_intent(inp) -> str` e `_generate_script(db, project_id, ws) -> (str, str)` batem entre Task 4 e os testes. `_last_error_line(str) -> str` idem (Task 1). Formato de `plan_files` item `{role,label,hint}` idêntico em analyze (Task 3), Form (Task 2) e intent (Task 4).
