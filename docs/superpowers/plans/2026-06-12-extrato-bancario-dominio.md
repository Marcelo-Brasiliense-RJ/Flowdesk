# Extrato Bancário → Lançamentos Domínio: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar ao FlowDesk a capacidade de transformar extrato bancário PDF em planilha de lançamentos contábeis do Domínio, com classificação híbrida (regras De/Para → IA → revisão humana), linha do tempo de execução em tempo real, e entrevista de montagem em profundidade de contrato.

**Architecture:** Execução em 2 passes pelo mesmo script: pass 1 lê extrato + plano de contas, aplica regras De/Para (materializadas pelo runner em `tables.json`), agrupa lançamentos por padrão de histórico e devolve `_classificacao_review`; o front pede sugestões de IA ao backend (payload mínimo) para grupos sem regra, o usuário revisa/confirma numa tela com semáforo; pass 2 recebe `_classificacao_confirmada` + `_periodo` no payload e gera o xlsx no contrato Domínio. Progresso via `progress()` do SDK gravado em `progress.jsonl` e devolvido no polling de execução que já existe.

**Tech Stack:** FastAPI + SQLAlchemy (DataTable/DataRow já existem), pdfplumber (posicional), openpyxl, xlrd (+fallback Excel COM para xls do Domínio), OpenAI (gpt-4o-mini, payload mínimo), React + TS no front.

**Decisões travadas no grill (não rediscutir):** política (c) híbrida com revisão; (a) uma automação por cliente, plano de contas anexado ao projeto; lançamento simples, Inicia Lote = 1 na primeira linha de cada dia, Cód. Histórico vazio, Complemento = histórico do extrato; período sempre confirmado pelo usuário, pré-preenchido do cabeçalho; verde (regra) passa direto, âmbar (IA) e vermelho (sem sugestão) exigem ação; "Ignorar grupo" existe; payload mínimo para IA (sem valores/saldos/CNPJ); leitor tolerante de xls; aceite = totais ao centavo + estrutura idêntica ao modelo + import real no Domínio (lado do usuário).

**Caminhos absolutos:** repo = `C:\Users\mbrasiliense98\Documents\Biulder IRKO\Biulder_claude\flowdesk`. Python do backend = `back\.venv\Scripts\python.exe`. Arquivos reais para teste de integração (NÃO commitar, são dados de cliente): `back\storage\37\uploads\JBB GIG - EXTRATO BRADESCO 04.2026.pdf`, `C:\Users\mbrasiliense98\Downloads\Contas.xls`, `C:\Users\mbrasiliense98\Downloads\planilhamodeloimportacaolancamentoscontabeis.xlsx`.

---

## File Structure

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `back/requirements.txt` | Modify | + xlrd |
| `back/app/services/storage.py` | Modify | SDK: `progress()`, `get_table()`, `read_table()` |
| `back/app/runtime/runner.py` | Modify | materializa DataTables em `run_dir/tables.json`; grava `execu.run_dir` |
| `back/app/routers/executions.py` | Modify | GET execução devolve `progress` |
| `back/app/routers/published.py` | Modify | idem no endpoint público + endpoint de regras token-gated |
| `back/app/routers/classify.py` | Create | regras De/Para (CRUD) + sugestão IA payload mínimo |
| `back/main.py` | Modify | registra router classify |
| `back/app/routers/templates.py` | Modify | novo modelo `extrato-dominio` (script de referência completo) |
| `back/app/routers/chat.py` | Modify | SYSTEM_PROMPT: entrevista profunda, narração, novos recursos SDK |
| `back/tests/` | Create | pytest unitário (parser, xlsx, agrupamento) + integração skippable |
| `front/src/lib/types.ts` | Modify | `Execution.progress`, tipos da revisão |
| `front/src/components/ProgressTimeline.tsx` | Create | linha do tempo de etapas |
| `front/src/components/ClassificacaoReview.tsx` | Create | revisão com semáforo |
| `front/src/pages/Wizard.tsx` | Modify | TestPanel: timeline ao vivo + revisão + runTest(extra) |
| `front/src/pages/PublishedApp.tsx` | Modify | timeline + revisão no app publicado |
| `back/qa_suite.py` | Modify | seções novas (regras, classificar, template) |
| `docs/Arquitetura-FlowDesk.html` + `.pdf` | Modify | doc de arquitetura em dia (regra permanente do usuário) |

---

### Task 1: Branch e commit do trabalho pendente

Há mudanças não commitadas de correções anteriores (download no teste, aviso de resultado vazio, gate de publicar, prompt do chat, run-dev.ps1, docs). Elas precisam entrar antes para o diff das tasks ficar limpo.

**Files:** nenhum novo; commit do existente.

- [ ] **Step 1: Conferir o que está pendente**

Run: `git -C "C:\Users\mbrasiliense98\Documents\Biulder IRKO\Biulder_claude\flowdesk" status --short`
Expected: `M back/app/routers/chat.py`, `M front/src/pages/Wizard.tsx`, `?? back/run-dev.ps1`, `?? docs/...`, `?? docs/superpowers/plans/...`

- [ ] **Step 2: Criar branch e commitar**

```bash
cd "C:\Users\mbrasiliense98\Documents\Biulder IRKO\Biulder_claude\flowdesk"
git checkout -b feat/extrato-dominio
git add -A
git commit -m "fix(assistente): download do resultado no teste, aviso de resultado vazio e gate de publicar; script run-dev; docs de arquitetura

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

- [ ] **Step 3: Instalar dependências de teste e runtime**

```bash
cd "C:\Users\mbrasiliense98\Documents\Biulder IRKO\Biulder_claude\flowdesk\back"
.venv/Scripts/python.exe -m pip install xlrd pytest --quiet
```

Adicionar em `back/requirements.txt` (linha nova, junto das libs de dados): `xlrd` (pytest é só dev, não entra).

- [ ] **Step 4: Commit**

```bash
git add back/requirements.txt
git commit -m "chore(back): xlrd para ler xls legado do Domínio"
```

---

### Task 2: SDK — progress(), get_table() e read_table()

**Files:**
- Modify: `back/app/services/storage.py` (dentro da string `_SDK_SOURCE`, após a função `log`, ~linha 150)
- Modify: `back/app/runtime/runner.py` (em `_execute`, após criar `input_path`, ~linha 119)
- Test: `back/tests/test_sdk_helpers.py`

- [ ] **Step 1: Escrever teste que falha**

Criar `back/tests/__init__.py` vazio e `back/tests/test_sdk_helpers.py`:

```python
"""Testa os helpers novos do SDK executando-o como módulo isolado."""
import json
import os
import sys
import importlib.util
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))


def _load_sdk(tmp_path, monkeypatch):
    """Materializa o _SDK_SOURCE num arquivo e importa com env de runtime fake."""
    from app.services.storage import _SDK_SOURCE
    sdk_file = tmp_path / "flowdesk_sdk.py"
    sdk_file.write_text(_SDK_SOURCE, encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (tmp_path / "input.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("FLOWDESK_INPUT", str(tmp_path / "input.json"))
    monkeypatch.setenv("FLOWDESK_OUTPUT", str(tmp_path / "output.json"))
    monkeypatch.setenv("FLOWDESK_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("FLOWDESK_RUN_DIR", str(run_dir))
    spec = importlib.util.spec_from_file_location("flowdesk_sdk_t", sdk_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, run_dir


def test_progress_appends_jsonl(tmp_path, monkeypatch):
    sdk, run_dir = _load_sdk(tmp_path, monkeypatch)
    sdk.progress("Lendo extrato", "564 lançamentos")
    sdk.progress("Aplicando regras")
    lines = (run_dir / "progress.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["etapa"] == "Lendo extrato"
    assert first["detalhe"] == "564 lançamentos"


def test_get_table_reads_materialized_json(tmp_path, monkeypatch):
    sdk, run_dir = _load_sdk(tmp_path, monkeypatch)
    (run_dir / "tables.json").write_text(
        json.dumps({"regras_classificacao": [{"padrao": "TARIFA BANCARIA", "conta_codigo": "999"}]}),
        encoding="utf-8",
    )
    rows = sdk.get_table("regras_classificacao")
    assert rows[0]["conta_codigo"] == "999"
    assert sdk.get_table("inexistente") == []


def test_read_table_xlsx_and_csv(tmp_path, monkeypatch):
    import pandas as pd
    sdk, _ = _load_sdk(tmp_path, monkeypatch)
    df0 = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    xlsx = tmp_path / "t.xlsx"; df0.to_excel(xlsx, index=False)
    csv = tmp_path / "t.csv"; df0.to_csv(csv, index=False)
    assert sdk.read_table(str(xlsx)).shape == (2, 2)
    assert sdk.read_table(str(csv)).shape == (2, 2)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd back && .venv/Scripts/python.exe -m pytest tests/test_sdk_helpers.py -v`
Expected: FAIL com `AttributeError: module 'flowdesk_sdk_t' has no attribute 'progress'`

- [ ] **Step 3: Implementar no `_SDK_SOURCE`**

Em `back/app/services/storage.py`, logo após a função `log` dentro da string `_SDK_SOURCE` (antes do bloco `# ---- PDF / OCR`), inserir:

```python
_RUN_DIR = os.environ.get("FLOWDESK_RUN_DIR", ".")


def progress(etapa, detalhe="") -> None:
    """Etapa visível ao usuário na linha do tempo da execução.
    Use linguagem simples: progress("Lendo extrato", "564 lançamentos")."""
    import datetime as _dt
    rec = {"etapa": str(etapa), "detalhe": str(detalhe),
           "ts": _dt.datetime.now().strftime("%H:%M:%S")}
    p = Path(_RUN_DIR) / "progress.jsonl"
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\\n")
    print(f"[etapa] {etapa} {detalhe}", flush=True)


def get_table(nome) -> list:
    """Linhas (list[dict]) de uma tabela interna do projeto (ex: regras De/Para).
    O runtime materializa as tabelas em tables.json antes da execução."""
    p = Path(_RUN_DIR) / "tables.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get(nome, [])


def read_table(path, **kw):
    """Lê planilha (xlsx/xls/csv) com tolerância a xls fora do padrão (Domínio).
    Cadeia: pandas normal -> conversão via Excel instalado -> erro claro."""
    import pandas as pd
    spath = str(path)
    ext = os.path.splitext(spath)[1].lower()
    if ext == ".csv":
        return pd.read_csv(spath, **kw)
    try:
        return pd.read_excel(spath, **kw)
    except Exception:
        if ext != ".xls":
            raise
    # xls do Domínio: converte com o Excel da máquina (on-premise Windows)
    import subprocess, tempfile
    dst = os.path.join(tempfile.gettempdir(), "fd_conv_" + os.path.basename(spath) + ".xlsx")
    ps = (
        "$x=New-Object -ComObject Excel.Application;$x.Visible=$false;"
        "$x.DisplayAlerts=$false;$wb=$x.Workbooks.Open('{src}');"
        "$wb.SaveAs('{dst}',51);$wb.Close($false);$x.Quit()"
    ).format(src=spath.replace("'", "''"), dst=dst.replace("'", "''"))
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=120)
    if r.returncode != 0 or not os.path.exists(dst):
        raise RuntimeError(
            "Não consegui ler este .xls (formato fora do padrão e a conversão "
            "via Excel falhou). Exporte como .xlsx ou .csv e envie de novo.")
    return pd.read_excel(dst, **kw)
```

Atualizar o docstring de exemplo no topo do `_SDK_SOURCE` para citar `progress` no import de exemplo.

- [ ] **Step 4: Materializar tabelas e run_dir no runner**

Em `back/app/runtime/runner.py`, método `_execute`, logo após `input_path.write_text(...)` (~linha 119), inserir:

```python
            execu.run_dir = str(run_dir)
            # tabelas internas do projeto disponíveis ao script (ex: De/Para)
            from ..models import DataRow, DataTable
            tables: dict[str, list] = {}
            for t in db.query(DataTable).filter(DataTable.project_id == project.id):
                rows = db.query(DataRow).filter(DataRow.table_id == t.id).all()
                tables[t.name] = [r.values for r in rows]
            (run_dir / "tables.json").write_text(
                json.dumps(tables, ensure_ascii=False), encoding="utf-8"
            )
```

- [ ] **Step 5: Rodar testes e ver passar**

Run: `cd back && .venv/Scripts/python.exe -m pytest tests/test_sdk_helpers.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add back/app/services/storage.py back/app/runtime/runner.py back/tests/
git commit -m "feat(sdk): progress(), get_table() e read_table() tolerante a xls Domínio"
```

---

### Task 3: progress no polling de execução (console e app publicado)

**Files:**
- Modify: `back/app/routers/executions.py:66-77` (get_execution)
- Modify: `back/app/routers/published.py` (endpoint `GET /{subdomain}/executions/{execution_id}`)
- Test: `back/qa_suite.py` (seção nova, Task 9 consolida) — verificação manual aqui

- [ ] **Step 1: Helper compartilhado de leitura do progresso**

Em `back/app/services/storage.py` (código do servidor, fora do `_SDK_SOURCE`, junto de `list_dir`), adicionar:

```python
def read_progress(project_id: int, execution_id: str) -> list[dict]:
    """Eventos progress() de uma execução (vazio se não houver)."""
    import json as _json
    p = STORAGE_DIR / str(project_id) / "runs" / execution_id / "progress.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(_json.loads(line))
        except Exception:
            continue
    return out
```

- [ ] **Step 2: Devolver no endpoint do console**

Em `back/app/routers/executions.py`, trocar o `get_execution` para devolver dict com progress (remover `response_model=ExecutionOut` da rota):

```python
@router.get("/projects/{project_id}/executions/{execution_id}")
def get_execution(
    project_id: int,
    execution_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project(db, project_id, user)
    execu = db.get(Execution, execution_id)
    if execu is None or execu.project_id != project_id:
        raise HTTPException(status_code=404, detail="Execução não encontrada")
    data = ExecutionOut.model_validate(execu).model_dump()
    data["progress"] = storage.read_progress(project_id, execution_id)
    return data
```

(adicionar `from ..services import storage` nos imports.)

- [ ] **Step 3: Devolver no endpoint público**

Em `back/app/routers/published.py`, localizar o endpoint `GET /{subdomain}/executions/{execution_id}` (usado pelo polling do app publicado) e acrescentar a mesma chave no dict de resposta: `"progress": storage.read_progress(project.id, execution_id)`.

- [ ] **Step 4: Verificar manualmente**

Com o backend rodando (`back/run-dev.ps1`), rodar um teste de qualquer automação existente e:
Run: `curl -s http://127.0.0.1:8000/api/health`
Expected: `{"status":"ok",...}`; e o GET de uma execução conter `"progress": []` (scripts antigos não emitem ainda).

- [ ] **Step 5: Commit**

```bash
git add back/app/routers/executions.py back/app/routers/published.py back/app/services/storage.py
git commit -m "feat(runtime): linha do tempo progress() exposta no polling de execução"
```

---

### Task 4: Router classify — regras De/Para e sugestão IA com payload mínimo

**Files:**
- Create: `back/app/routers/classify.py`
- Modify: `back/main.py` (import + include no loop de routers)

- [ ] **Step 1: Criar o router completo**

`back/app/routers/classify.py`:

```python
"""Classificação contábil: regras De/Para por projeto + sugestão por IA.

Privacidade (decisão de projeto): para a IA vão APENAS os textos de histórico
dos grupos e a lista de contas candidatas (código + nome). Valores, saldos,
agência/conta e CNPJ nunca saem da máquina.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import DataRow, DataTable, User
from .projects import get_project

router = APIRouter(prefix="/api", tags=["classify"])

REGRAS_TABLE = "regras_classificacao"


def _regras_table(db: Session, project_id: int) -> DataTable:
    t = (
        db.query(DataTable)
        .filter(DataTable.project_id == project_id, DataTable.name == REGRAS_TABLE)
        .first()
    )
    if t is None:
        t = DataTable(project_id=project_id, name=REGRAS_TABLE,
                      columns=["padrao", "conta_codigo", "conta_nome", "origem"])
        db.add(t)
        db.commit()
        db.refresh(t)
    return t


@router.get("/projects/{project_id}/regras-classificacao")
def listar_regras(project_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    t = _regras_table(db, project_id)
    rows = db.query(DataRow).filter(DataRow.table_id == t.id).all()
    return [{"id": r.id, **r.values} for r in rows]


class RegraIn(BaseModel):
    padrao: str
    conta_codigo: str
    conta_nome: str = ""
    origem: str = "revisao"


@router.post("/projects/{project_id}/regras-classificacao")
def salvar_regras(project_id: int, regras: list[RegraIn],
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Upsert por padrão (a correção mais recente vence)."""
    get_project(db, project_id, user)
    t = _regras_table(db, project_id)
    existentes = {r.values.get("padrao"): r for r in
                  db.query(DataRow).filter(DataRow.table_id == t.id)}
    salvas = 0
    for regra in regras:
        padrao = regra.padrao.strip().upper()
        if not padrao or not regra.conta_codigo.strip():
            continue
        values = {"padrao": padrao, "conta_codigo": regra.conta_codigo.strip(),
                  "conta_nome": regra.conta_nome.strip(), "origem": regra.origem}
        if padrao in existentes:
            existentes[padrao].values = values
        else:
            db.add(DataRow(table_id=t.id, values=values))
        salvas += 1
    db.commit()
    return {"ok": True, "salvas": salvas}


@router.delete("/projects/{project_id}/regras-classificacao/{row_id}")
def excluir_regra(project_id: int, row_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    t = _regras_table(db, project_id)
    row = db.get(DataRow, row_id)
    if row is None or row.table_id != t.id:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    db.delete(row)
    db.commit()
    return {"ok": True}


class GrupoIn(BaseModel):
    padrao: str
    tipo: str = ""  # credito | debito


class ContaIn(BaseModel):
    codigo: str
    nome: str


class SugestaoRequest(BaseModel):
    grupos: list[GrupoIn]
    contas: list[ContaIn]


@router.post("/projects/{project_id}/classificar-grupos")
def classificar_grupos(project_id: int, req: SugestaoRequest,
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Sugere conta contábil por grupo de histórico. Payload mínimo para a IA."""
    get_project(db, project_id, user)
    if not req.grupos:
        return {"sugestoes": []}
    if not settings.ai_enabled:
        # modo simulado: heurística por palavra no nome da conta
        sugestoes = []
        for g in req.grupos:
            alvo = next((c for c in req.contas
                         if any(w in c.nome.upper() for w in g.padrao.split()[:2] if len(w) > 4)), None)
            sugestoes.append({"padrao": g.padrao,
                              "conta_codigo": alvo.codigo if alvo else "",
                              "confianca": 0.3 if alvo else 0.0})
        return {"sugestoes": sugestoes}

    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)
    contas_txt = "\n".join(f"{c.codigo} = {c.nome}" for c in req.contas[:400])
    grupos_txt = "\n".join(f"- [{g.tipo}] {g.padrao}" for g in req.grupos)
    prompt = (
        "Você é um contador brasileiro classificando movimentos de extrato bancário "
        "na contrapartida contábil. O lado banco já está resolvido; sugira APENAS a "
        "contrapartida, escolhendo estritamente um código da lista de contas analíticas.\n"
        "Para [credito] (entrada no banco) a contrapartida típica é receita/recebimento; "
        "para [debito] (saída) é despesa/pagamento.\n\n"
        f"CONTAS ANALÍTICAS DISPONÍVEIS:\n{contas_txt}\n\n"
        f"GRUPOS DE HISTÓRICO:\n{grupos_txt}\n\n"
        'Responda SÓ JSON: {"sugestoes": [{"padrao": "...", "conta_codigo": "...", '
        '"confianca": 0.0}]} — confianca entre 0 e 1; conta_codigo vazio se não houver '
        "conta adequada (NUNCA invente código fora da lista)."
    )
    resp = client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    try:
        data = json.loads(resp.choices[0].message.content or "{}")
        sugestoes = data.get("sugestoes", [])
    except json.JSONDecodeError:
        sugestoes = []
    validos = {c.codigo for c in req.contas}
    for s in sugestoes:
        if str(s.get("conta_codigo", "")) not in validos:
            s["conta_codigo"] = ""
            s["confianca"] = 0.0
    return {"sugestoes": sugestoes}
```

- [ ] **Step 2: Registrar no main.py**

Em `back/main.py`: adicionar `classify,` na lista do `from app.routers import (` e `classify,` no loop `for module in (...)`.

- [ ] **Step 3: Verificar sobe e responde**

Run (backend rodando): login + `POST /api/projects/37/classificar-grupos` com `{"grupos":[],"contas":[]}`
Expected: `{"sugestoes": []}`; e `GET /api/projects/37/regras-classificacao` → `[]`.

- [ ] **Step 4: Commit**

```bash
git add back/app/routers/classify.py back/main.py
git commit -m "feat(classify): regras De/Para por projeto e sugestao IA com payload minimo"
```

---

### Task 5: Script de referência (parser Bradesco + classificador + xlsx Domínio) como template da galeria

**Files:**
- Modify: `back/app/routers/templates.py` (nova constante `_EXTRATO_DOMINIO` + entrada no dict `TEMPLATES`)
- Test: `back/tests/test_extrato_dominio.py` (unitário sintético) e `back/tests/test_integracao_real.py` (arquivos reais, skippable)

- [ ] **Step 1: Testes unitários que falham (funções puras extraídas do template)**

O código do template fica numa string, mas as funções puras devem ser importáveis para teste. Criar `back/app/services/extrato_dominio.py` com as funções, e o template importa? Não: o subprocess não enxerga `app.*`. Decisão: o código vive na string do template (auto-contido) e os testes materializam a string num módulo, igual ao SDK. Criar `back/tests/test_extrato_dominio.py`:

```python
import sys
import importlib.util
import datetime as dt
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))


def _load_template_module(tmp_path, monkeypatch):
    from app.routers.templates import TEMPLATES
    from app.services.storage import _SDK_SOURCE
    (tmp_path / "flowdesk_sdk.py").write_text(_SDK_SOURCE, encoding="utf-8")
    code = TEMPLATES["extrato-dominio"]["code"]
    f = tmp_path / "processar.py"
    f.write_text(code, encoding="utf-8")
    run = tmp_path / "run"; run.mkdir()
    (tmp_path / "input.json").write_text('{"_somente_definicoes": true}', encoding="utf-8")
    monkeypatch.setenv("FLOWDESK_INPUT", str(tmp_path / "input.json"))
    monkeypatch.setenv("FLOWDESK_OUTPUT", str(tmp_path / "output.json"))
    monkeypatch.setenv("FLOWDESK_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("FLOWDESK_RUN_DIR", str(run))
    monkeypatch.syspath_prepend(str(tmp_path))
    spec = importlib.util.spec_from_file_location("processar_t", f)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # _somente_definicoes=True faz main() não rodar
    return mod


def test_padrao_remove_numeros(tmp_path, monkeypatch):
    m = _load_template_module(tmp_path, monkeypatch)
    assert m.padrao_de("CIELO VDA DEBITO MASTER 8207205") == "CIELO VDA DEBITO MASTER"
    assert m.padrao_de("REM: JOINT BILLION BRAZIL 01/04") == "REM: JOINT BILLION BRAZIL"
    assert m.padrao_de("TARIFA BANCARIA 300326") == "TARIFA BANCARIA"


def test_gerar_xlsx_contrato_dominio(tmp_path, monkeypatch):
    m = _load_template_module(tmp_path, monkeypatch)
    lanc = [
        {"data": dt.date(2026, 4, 1), "historico": "VENDA CARTAO", "credito": 100.5, "debito": None},
        {"data": dt.date(2026, 4, 1), "historico": "TARIFA", "credito": None, "debito": 8.14},
        {"data": dt.date(2026, 4, 2), "historico": "PIX REC", "credito": 50.0, "debito": None},
    ]
    mapa = {"VENDA CARTAO": "412", "TARIFA": "777", "PIX REC": "413"}
    out = tmp_path / "saida.xlsx"
    m.gerar_xlsx(lanc, mapa, conta_banco="9", caminho=out)
    import openpyxl
    ws = openpyxl.load_workbook(out)["Planilha1"]
    headers = [c.value for c in ws[1]]
    assert headers == ["Data", "Cód. Conta Debito", "Cód. Conta Credito", "Valor",
                       "Cód. Histórico", "Complemento Histórico", "Inicia Lote",
                       "Código Matriz/Filial", "Centro de Custo Débito",
                       "Centro de Custo Crédito"]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    # entrada no banco: débito banco 9 / crédito contrapartida; Inicia Lote=1 só na 1a linha do dia
    assert rows[0][1] == "9" and rows[0][2] == "412" and rows[0][6] == 1
    assert rows[1][1] == "777" and rows[1][2] == "9" and rows[1][6] is None
    assert rows[2][6] == 1  # novo dia 02/04 reinicia lote
    assert rows[0][4] is None  # Cód. Histórico sempre vazio
    assert abs(rows[0][3] - 100.5) < 0.001  # valor numérico


def test_classificar_com_regras_e_ignorar(tmp_path, monkeypatch):
    m = _load_template_module(tmp_path, monkeypatch)
    lanc = [
        {"data": dt.date(2026, 4, 1), "historico": "TARIFA BANCARIA 1", "credito": None, "debito": 5.0},
        {"data": dt.date(2026, 4, 1), "historico": "COISA NOVA 99", "credito": 10.0, "debito": None},
    ]
    regras = {"TARIFA BANCARIA": "777"}
    grupos = m.agrupar(lanc, regras)
    por_padrao = {g["padrao"]: g for g in grupos}
    assert por_padrao["TARIFA BANCARIA"]["conta"] == "777"
    assert por_padrao["TARIFA BANCARIA"]["origem"] == "regra"
    assert por_padrao["COISA NOVA"]["conta"] is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd back && .venv/Scripts/python.exe -m pytest tests/test_extrato_dominio.py -v`
Expected: FAIL com `KeyError: 'extrato-dominio'`

- [ ] **Step 3: Escrever o template completo**

Em `back/app/routers/templates.py`, adicionar a constante (código auto-contido, parser já validado ao centavo contra o extrato real):

```python
_EXTRATO_DOMINIO = '''"""Extrato bancário (PDF Bradesco) -> planilha de lançamentos do Domínio.

Fluxo em 2 passes:
  pass 1 (sem _classificacao_confirmada): lê extrato + plano de contas, aplica
    regras De/Para do projeto e devolve _classificacao_review para a tela de revisão.
  pass 2 (com _classificacao_confirmada): aplica o mapa confirmado, filtra o
    período e gera o xlsx no contrato do Domínio.
"""
import datetime as dt
import re
from flowdesk_sdk import (get_input, get_file, set_output, output_path, log,
                          progress, get_table, read_table)

NUM = re.compile(r"^-?\\d{1,3}(\\.\\d{3})*,\\d{2}$")
DATE = re.compile(r"^\\d{2}/\\d{2}/\\d{4}$")
COLUNAS = ["Data", "Cód. Conta Debito", "Cód. Conta Credito", "Valor",
           "Cód. Histórico", "Complemento Histórico", "Inicia Lote",
           "Código Matriz/Filial", "Centro de Custo Débito", "Centro de Custo Crédito"]


def brl(s):
    return float(s.replace(".", "").replace(",", "."))


def padrao_de(historico):
    """Padrão de agrupamento: histórico sem números/datas (estável entre meses)."""
    toks = [t for t in str(historico).split()
            if not t.replace("/", "").replace("-", "").replace(".", "").isdigit()]
    return " ".join(toks).strip().upper()


def parse_extrato(pdf_path):
    """Parser posicional do extrato Bradesco. Crédito x1<400, débito 400<=x1<490,
    saldo x1>=490 (valores alinhados à direita). Valida pela aritmética do saldo."""
    import pdfplumber
    lanc, saldo_ant, saldo_fim = [], None, None
    data_atual, desc_acum = None, []
    periodo = None
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            linhas = {}
            for w in words:
                linhas.setdefault(round(w["top"]), []).append(w)
            for top in sorted(linhas):
                ws = sorted(linhas[top], key=lambda x: x["x0"])
                texto_linha = " ".join(w["text"] for w in ws)
                m = re.search(r"Entre (\\d{2}/\\d{2}/\\d{4}) e (\\d{2}/\\d{2}/\\d{4})", texto_linha)
                if m and periodo is None:
                    periodo = (m.group(1), m.group(2))
                nums = [w for w in ws if NUM.match(w["text"])]
                saldo_tok = [w for w in nums if w["x1"] >= 490]
                textos = [w["text"] for w in ws
                          if not NUM.match(w["text"]) and not DATE.match(w["text"])]
                dtok = next((w["text"] for w in ws if DATE.match(w["text"])), None)
                if dtok:
                    data_atual = dt.datetime.strptime(dtok, "%d/%m/%Y").date()
                if saldo_tok:
                    saldo = brl(saldo_tok[-1]["text"])
                    inline = [t for t in textos if t.upper() not in ("SALDO", "ANTERIOR", "TOTAL")]
                    desc = " ".join(desc_acum + inline).strip()
                    desc_acum = []
                    cred = next((brl(w["text"]) for w in nums if w["x1"] < 400), None)
                    deb = next((brl(w["text"]) for w in nums if 400 <= w["x1"] < 490), None)
                    eh_rodape = "TOTAL" in " ".join(textos).upper()
                    if cred is None and deb is None:
                        if saldo_ant is None:
                            saldo_ant = saldo
                        saldo_fim = saldo
                        continue
                    if eh_rodape:
                        continue
                    lanc.append({"data": data_atual, "historico": desc,
                                 "credito": round(cred, 2) if cred is not None else None,
                                 "debito": round(abs(deb), 2) if deb is not None else None,
                                 "saldo": saldo})
                    saldo_fim = saldo
                elif textos:
                    desc_acum.append(" ".join(textos))
    # validação aritmética linha a linha (saldo anterior + delta = saldo da linha)
    prev, erros = saldo_ant or 0, 0
    for l in lanc:
        impresso = (l["credito"] or 0) - (l["debito"] or 0)
        if abs(impresso - round(l["saldo"] - prev, 2)) > 0.01:
            erros += 1
        prev = l["saldo"]
    return {"lancamentos": lanc, "saldo_anterior": saldo_ant, "saldo_final": saldo_fim,
            "periodo": periodo, "linhas_inconsistentes": erros}


def carregar_plano(caminho):
    """Plano de contas Domínio: devolve contas analíticas [{codigo, nome, classificacao}].
    Sintéticas têm 'S' na coluna T; o nome fica na coluna do grau correspondente."""
    df = read_table(caminho, header=None)
    contas = []
    for _, row in df.iterrows():
        vals = ["" if v != v else str(v).strip() for v in row.tolist()]  # NaN -> ""
        codigo = vals[0]
        if not codigo or not codigo.replace(".", "").isdigit():
            continue
        if "S" in (vals[3] if len(vals) > 3 else ""):
            continue  # sintética não recebe lançamento
        classif = next((v for v in vals if re.match(r"^\\d+(\\.\\d+)+$", v)), "")
        nome = next((v for v in vals[10:] if v and not v.isdigit()), "")
        if nome:
            contas.append({"codigo": codigo.split(".")[0], "nome": nome,
                           "classificacao": classif})
    return contas


def agrupar(lancamentos, regras):
    """Agrupa por padrão de histórico e aplica regras De/Para (match exato)."""
    grupos = {}
    for i, l in enumerate(lancamentos):
        p = padrao_de(l["historico"])
        g = grupos.setdefault(p, {"padrao": p, "exemplo": l["historico"], "qtd": 0,
                                  "total": 0.0, "tipo": "", "linhas": [],
                                  "conta": None, "conta_nome": "", "origem": None})
        g["qtd"] += 1
        g["total"] = round(g["total"] + (l["credito"] or l["debito"] or 0), 2)
        g["tipo"] = "credito" if l["credito"] else "debito"
        g["linhas"].append(i)
    for g in grupos.values():
        if g["padrao"] in regras:
            g["conta"] = regras[g["padrao"]]
            g["origem"] = "regra"
    return sorted(grupos.values(), key=lambda g: -g["total"])


def gerar_xlsx(lancamentos, mapa, conta_banco, caminho):
    """Contrato Domínio: lançamento simples; Inicia Lote = 1 na primeira linha de
    cada dia; Cód. Histórico vazio; Complemento = histórico do extrato."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Planilha1"
    ws.append(COLUNAS)
    dia_anterior = None
    for l in sorted(lancamentos, key=lambda x: (x["data"], x.get("ordem", 0))):
        conta = mapa.get(padrao_de(l["historico"]))
        if conta in (None, "", "IGNORAR"):
            continue
        inicia = 1 if l["data"] != dia_anterior else None
        dia_anterior = l["data"]
        if l["credito"]:  # entrada: débito banco / crédito contrapartida
            deb, cred, valor = conta_banco, conta, l["credito"]
        else:             # saída: débito contrapartida / crédito banco
            deb, cred, valor = conta, conta_banco, l["debito"]
        ws.append([l["data"], deb, cred, valor, None, l["historico"], inicia,
                   None, None, None])
    for cell in ws["A"]:
        if cell.row > 1:
            cell.number_format = "DD/MM/YYYY"
    wb.save(str(caminho))


def localizar_plano():
    """Plano de contas é ativo do projeto: uploads/plano_contas.* ou similar."""
    import glob, os
    for pat in ("uploads/plano*conta*.*", "uploads/*contas*.*", "uploads/*.xls"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[0]
    return None


def main():
    entrada = get_input()
    progress("Lendo o extrato", "")
    pdf = get_file("arquivo") or get_file()
    if not pdf:
        set_output({"erro": "Envie o PDF do extrato bancário."})
        return
    ext = parse_extrato(pdf)
    lanc = ext["lancamentos"]
    progress("Extrato lido", f"{len(lanc)} lançamentos, período "
             f"{ext['periodo'][0] if ext['periodo'] else '?'} a "
             f"{ext['periodo'][1] if ext['periodo'] else '?'}")
    if ext["linhas_inconsistentes"]:
        log(f"Atenção: {ext['linhas_inconsistentes']} linhas não batem com o saldo.")

    plano_path = localizar_plano()
    if not plano_path:
        set_output({"erro": "Plano de contas não encontrado. Anexe o arquivo do "
                            "plano (xls/xlsx/csv) em uploads/ com 'contas' no nome."})
        return
    progress("Lendo o plano de contas", "")
    contas = carregar_plano(plano_path)
    progress("Plano de contas lido", f"{len(contas)} contas analíticas")

    regras_rows = get_table("regras_classificacao")
    regras = {r["padrao"]: r["conta_codigo"] for r in regras_rows}
    conta_banco = regras.get("_CONTA_BANCO")

    confirmado = entrada.get("_classificacao_confirmada")
    if not confirmado:
        # PASS 1: montar a revisão
        progress("Aplicando suas regras", f"{len(regras)} regras conhecidas")
        grupos = agrupar(lanc, regras)
        com_regra = sum(1 for g in grupos if g["origem"] == "regra")
        progress("Aguardando sua revisão",
                 f"{com_regra} de {len(grupos)} grupos classificados por regra")
        datas = [l["data"] for l in lanc if l["data"]]
        set_output({
            "_classificacao_review": {
                "periodo_detectado": {"inicio": ext["periodo"][0], "fim": ext["periodo"][1]}
                                     if ext["periodo"] else
                                     {"inicio": min(datas).strftime("%d/%m/%Y"),
                                      "fim": max(datas).strftime("%d/%m/%Y")},
                "conta_banco": conta_banco,
                "grupos": [{k: g[k] for k in
                            ("padrao", "exemplo", "qtd", "total", "tipo",
                             "conta", "conta_nome", "origem")} for g in grupos],
                "contas": contas,
                "total_lancamentos": len(lanc),
            },
            "resumo": {"lancamentos_no_extrato": len(lanc),
                       "grupos": len(grupos), "classificados_por_regra": com_regra},
        })
        return

    # PASS 2: gerar a planilha com o mapa confirmado
    mapa = {str(k).upper(): str(v) for k, v in confirmado.items()}
    conta_banco = entrada.get("_conta_banco") or conta_banco
    if not conta_banco:
        set_output({"erro": "Conta do banco não informada na revisão."})
        return
    periodo = entrada.get("_periodo") or {}
    ini = dt.datetime.strptime(periodo["inicio"], "%d/%m/%Y").date() if periodo.get("inicio") else None
    fim = dt.datetime.strptime(periodo["fim"], "%d/%m/%Y").date() if periodo.get("fim") else None
    progress("Filtrando pela competência",
             f"{periodo.get('inicio', '')} a {periodo.get('fim', '')}")
    no_periodo = [l for l in lanc if l["data"] and
                  (ini is None or l["data"] >= ini) and (fim is None or l["data"] <= fim)]
    fora = len(lanc) - len(no_periodo)
    ignorados = sum(1 for l in no_periodo
                    if mapa.get(padrao_de(l["historico"])) in (None, "", "IGNORAR"))
    progress("Gerando a planilha do Domínio", f"{len(no_periodo) - ignorados} lançamentos")
    out = output_path("lancamentos_dominio.xlsx")
    gerar_xlsx(no_periodo, mapa, conta_banco, out)
    tot_cred = round(sum(l["credito"] or 0 for l in no_periodo
                         if mapa.get(padrao_de(l["historico"])) not in (None, "", "IGNORAR")), 2)
    tot_deb = round(sum(l["debito"] or 0 for l in no_periodo
                        if mapa.get(padrao_de(l["historico"])) not in (None, "", "IGNORAR")), 2)
    progress("Pronto", f"créditos R$ {tot_cred:,.2f} | débitos R$ {tot_deb:,.2f}")
    set_output({
        "arquivo_resultado": str(out),
        "resumo": {"lancamentos_importados": len(no_periodo) - ignorados,
                   "fora_da_competencia": fora, "ignorados_na_revisao": ignorados,
                   "total_creditos": tot_cred, "total_debitos": tot_deb},
    })


if not get_input().get("_somente_definicoes"):
    main()
'''
```

E no dict `TEMPLATES` (mesma estrutura dos 3 existentes), adicionar:

```python
    "extrato-dominio": {
        "name": "Extrato bancário para lançamentos (Domínio)",
        "description": "Lê o extrato em PDF, classifica cada lançamento com suas "
                       "regras e revisão assistida por IA, e gera a planilha de "
                       "importação de lançamentos contábeis do Domínio.",
        "input_fields": [{"name": "arquivo", "label": "Extrato bancário (PDF)", "type": "file"}],
        "code": _EXTRATO_DOMINIO,
    },
```

- [ ] **Step 4: Rodar testes unitários e ver passar**

Run: `cd back && .venv/Scripts/python.exe -m pytest tests/test_extrato_dominio.py -v`
Expected: 3 passed

- [ ] **Step 5: Teste de integração com os arquivos reais (skippable, dados ficam fora do git)**

Criar `back/tests/test_integracao_real.py`:

```python
"""Integração com arquivos reais de cliente (existem só nesta máquina; pula no CI)."""
import sys
import importlib.util
from pathlib import Path

import pytest

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

PDF = BACK / "storage" / "37" / "uploads" / "JBB GIG - EXTRATO BRADESCO 04.2026.pdf"
CONTAS = Path(r"C:\\Users\\mbrasiliense98\\Downloads\\Contas.xls")

pytestmark = pytest.mark.skipif(
    not (PDF.exists() and CONTAS.exists()), reason="arquivos reais ausentes"
)


def _mod(tmp_path, monkeypatch):
    from tests.test_extrato_dominio import _load_template_module
    return _load_template_module(tmp_path, monkeypatch)


def test_parser_fecha_ao_centavo(tmp_path, monkeypatch):
    m = _mod(tmp_path, monkeypatch)
    ext = m.parse_extrato(PDF)
    lanc = ext["lancamentos"]
    assert len(lanc) > 500
    assert ext["linhas_inconsistentes"] == 0
    calc = ext["saldo_anterior"] + sum(l["credito"] or 0 for l in lanc) - sum(l["debito"] or 0 for l in lanc)
    assert abs(calc - ext["saldo_final"]) < 0.01
    assert ext["periodo"] == ("01/04/2026", "30/04/2026")


def test_plano_de_contas_real(tmp_path, monkeypatch):
    m = _mod(tmp_path, monkeypatch)
    contas = m.carregar_plano(str(CONTAS))
    assert len(contas) > 500
    bradesco = [c for c in contas if "BRADESCO" in c["nome"].upper()]
    assert any(c["codigo"] == "9" for c in bradesco)
    assert all(c["codigo"].isdigit() for c in contas)
```

Run: `cd back && .venv/Scripts/python.exe -m pytest tests/ -v`
Expected: todos passed (integração roda nesta máquina).

- [ ] **Step 6: Commit**

```bash
git add back/app/routers/templates.py back/tests/
git commit -m "feat(template): extrato Bradesco -> lancamentos Dominio com revisao em 2 passes"
```

---

### Task 6: Front — tipos e ProgressTimeline

**Files:**
- Modify: `front/src/lib/types.ts`
- Create: `front/src/components/ProgressTimeline.tsx`

- [ ] **Step 1: Tipos**

Em `front/src/lib/types.ts`, adicionar ao tipo `Execution` o campo `progress?: ProgressEvent[];` e exportar:

```typescript
export interface ProgressEvent {
  etapa: string;
  detalhe: string;
  ts: string;
}

export interface GrupoClassificacao {
  padrao: string;
  exemplo: string;
  qtd: number;
  total: number;
  tipo: "credito" | "debito" | "";
  conta: string | null;
  conta_nome: string;
  origem: "regra" | "ia" | null;
}

export interface ContaPlano {
  codigo: string;
  nome: string;
  classificacao: string;
}

export interface ClassificacaoReviewData {
  periodo_detectado: { inicio: string; fim: string };
  conta_banco: string | null;
  grupos: GrupoClassificacao[];
  contas: ContaPlano[];
  total_lancamentos: number;
}
```

- [ ] **Step 2: Componente ProgressTimeline**

Criar `front/src/components/ProgressTimeline.tsx`:

```tsx
import type { ProgressEvent } from "../lib/types";
import { Spinner } from "./ui";

/** Linha do tempo "o que a automação está fazendo", em linguagem simples. */
export default function ProgressTimeline({
  events,
  running,
}: {
  events: ProgressEvent[];
  running: boolean;
}) {
  if (!events.length && !running) return null;
  return (
    <ol className="mt-3 space-y-1.5" aria-label="Etapas da execução">
      {events.map((e, i) => {
        const isLast = i === events.length - 1;
        return (
          <li key={i} className="flex items-start gap-2 text-sm">
            {isLast && running ? (
              <Spinner className="mt-0.5 h-3.5 w-3.5 text-accent-600" />
            ) : (
              <svg viewBox="0 0 24 24" className="mt-0.5 h-3.5 w-3.5 text-emerald-500"
                fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"
                strokeLinejoin="round" aria-hidden>
                <polyline points="20 6 9 17 4 12" />
              </svg>
            )}
            <span className="text-slate-700">{e.etapa}</span>
            {e.detalhe && <span className="text-slate-400">{e.detalhe}</span>}
            <span className="ml-auto text-[10px] text-slate-300">{e.ts}</span>
          </li>
        );
      })}
      {running && events.length === 0 && (
        <li className="flex items-center gap-2 text-sm text-slate-500">
          <Spinner className="h-3.5 w-3.5 text-accent-600" /> Iniciando…
        </li>
      )}
    </ol>
  );
}
```

- [ ] **Step 3: Type-check**

Run: `cd front && npx tsc --noEmit`
Expected: exit 0

- [ ] **Step 4: Commit**

```bash
git add front/src/lib/types.ts front/src/components/ProgressTimeline.tsx
git commit -m "feat(front): tipos de progresso/revisao e componente ProgressTimeline"
```

---

### Task 7: Front — ClassificacaoReview (semáforo)

**Files:**
- Create: `front/src/components/ClassificacaoReview.tsx`

- [ ] **Step 1: Componente completo**

Regras do design (decididas no grill): verde = regra, passa direto; âmbar = sugestão de IA, exige confirmação; vermelho = sem sugestão, obriga escolha; "Ignorar grupo"; busca só em contas analíticas; período editável pré-preenchido; conta do banco obrigatória; confirmar só habilita sem vermelhos e sem âmbar pendente.

```tsx
import { useMemo, useState } from "react";
import type {
  ClassificacaoReviewData,
  ContaPlano,
  GrupoClassificacao,
} from "../lib/types";

interface Escolha {
  conta: string | null; // codigo, "IGNORAR" ou null (pendente)
  confirmado: boolean;
  origem: "regra" | "ia" | "manual" | null;
  confianca?: number;
}

/** Revisão da classificação contábil antes de gerar a planilha do Domínio. */
export default function ClassificacaoReview({
  data,
  sugestoesIa,
  busy,
  onConfirm,
}: {
  data: ClassificacaoReviewData;
  /** padrao -> {conta_codigo, confianca}, vindas do endpoint classificar-grupos */
  sugestoesIa: Record<string, { conta_codigo: string; confianca: number }>;
  busy: boolean;
  onConfirm: (payload: {
    mapa: Record<string, string>;
    contaBanco: string;
    periodo: { inicio: string; fim: string };
    novasRegras: { padrao: string; conta_codigo: string; conta_nome: string }[];
  }) => void;
}) {
  const contasPorCodigo = useMemo(
    () => Object.fromEntries(data.contas.map((c) => [c.codigo, c])),
    [data.contas]
  );
  const [escolhas, setEscolhas] = useState<Record<string, Escolha>>(() => {
    const init: Record<string, Escolha> = {};
    for (const g of data.grupos) {
      if (g.origem === "regra" && g.conta) {
        init[g.padrao] = { conta: g.conta, confirmado: true, origem: "regra" };
      } else {
        const s = sugestoesIa[g.padrao];
        init[g.padrao] = s?.conta_codigo
          ? { conta: s.conta_codigo, confirmado: false, origem: "ia", confianca: s.confianca }
          : { conta: null, confirmado: false, origem: null };
      }
    }
    return init;
  });
  const [contaBanco, setContaBanco] = useState(data.conta_banco || "");
  const [inicio, setInicio] = useState(data.periodo_detectado.inicio);
  const [fim, setFim] = useState(data.periodo_detectado.fim);
  const [lembrar, setLembrar] = useState(true);

  function definir(padrao: string, conta: string) {
    setEscolhas((e) => ({
      ...e,
      [padrao]: { conta, confirmado: true, origem: "manual" },
    }));
  }
  function confirmarSugestao(padrao: string) {
    setEscolhas((e) => ({ ...e, [padrao]: { ...e[padrao], confirmado: true } }));
  }

  const pendentes = data.grupos.filter((g) => {
    const e = escolhas[g.padrao];
    return !e?.conta || !e.confirmado;
  });
  const pronto = pendentes.length === 0 && !!contaBanco.trim();

  function confirmar() {
    const mapa: Record<string, string> = {};
    const novasRegras: { padrao: string; conta_codigo: string; conta_nome: string }[] = [];
    for (const g of data.grupos) {
      const e = escolhas[g.padrao];
      if (!e?.conta) continue;
      mapa[g.padrao] = e.conta;
      if (lembrar && e.origem !== "regra" && e.conta !== "IGNORAR") {
        novasRegras.push({
          padrao: g.padrao,
          conta_codigo: e.conta,
          conta_nome: contasPorCodigo[e.conta]?.nome || "",
        });
      }
    }
    if (lembrar && contaBanco && contaBanco !== data.conta_banco) {
      novasRegras.push({ padrao: "_CONTA_BANCO", conta_codigo: contaBanco, conta_nome: "Conta do banco" });
    }
    onConfirm({ mapa, contaBanco, periodo: { inicio, fim }, novasRegras });
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <h4 className="text-sm font-bold text-brand-900">Revisão da classificação</h4>
      <p className="mt-0.5 text-xs text-slate-500">
        {data.total_lancamentos} lançamentos em {data.grupos.length} grupos. Verde veio
        das suas regras; âmbar é sugestão da IA (confirme); vermelho precisa de conta.
      </p>

      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        <label className="text-xs text-slate-600">
          Conta do banco (lado banco)
          <ContaSelect contas={data.contas} value={contaBanco} onChange={setContaBanco} />
        </label>
        <label className="text-xs text-slate-600">
          Competência: início
          <input className="input mt-1 py-1.5 text-sm" value={inicio}
            onChange={(e) => setInicio(e.target.value)} placeholder="dd/mm/aaaa" />
        </label>
        <label className="text-xs text-slate-600">
          Competência: fim
          <input className="input mt-1 py-1.5 text-sm" value={fim}
            onChange={(e) => setFim(e.target.value)} placeholder="dd/mm/aaaa" />
        </label>
      </div>

      <div className="mt-3 max-h-80 space-y-2 overflow-auto pr-1">
        {data.grupos.map((g) => (
          <GrupoRow key={g.padrao} grupo={g} escolha={escolhas[g.padrao]}
            contas={data.contas} contasPorCodigo={contasPorCodigo}
            onEscolher={(c) => definir(g.padrao, c)}
            onConfirmar={() => confirmarSugestao(g.padrao)} />
        ))}
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3">
        <label className="flex items-center gap-1.5 text-xs text-slate-500">
          <input type="checkbox" checked={lembrar} onChange={(e) => setLembrar(e.target.checked)}
            className="h-3.5 w-3.5 accent-brand-600" />
          Lembrar destas escolhas para as próximas execuções
        </label>
        <button onClick={confirmar} disabled={!pronto || busy}
          className="btn-accent py-2 text-sm disabled:opacity-40"
          title={pronto ? "" : "Defina a conta do banco e resolva os grupos pendentes"}>
          {busy ? "Gerando…" : `Confirmar classificação e gerar planilha`}
        </button>
      </div>
      {!pronto && (
        <p className="mt-1 text-right text-xs text-amber-600">
          {pendentes.length > 0 && `${pendentes.length} grupo(s) pendente(s). `}
          {!contaBanco.trim() && "Informe a conta do banco."}
        </p>
      )}
    </div>
  );
}

function GrupoRow({ grupo, escolha, contas, contasPorCodigo, onEscolher, onConfirmar }: {
  grupo: GrupoClassificacao;
  escolha: Escolha;
  contas: ContaPlano[];
  contasPorCodigo: Record<string, ContaPlano>;
  onEscolher: (conta: string) => void;
  onConfirmar: () => void;
}) {
  const cor = !escolha?.conta
    ? "border-red-200 bg-red-50"
    : escolha.confirmado
      ? "border-emerald-200 bg-emerald-50/60"
      : "border-amber-200 bg-amber-50";
  const valor = grupo.total.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  return (
    <div className={`rounded-lg border p-2.5 ${cor}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-brand-900" title={grupo.exemplo}>
            {grupo.padrao || "(sem histórico)"}
          </div>
          <div className="text-[11px] text-slate-500">
            {grupo.qtd} lançamento(s) · {valor} · {grupo.tipo === "credito" ? "entrada" : "saída"}
            {escolha?.origem === "regra" && " · sua regra"}
            {escolha?.origem === "ia" &&
              ` · IA ${(escolha.confianca ? Math.round(escolha.confianca * 100) : 0)}%`}
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <ContaSelect contas={contas} value={escolha?.conta === "IGNORAR" ? "" : escolha?.conta || ""}
            onChange={onEscolher} compact />
          {escolha?.conta && !escolha.confirmado && (
            <button onClick={onConfirmar} className="btn-accent px-2 py-1 text-xs">OK</button>
          )}
          <button onClick={() => onEscolher("IGNORAR")}
            className={`rounded-md px-2 py-1 text-xs ${escolha?.conta === "IGNORAR"
              ? "bg-slate-700 text-white" : "text-slate-400 hover:bg-slate-100"}`}
            title="Não importar este grupo">
            Ignorar
          </button>
        </div>
      </div>
      {escolha?.conta && escolha.conta !== "IGNORAR" && (
        <div className="mt-1 text-[11px] text-slate-600">
          → {escolha.conta} {contasPorCodigo[escolha.conta]?.nome || ""}
        </div>
      )}
      {escolha?.conta === "IGNORAR" && (
        <div className="mt-1 text-[11px] text-slate-500">→ fora da planilha (ignorado)</div>
      )}
    </div>
  );
}

function ContaSelect({ contas, value, onChange, compact = false }: {
  contas: ContaPlano[];
  value: string;
  onChange: (codigo: string) => void;
  compact?: boolean;
}) {
  const [busca, setBusca] = useState("");
  const [aberto, setAberto] = useState(false);
  const filtradas = useMemo(() => {
    const q = busca.trim().toLowerCase();
    if (!q) return contas.slice(0, 30);
    return contas.filter((c) =>
      c.nome.toLowerCase().includes(q) || c.codigo.includes(q) || c.classificacao.includes(q)
    ).slice(0, 30);
  }, [contas, busca]);
  return (
    <div className="relative">
      <input
        className={`input ${compact ? "w-48 py-1 text-xs" : "mt-1 py-1.5 text-sm"}`}
        placeholder={value ? `${value}` : "Buscar conta…"}
        value={busca}
        onFocus={() => setAberto(true)}
        onBlur={() => setTimeout(() => setAberto(false), 150)}
        onChange={(e) => { setBusca(e.target.value); setAberto(true); }}
      />
      {aberto && (
        <div className="absolute z-20 mt-1 max-h-48 w-72 overflow-auto rounded-lg border border-slate-200 bg-white shadow-lg">
          {filtradas.map((c) => (
            <button key={c.codigo} type="button"
              onMouseDown={() => { onChange(c.codigo); setBusca(""); setAberto(false); }}
              className="block w-full px-2.5 py-1.5 text-left text-xs hover:bg-brand-50">
              <span className="font-mono text-brand-700">{c.codigo}</span>{" "}
              <span className="text-slate-700">{c.nome}</span>
              <span className="ml-1 text-slate-300">{c.classificacao}</span>
            </button>
          ))}
          {filtradas.length === 0 && (
            <div className="px-2.5 py-2 text-xs text-slate-400">Nenhuma conta encontrada.</div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd front && npx tsc --noEmit`
Expected: exit 0

- [ ] **Step 3: Commit**

```bash
git add front/src/components/ClassificacaoReview.tsx
git commit -m "feat(front): tela de revisao de classificacao com semaforo, busca de contas e ignorar grupo"
```

---

### Task 8: Integração no TestPanel do assistente (Wizard.tsx)

**Files:**
- Modify: `front/src/pages/Wizard.tsx` (TestPanel, ~linhas 1228-1520)

- [ ] **Step 1: runTest aceita payload extra e atualiza exec a cada tick**

No `TestPanel`, refatorar a assinatura de `runTest` (compatível com o uso existente do OcrReview):

```tsx
  async function runTest(extra?: Record<string, unknown> | string): Promise<Execution> {
    const extraPayload: Record<string, unknown> =
      typeof extra === "string" ? { _texto_corrigido: extra } : (extra ?? {});
    if (typeof extra === "string") setCorrectedText(extra);
    setTesting(true);
    setExec(null);
    setReviewed(false);
    onFlow?.("input", "running");
    try {
      await new Promise((r) => setTimeout(r, 450));
      onFlow?.("script", "running");
      const started = await api.post<Execution>(
        `/api/projects/${projectId}/stages/${scriptStageId}/run`,
        { ...buildPayload(), ...extraPayload }
      );
      let last = started;
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        last = await api.get<Execution>(`/api/projects/${projectId}/executions/${started.id}`);
        setExec(last); // atualiza a linha do tempo ao vivo
        if (last.status === "success" || last.status === "error") break;
      }
      onFlow?.(last.status === "success" ? "result" : "script",
        last.status === "success" ? "success" : "error");
      return last;
    } catch (e: any) {
      const errExec = { status: "error", stderr: e?.message || "Falha ao iniciar o teste." } as Execution;
      setExec(errExec);
      onFlow?.("script", "error");
      return errExec;
    } finally {
      setTesting(false);
    }
  }
```

(`buildPayload` perde o parâmetro `textoCorrigido`; o `_texto_corrigido` agora entra via `extraPayload`. Ajustar `buildPayload` para não receber argumento e remover a linha `const extra = texto ? ... : {}` que dependia dele — manter `correctedText` aplicado dentro de `buildPayload` como hoje, só que sem parâmetro.)

- [ ] **Step 2: Estados e dados da revisão**

Dentro do `TestPanel`, junto dos `useState` existentes:

```tsx
  const [sugestoesIa, setSugestoesIa] = useState<Record<string, { conta_codigo: string; confianca: number }>>({});
  const classifReview = exec?.output_data?._classificacao_review as
    ClassificacaoReviewData | undefined;
```

E um efeito que pede sugestões de IA quando chega uma revisão com grupos sem regra:

```tsx
  useEffect(() => {
    if (!classifReview) return;
    const semRegra = classifReview.grupos.filter((g) => !g.conta);
    if (semRegra.length === 0) { setSugestoesIa({}); return; }
    api.post<{ sugestoes: { padrao: string; conta_codigo: string; confianca: number }[] }>(
      `/api/projects/${projectId}/classificar-grupos`,
      {
        grupos: semRegra.map((g) => ({ padrao: g.padrao, tipo: g.tipo })),
        contas: classifReview.contas.map((c) => ({ codigo: c.codigo, nome: c.nome })),
      }
    ).then((r) => {
      setSugestoesIa(Object.fromEntries(
        r.sugestoes.filter((s) => s.conta_codigo).map((s) => [s.padrao, s])
      ));
    }).catch(() => setSugestoesIa({}));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classifReview ? exec?.id : null]);
```

Imports novos no topo do arquivo: `ClassificacaoReviewData` em `../lib/types`, `ProgressTimeline` e `ClassificacaoReview` em `../components/...`, e `useEffect` já existe.

- [ ] **Step 3: Render**

Logo após o botão "Testar agora" (antes do bloco `<AnimatePresence>{exec && ...}`), renderizar a timeline:

```tsx
      <ProgressTimeline events={exec?.progress ?? []} running={testing} />
```

E dentro do bloco de sucesso (`passed ? (...)`), depois do `</div>` da caixa verde/âmbar, renderizar a revisão quando existir (a revisão substitui o aviso de "resultado vazio", então a condição `looksEmpty` passa a ser `looksEmpty && !classifReview`):

```tsx
            {passed && classifReview && (
              <div className="mt-3">
                <ClassificacaoReview
                  data={classifReview}
                  sugestoesIa={sugestoesIa}
                  busy={testing}
                  onConfirm={async ({ mapa, contaBanco, periodo, novasRegras }) => {
                    if (novasRegras.length) {
                      await api.post(`/api/projects/${projectId}/regras-classificacao`, novasRegras);
                    }
                    await runTest({
                      _classificacao_confirmada: mapa,
                      _conta_banco: contaBanco,
                      _periodo: periodo,
                    });
                  }}
                />
              </div>
            )}
```

Atenção à coerência: na linha do `looksEmpty` (caixa âmbar), trocar a condição para `looksEmpty && !classifReview` nos dois lugares onde aparece (título e gate do publicar usa `looksEmpty` também: em `disabled={...|| looksEmpty ||...}` trocar por `(looksEmpty && !classifReview)`), porque o pass 1 da revisão não gera arquivo e não pode ser tratado como falha.

- [ ] **Step 4: Type-check e smoke**

Run: `cd front && npx tsc --noEmit`
Expected: exit 0

- [ ] **Step 5: Commit**

```bash
git add front/src/pages/Wizard.tsx
git commit -m "feat(assistente): timeline ao vivo e revisao de classificacao no painel de teste"
```

---

### Task 9: Integração no app publicado (PublishedApp.tsx + endpoint de regras token-gated)

**Files:**
- Modify: `front/src/pages/PublishedApp.tsx`
- Modify: `back/app/routers/published.py`

- [ ] **Step 1: Endpoint de regras no published.py**

Adicionar (mesma materialização do classify, mas autenticado pelo token do app):

```python
@router.post("/{subdomain}/regras-classificacao")
def app_salvar_regras(subdomain: str, body: dict, token: str | None = None,
                      db: Session = Depends(get_db)):
    project = _get_live_project(db, subdomain)
    _require_app_user(db, subdomain, token)
    from .classify import RegraIn, salvar_regras_interno  # reuso
    regras = [RegraIn(**r) for r in body.get("regras", [])]
    return salvar_regras_interno(db, project.id, regras)
```

Para isso, em `classify.py`, extrair o corpo do `salvar_regras` para uma função `salvar_regras_interno(db, project_id, regras: list[RegraIn])` chamada pelos dois endpoints (o do console passa a delegar para ela).

- [ ] **Step 2: PublishedApp — timeline e revisão**

Em `front/src/pages/PublishedApp.tsx`:

1. Estado novo: `const [progress, setProgress] = useState<any[]>([]);` e `const [review, setReview] = useState<any | null>(null);` e `const [lastInput, setLastInput] = useState<any>(null);` e `const [sugestoesIa, setSugestoesIa] = useState<Record<string, any>>({});`
2. No `pollExecution`, a cada tick: `setProgress(ex.progress || []);` e no sucesso, antes de `setPhase("result")`: se `ex.output_data?._classificacao_review` existir, `setReview(ex.output_data._classificacao_review); setLastInput(ex.input_data); setPhase("review_classif");` e pedir sugestões IA: como o app publicado não tem token do console, as sugestões já devem ter vindo... **Decisão de simplicidade (v1): no app publicado não há chamada de IA; grupos sem regra aparecem vermelhos e o usuário escolhe manualmente.** A IA roda no assistente (onde o operador IRKO monta e testa); no publicado, com as regras já aprendidas, quase tudo entra verde. Registrar essa diferença no texto da tela: "Sem sugestão automática aqui: escolha a conta ou peça ao time que rode no assistente."
3. Na fase `"processing"`, renderizar `<ProgressTimeline events={progress} running />` abaixo do spinner.
4. Nova fase no render:

```tsx
      {phase === "review_classif" && review && (
        <ClassificacaoReview
          data={review}
          sugestoesIa={{}}
          busy={busy}
          onConfirm={async ({ mapa, contaBanco, periodo, novasRegras }) => {
            setBusy(true);
            if (novasRegras.length) {
              await fetch(`${base}/regras-classificacao?token=${token}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ regras: novasRegras }),
              }).catch(() => {});
            }
            const fd = new FormData();
            fd.append("token", token!);
            fd.append("payload", JSON.stringify({
              ...lastInput,
              _classificacao_confirmada: mapa,
              _conta_banco: contaBanco,
              _periodo: periodo,
            }));
            fd.append("file_fields", JSON.stringify([]));
            const res = await fetch(`${base}/stages/${stage!.id}/submit`, {
              method: "POST", body: fd,
            }).then((r) => r.json());
            setBusy(false);
            setReview(null);
            if (res.status === "processing") {
              setPhase("processing");
              pollExecution(res.execution_id, res.result_stage_id);
            }
          }}
        />
      )}
```

5. Tipo da fase: `useState<"form" | "processing" | "review_classif" | "result" | "done">`.
6. Imports: `ProgressTimeline`, `ClassificacaoReview`.

- [ ] **Step 3: Type-check**

Run: `cd front && npx tsc --noEmit`
Expected: exit 0

- [ ] **Step 4: Commit**

```bash
git add front/src/pages/PublishedApp.tsx back/app/routers/published.py back/app/routers/classify.py
git commit -m "feat(app-publicado): timeline de execucao e revisao de classificacao com regras token-gated"
```

---

### Task 10: Entrevista profunda e narração no prompt do agente

**Files:**
- Modify: `back/app/routers/chat.py` (SYSTEM_PROMPT)

- [ ] **Step 1: Acrescentar ao SYSTEM_PROMPT**

Dentro da string `SYSTEM_PROMPT`, após o bloco do "PROCESSO OBRIGATÓRIO — ENTREVISTA", acrescentar:

```text
PROFUNDIDADE DA ENTREVISTA (REGRA DE OURO — NA DÚVIDA, PERGUNTE):
- Desça até o nível de CONTRATO do resultado: se a saída alimenta outro sistema \
(ex: importação do Domínio, SAP, ERP), pergunte o significado de cada coluna que \
não for óbvia, formatos de data/valor, e regras como numeração de lote. Exemplo \
real: "No Domínio, como funciona a coluna Inicia Lote?" — a resposta muda o código.
- SEMPRE ofereça sua recomendação fundamentada junto da pergunta ("recommended"), \
mas deixe o usuário decidir. Nunca assuma silenciosamente.
- NARRE o que você fez a cada passo, com números concretos: "Li o extrato: 564 \
lançamentos, 01/04 a 30/04" / "Li o plano de contas: 1.387 contas analíticas". \
O usuário precisa VER o progresso, não confiar às cegas.

RECURSOS DO SDK PARA AUTOMAÇÕES CONTÁBEIS (use quando fizer sentido):
- progress(etapa, detalhe): linha do tempo visível ao usuário durante a execução. \
Emita em TODA etapa relevante de scripts longos.
- get_table("regras_classificacao"): regras De/Para aprendidas do projeto \
(lista de {padrao, conta_codigo}). Use para classificação contábil.
- read_table(caminho): planilha xlsx/xls/csv com tolerância a xls legado (Domínio).
- Revisão humana de classificação: pass 1 devolve set_output({"_classificacao_review": \
{...}}) SEM gerar arquivo; a interface mostra a revisão; pass 2 chega com \
"_classificacao_confirmada" (mapa padrao->conta), "_conta_banco" e "_periodo" no \
input. Siga o contrato do modelo "extrato-dominio" da galeria.
```

- [ ] **Step 2: Verificação rápida do prompt**

Run: `cd back && .venv/Scripts/python.exe -c "from app.routers.chat import SYSTEM_PROMPT; assert 'Inicia Lote' in SYSTEM_PROMPT and 'progress(' in SYSTEM_PROMPT; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add back/app/routers/chat.py
git commit -m "feat(agente): entrevista em profundidade de contrato, narracao com numeros e contrato de revisao no prompt"
```

---

### Task 11: qa_suite, E2E real, doc de arquitetura e push

**Files:**
- Modify: `back/qa_suite.py`
- Modify: `docs/Arquitetura-FlowDesk.html` (+ regerar PDF)

- [ ] **Step 1: Seções novas no qa_suite**

Seguindo o padrão das seções existentes (login admin + `check(...)`), adicionar ao final, antes do resumo:

```python
    # ---- Classificacao contabil (regras + sugestao) ----
    section("Classificacao contabil")
    r = post(f"/api/projects/{pid}/regras-classificacao",
             [{"padrao": "TARIFA BANCARIA QA", "conta_codigo": "777", "conta_nome": "Despesas QA"}])
    check("salvar regra De/Para", r.status_code == 200 and r.json().get("salvas") == 1)
    r = get(f"/api/projects/{pid}/regras-classificacao")
    check("listar regras", r.status_code == 200 and
          any(x["padrao"] == "TARIFA BANCARIA QA" for x in r.json()))
    rid = next(x["id"] for x in r.json() if x["padrao"] == "TARIFA BANCARIA QA")
    r = post(f"/api/projects/{pid}/regras-classificacao",
             [{"padrao": "TARIFA BANCARIA QA", "conta_codigo": "888"}])
    check("upsert da regra (padrao repetido atualiza)", r.status_code == 200)
    r = delete(f"/api/projects/{pid}/regras-classificacao/{rid}")
    check("excluir regra", r.status_code == 200)
    r = post(f"/api/projects/{pid}/classificar-grupos", {"grupos": [], "contas": []})
    check("classificar-grupos vazio -> []", r.status_code == 200 and r.json()["sugestoes"] == [])

    # ---- Template extrato-dominio ----
    section("Modelo extrato-dominio")
    r = get("/api/templates")
    check("galeria contem extrato-dominio",
          any(t["key"] == "extrato-dominio" for t in r.json()))
    r = post("/api/templates/extrato-dominio/instantiate", {})
    check("instanciar extrato-dominio", r.status_code == 200 and r.json().get("project_id"))
```

(usar os helpers `get/post/delete/section/check` já definidos no arquivo; `pid` = projeto QA criado pela suíte.)

- [ ] **Step 2: Rodar a suíte completa**

Run: `cd back && .venv/Scripts/python.exe qa_suite.py`
Expected: todas as seções passando (74 + novas).

- [ ] **Step 3: E2E com os arquivos reais no navegador**

1. Instanciar "Extrato bancário para lançamentos (Domínio)" pela galeria do Console.
2. No projeto novo, subir `Contas.xls` para `uploads/` (tela Arquivos ou chat) com nome `plano_contas.xls`.
3. No assistente, subir o PDF do extrato e Testar: deve aparecer timeline ("Lendo o extrato" → "Extrato lido: 564 lançamentos...") e a revisão com grupos.
4. Definir conta do banco (buscar "Bradesco" → 9), confirmar alguns grupos, usar Ignorar em um, confirmar: pass 2 gera `lancamentos_dominio.xlsx`, baixar pelo botão do teste.
5. Abrir o xlsx baixado e conferir: colunas idênticas ao modelo, Inicia Lote = 1 a cada novo dia, Cód. Histórico vazio, totais do resumo = totais do extrato (menos ignorados).
6. Rodar de novo o teste: grupos confirmados devem vir verdes (regras aprendidas).

- [ ] **Step 4: Atualizar o documento de arquitetura (regra permanente)**

Em `docs/Arquitetura-FlowDesk.html`: na seção 6 (runtime), citar `progress()` e a materialização de `tables.json`; na seção 7 (IA), citar a classificação contábil com payload mínimo e a revisão com semáforo; na seção do SDK (características relevantes), acrescentar `progress`, `get_table`, `read_table`. Regerar o PDF:

```powershell
$chrome="C:\Program Files\Google\Chrome\Application\chrome.exe"
$html="C:\Users\mbrasiliense98\Documents\Biulder IRKO\Biulder_claude\flowdesk\docs\Arquitetura-FlowDesk.html"
$pdf="C:\Users\mbrasiliense98\Documents\Biulder IRKO\Biulder_claude\flowdesk\docs\Arquitetura-FlowDesk.pdf"
& $chrome --headless=new --disable-gpu --no-pdf-header-footer --virtual-time-budget=8000 --run-all-compositor-stages-before-draw --print-to-pdf="$pdf" ([System.Uri]$html).AbsoluteUri
```

- [ ] **Step 5: Commit final e push**

```bash
git add -A
git commit -m "test(qa): classificacao contabil e modelo extrato-dominio; docs de arquitetura em dia

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push -u origin feat/extrato-dominio
```

- [ ] **Step 6: Handoff ao usuário (aceite do lado dele)**

Entregar o `lancamentos_dominio.xlsx` gerado no E2E e pedir: **importar no Domínio real**. Critério de aceite final é o lote entrar sem erro. Qualquer recusa do Domínio volta como ajuste fino do contrato (formato de data/valor/lote).

---

## Self-Review (executado na escrita)

- **Cobertura da spec:** política (c) → Tasks 4/5/7/8; (a) plano por projeto → `localizar_plano()` em uploads + regras por projeto (Task 5/4); contrato Domínio (lote por dia, Cód. Histórico vazio, complemento, células tipadas) → `gerar_xlsx` + teste unitário (Task 5); período sempre confirmado e pré-preenchido → ClassificacaoReview (Task 7) + `_periodo` (Task 5); semáforo verde direto/âmbar confirma/vermelho obriga + Ignorar → Task 7; payload mínimo → classify.py só manda padrão+contas (Task 4); xls tolerante → `read_table` (Task 2); narração/timeline → progress + ProgressTimeline + endpoints (Tasks 2/3/6); entrevista profunda → Task 10; aceite ao centavo → teste de integração real (Task 5) + E2E (Task 11); import real no Domínio → handoff (Task 11 Step 6).
- **Placeholders:** nenhum "TBD/TODO"; todo step com código tem o código.
- **Consistência de tipos:** `progress` em `Execution` (Task 6) é o que `executions.py` devolve (Task 3); `_classificacao_review`/`_classificacao_confirmada`/`_conta_banco`/`_periodo` idênticos no script (Task 5), TestPanel (Task 8) e PublishedApp (Task 9); `RegraIn` compartilhado entre classify e published via `salvar_regras_interno` (Task 9).
- **Riscos assumidos:** layout posicional vale para extratos Bradesco neste formato (outros bancos ficam fora da v1, decisão de corte); `carregar_plano` depende do layout do relatório do Domínio validado com o arquivo real no teste de integração; COM fallback exige Excel na máquina (erro claro quando não houver).
