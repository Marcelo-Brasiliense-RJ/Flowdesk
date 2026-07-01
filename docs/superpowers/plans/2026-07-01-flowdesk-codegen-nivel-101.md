# Codegen nível 101 nas automações novas - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automações novas que batem com um padrão conhecido (extrato→Domínio) saem no nível do projeto 101 sem correção manual; as demais saem melhores.

**Architecture:** O agente `construtor` (orchestrator.run_construtor → call_agent) passa a (a) rodar `gpt-5.3-codex` via Responses API, isolada num ramo dentro de `call_agent`, e (b) receber o código real da galeria como referência (few-shot) e, em casamento claro, uma semente determinística com o código do template. Reparador e Treinador só trocam de modelo para `gpt-4.1`, sem migração.

**Tech Stack:** FastAPI, OpenAI Python SDK (Responses API), pytest, pandas/pdfplumber (runtime dos scripts).

## Global Constraints

- Migração para a Responses API acontece SÓ no `construtor`. Todo o resto permanece em `chat.completions`.
- `reparador` e `treinador` → `gpt-4.1` (chat.completions, sem migração). `construtor` → `gpt-5.3-codex`.
- Nenhum outro agente muda de modelo (assistente/roteador, planejador, nomeador, classificador seguem no modelo compartilhado atual).
- Confidencialidade inalterada: nada novo do cliente sai da máquina; código de template é local.
- Testes existentes (padrão do repo): unitários com `monkeypatch`, sem DB nem rede. Rodar `back/.venv/Scripts/python.exe -m pytest` a partir de `back/`.
- Não commitar nada além dos caminhos explícitos de cada task (há WIP concorrente na árvore).

---

### Task 1: Subir o SDK openai e validar o codex via Responses API (spike)

**Files:**
- Modify: `back/requirements.txt:12` (`openai==1.59.6`)

**Interfaces:**
- Produces: SDK com `client.responses.create` disponível; confirmação de que `gpt-5.3-codex` responde JSON utilizável via `output_text`.

- [ ] **Step 1: Subir o SDK**

Run (a partir de `back/`):
```bash
./.venv/Scripts/python.exe -m pip install -U openai
```

- [ ] **Step 2: Confirmar Responses API + codex (probe manual)**

Run:
```bash
./.venv/Scripts/python.exe - <<'PY'
import openai, json
from openai import OpenAI
from app.config import settings
print("openai", openai.__version__, "tem responses:", hasattr(OpenAI(api_key="x"), "responses"))
c = OpenAI(api_key=settings.openai_api_key)
r = c.responses.create(model="gpt-5.3-codex",
    input=[{"role":"system","content":"Responda SOMENTE em JSON."},
           {"role":"user","content":'Devolva {"ok": true} e nada mais.'}])
print("output_text:", repr(r.output_text))
print("json parseavel:", json.loads(r.output_text))
PY
```
Expected: `tem responses: True` e `json parseavel: {'ok': True}`. Se o `output_text` vier com cercas de código (```json), anote: o parser em Task 4 deve tolerar isso (usar `_strip_json`).

- [ ] **Step 3: Pinar a versão instalada no requirements**

Descobrir a versão instalada:
```bash
./.venv/Scripts/python.exe -c "import openai; print(openai.__version__)"
```
Editar `back/requirements.txt` linha 12: trocar `openai==1.59.6` por `openai==<versão_instalada>`.

- [ ] **Step 4: Garantir que o upgrade não quebrou nada**

Run:
```bash
./.venv/Scripts/python.exe -m pytest -q
```
Expected: mesma quantidade de testes passando de antes (nenhuma regressão do upgrade). Se algum teste quebrar por mudança de API do SDK, corrigir o call-site antes de seguir.

- [ ] **Step 5: Commit**

```bash
git add back/requirements.txt
git commit -m "chore(deps): sobe openai para versao com Responses API (codex no construtor)"
```

---

### Task 2: Modelo por agente (config.py + ai_config.py)

**Files:**
- Modify: `back/app/config.py` (novas settings)
- Modify: `back/app/services/ai_config.py` (`get_agent_model` com defaults por agente)
- Test: `back/tests/test_agent_model_defaults.py` (create)

**Interfaces:**
- Consumes: `settings.openai_model` (modelo compartilhado, já existe).
- Produces: `settings.openai_model_codegen`, `settings.openai_model_strong`; `ai_config.get_agent_model(agent_id)` retornando o default por agente quando não há override no grafo.

- [ ] **Step 1: Escrever o teste falhando**

Create `back/tests/test_agent_model_defaults.py`:
```python
from app.services import ai_config


def test_defaults_por_agente(monkeypatch):
    # sem grafo salvo e sem override de modelo compartilhado
    monkeypatch.setattr(ai_config, "_load", lambda: {})
    monkeypatch.setattr(ai_config, "get_graph", lambda: None)
    assert ai_config.get_agent_model("construtor") == "gpt-5.3-codex"
    assert ai_config.get_agent_model("reparador") == "gpt-4.1"
    assert ai_config.get_agent_model("treinador") == "gpt-4.1"
    # agente sem default cai no modelo compartilhado
    assert ai_config.get_agent_model("planejador") == ai_config.get_model()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_agent_model_defaults.py -q`
Expected: FAIL (get_agent_model devolve o modelo compartilhado para construtor).

- [ ] **Step 3: Adicionar as settings**

Em `back/app/config.py`, na classe `Settings`, logo após `openai_model`:
```python
    openai_model_codegen: str = "gpt-5.3-codex"
    openai_model_strong: str = "gpt-4.1"
```

- [ ] **Step 4: Implementar os defaults por agente**

Em `back/app/services/ai_config.py`, adicionar perto do topo (após os imports/settings):
```python
def _agent_model_defaults() -> dict:
    return {
        "construtor": settings.openai_model_codegen,
        "reparador": settings.openai_model_strong,
        "treinador": settings.openai_model_strong,
    }
```
E em `get_agent_model`, inserir o fallback ANTES de `return get_model()`:
```python
def get_agent_model(agent_id: str) -> str:
    """Modelo efetivo do agente: modelo do nó no grafo -> default por agente -> modelo compartilhado."""
    a = _graph_agent(agent_id)
    if a and isinstance(a.get("model"), str) and a["model"].strip():
        return a["model"].strip()
    d = _agent_model_defaults().get(agent_id)
    if d:
        return d
    return get_model()
```

- [ ] **Step 5: Rodar e ver passar**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_agent_model_defaults.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add back/app/config.py back/app/services/ai_config.py back/tests/test_agent_model_defaults.py
git commit -m "feat(ai_config): modelo por agente (construtor=codex, reparador/treinador=gpt-4.1)"
```

---

### Task 3: Reparador passa a usar o próprio modelo

**Files:**
- Modify: `back/app/routers/repair.py:146`
- Test: `back/tests/test_repair_model.py` (create)

**Interfaces:**
- Consumes: `ai_config.get_agent_model("reparador")` (Task 2).

- [ ] **Step 1: Escrever o teste falhando**

Create `back/tests/test_repair_model.py`:
```python
import types
import app.routers.repair as repair


class _FakeCompletions:
    def __init__(self, sink): self.sink = sink
    def create(self, **kw):
        self.sink["model"] = kw["model"]
        msg = types.SimpleNamespace(content='{"diagnosis":"d","change_summary":"c","fixed_code":"x"}')
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


def test_repair_usa_modelo_do_reparador(monkeypatch):
    sink = {}
    fake_client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=_FakeCompletions(sink)))
    monkeypatch.setattr(repair, "OpenAI", lambda **kw: fake_client, raising=False)
    monkeypatch.setattr(repair.ai_config, "get_agent_model", lambda a: f"modelo-de-{a}")
    # neutraliza acesso a DB/arquivos
    monkeypatch.setattr(repair, "_stage_source", lambda db, pid, st: None)
    monkeypatch.setattr(repair, "_execution_context", lambda e: "")
    monkeypatch.setattr(repair, "_attachment_context", lambda pid, paths: "")
    monkeypatch.setattr(repair, "_plan_profile_context", lambda plan, prof: "")
    db = types.SimpleNamespace(get=lambda model, _id: None)
    project = types.SimpleNamespace(id=1, plan={}, accounting_profile={})
    stage = types.SimpleNamespace()
    repair.run_repair(db, project, stage, "exec-1", None)
    assert sink["model"] == "modelo-de-reparador"
```
Nota: `repair.py` faz `from openai import OpenAI` DENTRO de `run_repair`; para o monkeypatch pegar, mover esse import para o topo do módulo (Step 3).

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_repair_model.py -q`
Expected: FAIL (usa `get_model()`, e/ou `OpenAI` importado dentro da função não é monkeypatchável).

- [ ] **Step 3: Implementar**

Em `back/app/routers/repair.py`:
1. Mover `from openai import OpenAI` para o topo do módulo (junto dos outros imports), removendo o import local dentro de `run_repair`.
2. Trocar a linha do modelo:
```python
    resp = client.chat.completions.create(
        model=ai_config.get_agent_model("reparador"),
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.1,
    )
```

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_repair_model.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add back/app/routers/repair.py back/tests/test_repair_model.py
git commit -m "feat(reparador): usa o modelo do proprio agente (gpt-4.1)"
```

---

### Task 4: Ramo Responses API no `call_agent` para modelos codex/raciocínio

**Files:**
- Modify: `back/app/routers/orchestrator.py:34-56` (`call_agent`)
- Test: `back/tests/test_call_agent_codex.py` (create)

**Interfaces:**
- Consumes: `ai_config.get_agent_model`, `ai_config.get_prompt`, `ai_config.get_temp`, `_client()`.
- Produces: `call_agent` roteia modelos casando `gpt-5|o3|o4|codex` para `client.responses.create` (sem temperature, retorna `output_text`); demais modelos seguem em `chat.completions`.

- [ ] **Step 1: Escrever o teste falhando**

Create `back/tests/test_call_agent_codex.py`:
```python
import types
from app.routers import orchestrator


def _fake_client(sink):
    def resp_create(**kw):
        sink["path"] = "responses"; sink["kw"] = kw
        return types.SimpleNamespace(output_text='{"ok":1}')
    def chat_create(**kw):
        sink["path"] = "chat"; sink["kw"] = kw
        msg = types.SimpleNamespace(content='{"ok":2}')
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])
    return types.SimpleNamespace(
        responses=types.SimpleNamespace(create=resp_create),
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=chat_create)),
    )


def test_codex_vai_para_responses(monkeypatch):
    sink = {}
    monkeypatch.setattr(orchestrator.settings, "openai_api_key", "x")
    monkeypatch.setattr(orchestrator, "_client", lambda: _fake_client(sink))
    monkeypatch.setattr(orchestrator.ai_config, "get_agent_model", lambda a: "gpt-5.3-codex")
    monkeypatch.setattr(orchestrator.ai_config, "get_prompt", lambda a, d: "sys")
    out = orchestrator.call_agent("construtor", "sys", [{"role": "user", "content": "oi"}], json_mode=True)
    assert sink["path"] == "responses"
    assert "temperature" not in sink["kw"]
    assert out == '{"ok":1}'


def test_chat_model_continua_em_chat(monkeypatch):
    sink = {}
    monkeypatch.setattr(orchestrator.settings, "openai_api_key", "x")
    monkeypatch.setattr(orchestrator, "_client", lambda: _fake_client(sink))
    monkeypatch.setattr(orchestrator.ai_config, "get_agent_model", lambda a: "gpt-4o-mini")
    monkeypatch.setattr(orchestrator.ai_config, "get_prompt", lambda a, d: "sys")
    monkeypatch.setattr(orchestrator.ai_config, "get_temp", lambda a: 0.2)
    out = orchestrator.call_agent("planejador", "sys", [{"role": "user", "content": "oi"}], json_mode=True)
    assert sink["path"] == "chat"
    assert sink["kw"]["response_format"] == {"type": "json_object"}
    assert out == '{"ok":2}'
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_call_agent_codex.py -q`
Expected: FAIL (call_agent sempre usa chat.completions).

- [ ] **Step 3: Implementar**

Em `back/app/routers/orchestrator.py`, adicionar no topo (após os imports):
```python
import re

_REASONING_MODEL = re.compile(r"gpt-5|o3|o4|codex", re.I)
```
Reescrever `call_agent` (linhas 34-56) para:
```python
def call_agent(
    agent_id: str,
    default_prompt: str,
    messages: list[dict],
    *,
    json_mode: bool = False,
) -> str:
    """Chama um agente lendo prompt/modelo/temperatura do grafo (ai_config).

    Modelos de raciocínio/codex (gpt-5*, o3*, o4*, *codex) usam a Responses API
    (sem temperature; o JSON é garantido pelo próprio prompt do agente, que já pede
    'SOMENTE em JSON'). Os demais seguem em chat.completions, inalterado.
    Com settings.ai_enabled desligado, retorna ""."""
    if not settings.ai_enabled:
        return ""
    prompt = ai_config.get_prompt(agent_id, default_prompt)
    model = ai_config.get_agent_model(agent_id)
    full = [{"role": "system", "content": prompt}, *messages]
    client = _client()
    if _REASONING_MODEL.search(model):
        resp = client.responses.create(model=model, input=full)
        return resp.output_text or ""
    kw = {
        "model": model,
        "temperature": ai_config.get_temp(agent_id),
        "messages": full,
    }
    if json_mode:
        kw["response_format"] = {"type": "json_object"}
    resp = client.chat.completions.create(**kw)
    return resp.choices[0].message.content or ""
```

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_call_agent_codex.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add back/app/routers/orchestrator.py back/tests/test_call_agent_codex.py
git commit -m "feat(orchestrator): call_agent usa Responses API para modelos codex/raciocinio"
```

---

### Task 5: Helper `reference_for_task` (pontua a galeria vs a tarefa)

**Files:**
- Create: `back/app/services/reference_code.py`
- Test: `back/tests/test_reference_code.py` (create)

**Interfaces:**
- Consumes: `TEMPLATES` de `app.routers.templates`.
- Produces: `reference_for_task(task_text: str) -> dict | None` = `{"template_key","code","score"}` (maior score); constantes `REF_LOW = 2`, `REF_HIGH = 4`.

- [ ] **Step 1: Escrever o teste falhando**

Create `back/tests/test_reference_code.py`:
```python
from app.services.reference_code import reference_for_task, REF_LOW, REF_HIGH


def test_extrato_casa_com_template_extrato_dominio():
    txt = "Ler o extrato bancario do Bradesco em PDF e gerar lancamentos para o Dominio"
    ref = reference_for_task(txt)
    assert ref is not None
    assert ref["template_key"] == "extrato-dominio"
    assert ref["score"] >= REF_HIGH
    assert "def parse_extrato" in ref["code"]


def test_tarefa_sem_relacao_tem_score_baixo():
    ref = reference_for_task("enviar um email de boas vindas para novos usuarios")
    # pode até casar algum template, mas com score abaixo do limiar de few-shot
    assert ref is None or ref["score"] < REF_LOW
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_reference_code.py -q`
Expected: FAIL (módulo não existe).

- [ ] **Step 3: Implementar**

Create `back/app/services/reference_code.py`:
```python
"""Seleciona o código de referência da galeria mais parecido com a tarefa, para
injetar como few-shot no Construtor (e semente determinística em casamento claro)."""
from __future__ import annotations

import re
import unicodedata

from ..routers.templates import TEMPLATES

REF_LOW = 2   # limiar mínimo para injetar como referência (few-shot)
REF_HIGH = 4  # limiar de casamento claro (semente determinística)

_STOP = {"para", "com", "dos", "das", "uma", "que", "por", "gerar", "arquivo", "dados"}


def _norm(s: str) -> str:
    """Minúsculas sem acentos, para 'bancário' casar com 'bancario'."""
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _tokens(s: str) -> set:
    toks = re.findall(r"[a-z0-9]{3,}", _norm(s))
    return {t for t in toks if t not in _STOP}


def reference_for_task(task_text: str):
    tt = _tokens(task_text)
    if not tt:
        return None
    best = None
    for key, tpl in TEMPLATES.items():
        base = _tokens(tpl["name"] + " " + tpl["description"])
        score = len(tt & base)
        if best is None or score > best["score"]:
            best = {"template_key": key, "code": tpl["code"], "score": score}
    if best is None or best["score"] < REF_LOW:
        return None
    return best
```

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_reference_code.py -q`
Expected: PASS. Se `extrato-dominio` não atingir REF_HIGH com esse texto, ajustar `_STOP`/limiares até o teste refletir o casamento real (a descrição do template contém "extrato", "PDF", "lançamentos", "Domínio").

- [ ] **Step 5: Commit**

```bash
git add back/app/services/reference_code.py back/tests/test_reference_code.py
git commit -m "feat(reference_code): seleciona codigo de referencia da galeria por relevancia"
```

---

### Task 6: Template `extrato-dominio` com `get_file` posicional

**Files:**
- Modify: `back/app/routers/templates.py` (dentro de `_EXTRATO_DOMINIO`)
- Test: `back/tests/test_extrato_dominio_positional.py` (create)

**Interfaces:**
- Produces: `_EXTRATO_DOMINIO` lê o PDF com `get_file(0)` e o plano com `get_file(1)` (com fallback ao glob), para casar formulários multi-arquivo como o do 102.

- [ ] **Step 1: Escrever o teste falhando**

Create `back/tests/test_extrato_dominio_positional.py`:
```python
from app.routers.templates import TEMPLATES


def test_extrato_dominio_usa_get_file_posicional():
    code = TEMPLATES["extrato-dominio"]["code"]
    assert "get_file(0)" in code          # PDF pelo índice
    assert "get_file(1)" in code          # plano de contas pelo índice
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_extrato_dominio_positional.py -q`
Expected: FAIL (hoje usa `get_file("arquivo")` e `localizar_plano()`).

- [ ] **Step 3: Implementar**

Em `back/app/routers/templates.py`, dentro de `_EXTRATO_DOMINIO`, no `main()`:
- Trocar `pdf = get_file("arquivo") or get_file()` por `pdf = get_file(0)`.
- Trocar `plano_path = localizar_plano()` por `plano_path = get_file(1) or localizar_plano()`.

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_extrato_dominio_positional.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add back/app/routers/templates.py back/tests/test_extrato_dominio_positional.py
git commit -m "feat(templates): extrato-dominio usa get_file posicional (forms multi-arquivo)"
```

---

### Task 7: Injeção de referência + semente determinística no `run_construtor`

**Files:**
- Modify: `back/app/routers/orchestrator.py` (`run_construtor` ~180-199)
- Test: `back/tests/test_construtor_reference.py` (create)

**Interfaces:**
- Consumes: `reference_for_task`, `REF_LOW`, `REF_HIGH` (Task 5); `call_agent` (Task 4).
- Produces: `run_construtor` injeta o código de referência quando `score >= REF_LOW` e, quando `score >= REF_HIGH`, força o conteúdo do script principal (.py) com o código do template.

- [ ] **Step 1: Escrever o teste falhando**

Create `back/tests/test_construtor_reference.py`:
```python
import json
from app.routers import orchestrator


def _plan_extrato():
    return {"regra_negocio": "extrato bancario Bradesco em PDF para lancamentos do Dominio",
            "saida": {"contrato": "layout Dominio"}}


def test_semente_deterministica_em_casamento_claro(monkeypatch):
    # o modelo devolve um script "errado"; a semente deve sobrescrever com o template
    monkeypatch.setattr(orchestrator, "call_agent", lambda *a, **k: json.dumps({
        "message": "ok",
        "actions": [{"kind": "create_file", "path": "x.py", "content": "print('errado')"}],
    }))
    out = orchestrator.run_construtor(_plan_extrato(), {}, "")
    py = next(a for a in out["actions"] if a["path"].endswith(".py"))
    assert "def parse_extrato" in py["content"]      # veio do template extrato-dominio
    assert "print('errado')" not in py["content"]


def test_few_shot_injeta_referencia_no_prompt(monkeypatch):
    captured = {}
    def fake(agent_id, prompt, messages, **k):
        captured["content"] = messages[0]["content"]
        return json.dumps({"message": "", "actions": []})
    monkeypatch.setattr(orchestrator, "call_agent", fake)
    orchestrator.run_construtor(_plan_extrato(), {}, "")
    assert "IMPLEMENTAÇÃO DE REFERÊNCIA PROVADA" in captured["content"]
    assert "def parse_extrato" in captured["content"]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_construtor_reference.py -q`
Expected: FAIL (run_construtor não injeta nem semeia).

- [ ] **Step 3: Implementar**

Em `back/app/routers/orchestrator.py`, no topo adicionar:
```python
from ..services.reference_code import reference_for_task, REF_LOW, REF_HIGH
```
E adicionar o helper e alterar `run_construtor`:
```python
def _seed_primary_script(actions: list[dict], code: str) -> list[dict]:
    """Força o conteúdo do script .py principal com o código de referência (semente
    determinística). Se não houver .py nas actions, cria um."""
    for a in actions:
        if a.get("kind") in ("create_file", "edit_file") and (a.get("path") or "").endswith(".py"):
            a["content"] = code
            return actions
    actions.append({"kind": "create_file", "title": "Criar script",
                    "path": "automacao.py", "content": code})
    return actions


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
    ref = reference_for_task(
        json.dumps(plan or {}, ensure_ascii=False) + " " + (project_context or "")
    )
    if ref and ref["score"] >= REF_LOW:
        blocks.append(
            "IMPLEMENTAÇÃO DE REFERÊNCIA PROVADA (adapte, não reescreva do zero):\n"
            f"```python\n{ref['code']}\n```"
        )
    messages = [{"role": "user", "content": "\n\n".join(blocks)}]
    raw = call_agent("construtor", CONSTRUTOR_PROMPT, messages, json_mode=True)
    try:
        data = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        data = {}
    actions = data.get("actions") or []
    if ref and ref["score"] >= REF_HIGH:
        actions = _seed_primary_script(actions, ref["code"])
    return {"message": data.get("message") or "", "actions": actions}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_construtor_reference.py -q`
Expected: PASS

- [ ] **Step 5: Rodar a suíte inteira (sem regressão)**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: tudo verde.

- [ ] **Step 6: Commit**

```bash
git add back/app/routers/orchestrator.py back/tests/test_construtor_reference.py
git commit -m "feat(construtor): injeta codigo de referencia da galeria + semente deterministica"
```

---

### Task 8: Verificação ponta a ponta (paridade com o 101)

**Files:** nenhum (verificação manual com evidência).

**Interfaces:**
- Consumes: tudo acima; `OPENAI_API_KEY` já configurada; arquivos reais em `back/storage/101/uploads/` ou `back/storage/102/uploads/`.

- [ ] **Step 1: Gerar o código via Construtor para um plano 102-like**

Run (a partir de `back/`):
```bash
./.venv/Scripts/python.exe - <<'PY'
from app.routers import orchestrator
plan = {"contabil": True,
        "regra_negocio": "Ler o extrato bancario Bradesco em PDF, classificar os lancamentos com o plano de contas e gerar a planilha de importacao do Dominio",
        "fonte": {"formato": "pdf"}, "saida": {"formato": "xlsx", "contrato": "layout Dominio"}}
out = orchestrator.run_construtor(plan, {}, "")
py = next(a for a in out["actions"] if a.get("path","").endswith(".py"))
open("../back/storage/_verif_construtor.py","w",encoding="utf-8").write(py["content"])
print("gerou .py com", len(py["content"]), "chars; parse_extrato presente:", "def parse_extrato" in py["content"])
PY
```
Expected: `parse_extrato presente: True` (semente determinística pegou; o script é o template provado).

- [ ] **Step 2: Rodar o script gerado contra os arquivos reais (pass 1)**

Usar o mesmo harness da correção do 101 (SDK + input.json com caminhos Windows dos uploads do 102), apontando `FLOWDESK_INPUT/OUTPUT/RUN_DIR` e `PYTHONPATH`. Rodar o `_verif_construtor.py`.
Expected: output com `_classificacao_review`, ~**564 lançamentos**, período 01/04–30/04, plano lido (~1760 contas). Paridade com o 101.

- [ ] **Step 3: Limpeza**

```bash
rm -f back/storage/_verif_construtor.py
```

- [ ] **Step 4: Sem commit** (verificação). Registrar o resultado no PR/descrição.

---

## Notas de execução

- Ordem recomendada: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8. Task 3 e 4 são independentes entre si (podem ser paralelas); ambas dependem da 2 (get_agent_model) e a 4 depende da 1 (Responses API). Task 7 depende de 5 e 6.
- Se o probe da Task 1 mostrar `output_text` com cercas ```json, adicionar em `call_agent` (Task 4) um `_strip_json(s)` que remove cercas antes de retornar, e ajustar o teste da Task 4.
- Bump de modelo do reparador/treinador para `gpt-4.1` é validado nas Tasks 2 e 3; o construtor codex é validado nas Tasks 4 e 8.
