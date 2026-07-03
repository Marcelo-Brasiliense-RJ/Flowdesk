# Auto-evolução dos Agentes do FlowDesk — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduzir um agente `Treinador` que colhe automações publicadas e validadas, injeta as melhores como few-shot no runtime dos agentes de build, e propõe melhorias de prompt (com aprovação humana), sem tocar no caminho crítico de produção.

**Architecture:** Um serviço novo (`services/treinador.py`) que persiste em JSON no `STORAGE_DIR` (mesmo padrão de `ai_config`, zero migração). A colheita dispara como task **destacada** após o commit de sucesso de uma execução (fora do try/except do worker, engolindo qualquer erro). O few-shot é anexado ao `project_context` já existente no chat (sem mudar assinaturas). A destilação de prompt roda por limiar de exemplos novos e gera propostas que o admin aprova na área de Agentes; aprovar aplica na fonte que `ai_config.get_prompt` realmente lê. O Quadro de agentes é redesenhado (dado puramente visual em `_default_graph`) para refletir o fluxo real.

**Tech Stack:** FastAPI + SQLAlchemy (SQLite/Postgres) · Pydantic · OpenAI chat completions (cliente já configurado) · React 18 + TypeScript + Tailwind · pytest.

## Global Constraints

- **Não quebrar produção:** toda alteração é aditiva. Nenhum hook no caminho crítico (runner, publish, execução) pode bloquear ou lançar exceção que altere o resultado do usuário. Hooks de treino são best-effort e engolem todas as exceções.
- **Zero migração de banco:** persistência do Treinador é JSON em `STORAGE_DIR`, espelhando `back/app/services/ai_config.py` (mesmo `_load`/`_save`/`threading.Lock`). Nenhuma tabela nova.
- **Confidencialidade:** exemplos guardam apenas `{plano_anonimizado, código}`. NUNCA arquivos enviados, `Execution.input_data`/`output_data`, ou dados de execução. O plano passa por anonimização antes de virar exemplo; se a anonimização falhar, o exemplo NÃO é gravado.
- **Nada cosmético:** aprovar uma proposta de prompt tem que aplicá-la na fonte que `ai_config.get_prompt` lê (grafo se houver, senão override simples). Ver `apply_prompt` na Task 3.
- **Provedor de IA:** usar o cliente OpenAI-compatível já existente (`ai_config.get_model()` / `orchestrator.call_agent`). NÃO trocar o cliente nem introduzir fine-tuning.
- **Agente Treinador fora do caminho crítico:** `treinador` nunca é chamado por `orchestrate_turn`, `route_intent`, `repair_propose` nem pelo runner de execução. Só roda nas funções de colheita/destilação.

---

## Estrutura de arquivos

**Criar:**
- `back/app/services/treinador.py` — núcleo: store JSON, colheita, anonimização, seleção/few-shot, eventos de reparo, destilação, propostas.
- `back/tests/test_treinador.py` — testes das funções puras (seleção, validação, dedup, eventos de reparo).
- `back/tests/test_ai_config_apply_prompt.py` — teste da aplicação de prompt na fonte certa.

**Modificar:**
- `back/app/services/ai_config.py` — adicionar `apply_prompt(agent_id, prompt)`.
- `back/app/routers/ai.py` — `treinador` no roster (`_AGENTS`, `_DEFAULT_PROMPTS`, `_COLORS`); reescrever `_default_graph()` (pipeline + camada meta); endpoints de propostas.
- `back/app/routers/chat.py` — injetar `treinador.examples_context(plan)` no `_orch_ctx`.
- `back/app/routers/repair.py` — capturar evento de reparo no `repair_apply` (best-effort); `RepairApplyIn` ganha `execution_id` opcional.
- `back/app/schemas.py` — `RepairApplyIn.execution_id: str | None`.
- `back/app/runtime/runner.py` — `_schedule_harvest` + `_safe_harvest` (task destacada após sucesso).
- `front/src/pages/Agents.tsx` — `Edge.kind?` + render tracejado; seção "Propostas do Treinador" (admin).

---

## Task 0: Redesenho do Quadro de agentes (independente, puramente visual)

Ship isolado. Não depende de nenhuma outra task. Muda só o grafo-semente e o render de arestas.

**Files:**
- Modify: `back/app/routers/ai.py:99-127` (`_default_graph`), `:75-93` (`_DEFAULT_PROMPTS`/`_COLORS` — só se o Treinador já existir; se Task 0 for antes da Task 1, adicionar o nó `treinador` aqui como placeholder visual é opcional — ver nota).
- Modify: `front/src/pages/Agents.tsx:26-30` (interface `Edge`), `:341-361` (render das arestas).
- Test: `back/tests/test_ai_default_graph.py` (criar).

**Interfaces:**
- Produces: `_default_graph()` retorna `{"agents": [...], "edges": [{"id","from","to","kind"?}]}`. Arestas com `"kind": "learn"` são tracejadas no frontend.

**Nota de escopo:** o nó `treinador` no grafo é adicionado de fato na Task 1 (roster). Se você executar a Task 0 antes da Task 1, use o layout de pipeline SEM o nó `treinador` e SEM as arestas `learn`; adicione o nó e as arestas meta quando a Task 1 entrar. As duas ordens funcionam. O plano abaixo assume Task 1 já feita (grafo completo com Treinador).

- [ ] **Step 1: Teste do grafo-semente (pipeline + meta)**

Criar `back/tests/test_ai_default_graph.py`:

```python
from app.routers.ai import _default_graph


def test_default_graph_is_pipeline_not_star():
    g = _default_graph()
    ids = {a["id"] for a in g["agents"]}
    assert "treinador" in ids  # Task 1 já adicionou o Treinador ao roster
    pairs = {(e["from"], e["to"]) for e in g["edges"]}
    # pipeline real: Planejador -> Construtor -> Nomeador
    assert ("planejador", "construtor") in pairs
    assert ("construtor", "nomeador") in pairs
    # Classificador alimenta o Construtor
    assert ("classificador", "construtor") in pairs
    # Assistente roteia para o Planejador (entrada do pipeline)
    assert ("assistente", "planejador") in pairs
    # NÃO é mais estrela: Assistente não liga direto no Construtor/Nomeador
    assert ("assistente", "construtor") not in pairs
    assert ("assistente", "nomeador") not in pairs


def test_treinador_edges_are_learn_kind():
    g = _default_graph()
    learn = [e for e in g["edges"] if e.get("kind") == "learn"]
    # Treinador melhora todos os agentes de build via arestas tracejadas
    assert learn, "esperava arestas 'learn' saindo do Treinador"
    assert all(e["from"] == "treinador" for e in learn)
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `cd back && python -m pytest tests/test_ai_default_graph.py -v`
Expected: FAIL (grafo atual é estrela via `parent`; sem `treinador` até a Task 1).

- [ ] **Step 3: Reescrever `_default_graph()` em `back/app/routers/ai.py`**

Substituir a função `_default_graph` (linhas 99-127) por posições explícitas de pipeline + camada meta e uma lista de arestas explícita. Copiar exatamente:

```python
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
```

Remover a antiga constante `_CANVAS_W = 760` duplicada (linha 96) se ficar duplicada — manter só a de cima.

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `cd back && python -m pytest tests/test_ai_default_graph.py -v`
Expected: PASS.

- [ ] **Step 5: Frontend — arestas tracejadas para a camada meta**

Em `front/src/pages/Agents.tsx`, estender a interface `Edge` (linha 26-30):

```typescript
interface Edge {
  id: string;
  from: string;
  to: string;
  kind?: string; // "learn" => tracejada (camada meta do Treinador)
}
```

No render das arestas (dentro do `.map`, na `<line>` principal, linha ~357), adicionar `strokeDasharray` quando `kind === "learn"`:

```tsx
<line
  x1={x1} y1={y1} x2={x2} y2={y2}
  stroke={selected ? "var(--accent)" : "var(--border-strong)"}
  strokeWidth={selected ? 2.4 : 1.8}
  strokeDasharray={e.kind === "learn" ? "5 5" : undefined}
  markerEnd={`url(#ag-arrow${selected ? "-sel" : ""})`}
  strokeLinecap="round"
/>
```

- [ ] **Step 6: Verificar build do frontend**

Run: `cd front && npm run build`
Expected: build sem erros de tipo.

- [ ] **Step 7: Commit**

```bash
git add back/app/routers/ai.py back/tests/test_ai_default_graph.py front/src/pages/Agents.tsx
git commit -m "feat(agents): redesenha Quadro de agentes como pipeline honesto + camada meta (Treinador)"
```

---

## Task 1: Agente Treinador no roster + esqueleto do store JSON

**Files:**
- Create: `back/app/services/treinador.py`
- Modify: `back/app/routers/ai.py:39-93` (`_AGENTS`, `_DEFAULT_PROMPTS`, `_COLORS`)
- Test: `back/tests/test_treinador.py` (criar)

**Interfaces:**
- Produces:
  - `treinador.TREINADOR_PROMPT: str`
  - `treinador._load(path) -> dict` / `_save(path, data) -> None` (privados, padrão `ai_config`)
  - `treinador._examples() -> list[dict]` / `treinador._proposals() -> list[dict]` / `treinador._repairs() -> list[dict]`
- Consumes (Task 4): `ai.py` importa `TREINADOR_PROMPT` para `_DEFAULT_PROMPTS`.

- [ ] **Step 1: Teste do store vazio (não explode sem arquivo)**

Criar `back/tests/test_treinador.py`:

```python
from app.services import treinador


def test_store_reads_empty_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    assert treinador._examples() == []
    assert treinador._proposals() == []
    assert treinador._repairs() == []


def test_treinador_has_default_prompt():
    assert isinstance(treinador.TREINADOR_PROMPT, str)
    assert treinador.TREINADOR_PROMPT.strip()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd back && python -m pytest tests/test_treinador.py -v`
Expected: FAIL (`ModuleNotFoundError: app.services.treinador`).

- [ ] **Step 3: Criar `back/app/services/treinador.py` (esqueleto + store)**

```python
"""Treinador: agente de auto-evolução (fora do caminho crítico).

Colhe automações publicadas e validadas, guarda plano anonimizado + código como
exemplos few-shot, registra eventos de reparo, e destila propostas de melhoria de
prompt para os agentes de build. Persiste em JSON no STORAGE_DIR, espelhando
services/ai_config.py (zero migração). NADA aqui roda no caminho crítico de
execução/publish: é chamado por hooks best-effort e por endpoints de admin.
"""
from __future__ import annotations

import hashlib
import json
import threading

from ..config import STORAGE_DIR

_DIR = STORAGE_DIR / "treinador"
_lock = threading.Lock()

# arquivos do store
def _examples_path():
    return _DIR / "examples.json"

def _proposals_path():
    return _DIR / "proposals.json"

def _repairs_path():
    return _DIR / "repairs.json"

def _meta_path():
    return _DIR / "meta.json"


def _load(path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(path, data: dict) -> None:
    with _lock:
        _DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _examples() -> list[dict]:
    return _load(_examples_path()).get("items", [])


def _proposals() -> list[dict]:
    return _load(_proposals_path()).get("items", [])


def _repairs() -> list[dict]:
    return _load(_repairs_path()).get("items", [])


TREINADOR_PROMPT = (
    "Você é o Treinador do FlowDesk. Seu trabalho é analisar automações que foram "
    "publicadas e validadas (rodaram em produção sem erro) e os ajustes feitos até "
    "elas irem ao ar, para melhorar os agentes que constroem automações. Você tem "
    "duas tarefas, indicadas em cada chamada:\n"
    "1) ANONIMIZAR: dado um PLANO de automação, remova ou generalize qualquer dado "
    "que identifique um cliente/empresa específico (razões sociais, nomes próprios, "
    "CNPJ, nomes de contas específicas, nomes de colunas com identificadores), "
    "mantendo intacto o PADRÃO estrutural (formatos, tipos de regra, tipo de saída). "
    "Responda SOMENTE o JSON do plano anonimizado.\n"
    "2) DESTILAR: dado um conjunto de exemplos validados e ajustes (reparos, "
    "rejeições), e o system prompt ATUAL de um agente, proponha um system prompt "
    "MELHOR que evite os erros observados e reforce os padrões que deram certo. "
    "Não invente regras não sustentadas pelos exemplos. Responda SOMENTE em JSON "
    '{"proposed_prompt": "...", "rationale": "1 a 3 frases do que muda e por quê"}.'
)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd back && python -m pytest tests/test_treinador.py -v`
Expected: PASS.

- [ ] **Step 5: Adicionar o Treinador ao roster em `back/app/routers/ai.py`**

No topo, junto dos imports de prompts (linha 18), adicionar:

```python
from ..services.treinador import TREINADOR_PROMPT
```

Em `_AGENTS` (após o dict do `classificador`, linha 69), acrescentar:

```python
    {"id": "treinador", "name": "Treinador", "role": "Aprende do validado e melhora os agentes",
     "level": 3, "parent": None, "temp": "0.2",
     "tools": ["Colhe exemplos", "Anonimiza", "Destila prompt", "Propõe melhorias"],
     "desc": "Camada de auto-evolução: colhe automações publicadas e validadas, guarda o plano anonimizado e o código como exemplos, e propõe melhorias de prompt para os agentes de build. Nunca roda no fluxo de execução/publish, só no ciclo de treino.",
     "where": "services/treinador.py"},
```

Em `_DEFAULT_PROMPTS` (linha 75-82), acrescentar:

```python
    "treinador": TREINADOR_PROMPT,
```

Em `_COLORS` (linha 86-93), acrescentar:

```python
    "treinador": ["#0d9488", "#5eead4"],
```

- [ ] **Step 6: Verificar que o roster carrega**

Run: `cd back && python -c "from app.routers.ai import _default_graph; ids=[a['id'] for a in _default_graph()['agents']]; print(ids); assert 'treinador' in ids"`
Expected: lista com `treinador` presente, sem erro.

- [ ] **Step 7: Commit**

```bash
git add back/app/services/treinador.py back/tests/test_treinador.py back/app/routers/ai.py
git commit -m "feat(treinador): adiciona agente Treinador ao roster e esqueleto do store JSON"
```

---

## Task 2: `apply_prompt` — aplicar na fonte que `get_prompt` lê

Resolve o gotcha: `get_prompt` lê o prompt do nó do grafo primeiro; um `set_prompt` seria ignorado quando há grafo salvo.

**Files:**
- Modify: `back/app/services/ai_config.py` (após `set_prompt`, linha 100)
- Test: `back/tests/test_ai_config_apply_prompt.py` (criar)

**Interfaces:**
- Produces: `ai_config.apply_prompt(agent_id: str, prompt: str) -> None` — grava no nó do grafo se houver grafo salvo; senão no override simples. Garante que `get_prompt(agent_id, default)` passe a devolver `prompt`.

- [ ] **Step 1: Teste — aplica no grafo quando há grafo**

Criar `back/tests/test_ai_config_apply_prompt.py`:

```python
from app.services import ai_config


def test_apply_prompt_writes_to_graph_node_when_graph_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_config, "_PATH", tmp_path / "ai_config.json")
    ai_config.set_graph({"agents": [{"id": "construtor", "prompt": "velho"}], "edges": []})
    ai_config.apply_prompt("construtor", "novo prompt")
    # get_prompt lê o grafo primeiro; tem que refletir o novo valor
    assert ai_config.get_prompt("construtor", "DEFAULT") == "novo prompt"


def test_apply_prompt_falls_back_to_override_without_graph(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_config, "_PATH", tmp_path / "ai_config.json")
    ai_config.apply_prompt("planejador", "prompt override")
    assert ai_config.get_prompt("planejador", "DEFAULT") == "prompt override"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd back && python -m pytest tests/test_ai_config_apply_prompt.py -v`
Expected: FAIL (`AttributeError: module ... has no attribute 'apply_prompt'`).

- [ ] **Step 3: Implementar `apply_prompt` em `back/app/services/ai_config.py`**

Adicionar após `set_prompt` (linha 100):

```python
def apply_prompt(agent_id: str, prompt: str) -> None:
    """Aplica um system prompt na fonte que get_prompt REALMENTE lê.

    get_prompt prioriza o prompt do nó no grafo salvo; então, se há grafo, o novo
    prompt precisa ir para o nó (senão seria ignorado). Sem grafo, cai no override
    simples. É assim que uma proposta aprovada do Treinador tem efeito de verdade.
    """
    data = _load()
    g = data.get("graph")
    if isinstance(g, dict):
        for a in g.get("agents") or []:
            if isinstance(a, dict) and a.get("id") == agent_id:
                a["prompt"] = prompt
                data["graph"] = g
                _save(data)
                return
    prompts = dict(data.get("prompts") or {})
    prompts[agent_id] = prompt
    data["prompts"] = prompts
    _save(data)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd back && python -m pytest tests/test_ai_config_apply_prompt.py -v`
Expected: PASS (ambos).

- [ ] **Step 5: Commit**

```bash
git add back/app/services/ai_config.py back/tests/test_ai_config_apply_prompt.py
git commit -m "feat(ai_config): apply_prompt aplica na fonte que get_prompt lê (grafo ou override)"
```

---

## Task 3: Sinal de validado + fingerprint de dedup

**Files:**
- Modify: `back/app/services/treinador.py`
- Test: `back/tests/test_treinador.py`

**Interfaces:**
- Produces:
  - `treinador.is_validated(db, project_id: int) -> bool` — `Project.status=='live'` E, entre as últimas 5 execuções, ≥1 `success` e 0 `error`.
  - `treinador._source_fingerprint(db, project_id: int) -> str` — sha1 do conteúdo concatenado dos `SourceFile` (chave de dedup por versão de código).

- [ ] **Step 1: Teste de `is_validated`**

Adicionar em `back/tests/test_treinador.py`:

```python
import datetime as dt
from app.models import Base, Organization, Project, Execution
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _mem_db():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    return Session(eng)


def _proj(db, status="live"):
    org = Organization(name="IRKO")
    db.add(org); db.flush()
    p = Project(org_id=org.id, name="P", subdomain="p", status=status)
    db.add(p); db.flush()
    return p


def _exec(db, pid, status, minutes_ago):
    e = Execution(
        id=f"{pid}-{status}-{minutes_ago}", project_id=pid, stage_id=1,
        status=status,
        started_at=dt.datetime(2026, 1, 1) + dt.timedelta(minutes=100 - minutes_ago),
    )
    db.add(e); db.flush()
    return e


def test_validated_needs_live_success_and_no_recent_error():
    db = _mem_db()
    p = _proj(db, status="live")
    _exec(db, p.id, "success", 1)
    assert treinador.is_validated(db, p.id) is True


def test_not_validated_when_recent_error():
    db = _mem_db()
    p = _proj(db, status="live")
    _exec(db, p.id, "success", 5)
    _exec(db, p.id, "error", 1)  # erro recente derruba
    assert treinador.is_validated(db, p.id) is False


def test_not_validated_when_draft():
    db = _mem_db()
    p = _proj(db, status="draft")
    _exec(db, p.id, "success", 1)
    assert treinador.is_validated(db, p.id) is False


def test_not_validated_without_any_success():
    db = _mem_db()
    p = _proj(db, status="live")
    assert treinador.is_validated(db, p.id) is False
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd back && python -m pytest tests/test_treinador.py -k validated -v`
Expected: FAIL (`is_validated` não existe).

- [ ] **Step 3: Implementar `is_validated` e `_source_fingerprint`**

Adicionar em `back/app/services/treinador.py`:

```python
def is_validated(db, project_id: int) -> bool:
    """Publicada E estável: status live, e entre as últimas 5 execuções há pelo menos
    um sucesso e nenhum erro. É o sinal de 'boa o suficiente para virar exemplo'."""
    from ..models import Execution, Project

    project = db.get(Project, project_id)
    if project is None or project.status != "live":
        return False
    recent = (
        db.query(Execution)
        .filter(Execution.project_id == project_id)
        .order_by(Execution.started_at.desc())
        .limit(5)
        .all()
    )
    statuses = [e.status for e in recent]
    return ("success" in statuses) and ("error" not in statuses)


def _source_fingerprint(db, project_id: int) -> str:
    """sha1 do código atual do projeto. Muda quando o código muda -> re-colhe uma
    versão validada nova; igual -> dedup (não re-anonimiza a cada execução)."""
    from ..models import SourceFile

    files = (
        db.query(SourceFile)
        .filter(SourceFile.project_id == project_id)
        .order_by(SourceFile.path)
        .all()
    )
    blob = "\n".join(f"{f.path}\x00{f.content or ''}" for f in files if not f.is_dir)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd back && python -m pytest tests/test_treinador.py -k "validated or fingerprint" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add back/app/services/treinador.py back/tests/test_treinador.py
git commit -m "feat(treinador): sinal de validado (live+sucesso+sem erro recente) e fingerprint de dedup"
```

---

## Task 4: Seleção heurística de exemplos + bloco de contexto few-shot

**Files:**
- Modify: `back/app/services/treinador.py`
- Test: `back/tests/test_treinador.py`

**Interfaces:**
- Produces:
  - `treinador.select_examples(plan: dict, k: int = 2) -> list[dict]` — casa por `contabil`, `fonte.formato`, `saida.formato` e overlap de palavras em `regra_negocio`; retorna os `k` melhores com score ≥ 1.
  - `treinador.examples_context(plan: dict) -> str` — bloco de sistema (string) com os exemplos escolhidos, ou `""` quando não há.
- Formato de um exemplo no store: `{"plan": <plano anon>, "code": <str>, "fingerprint": <str>, "project_id": <int>}`.

- [ ] **Step 1: Teste da seleção heurística**

Adicionar em `back/tests/test_treinador.py`:

```python
def _example(contabil, fonte_fmt, saida_fmt, regra, code="x"):
    return {
        "plan": {
            "contabil": contabil,
            "fonte": {"formato": fonte_fmt},
            "saida": {"formato": saida_fmt},
            "regra_negocio": regra,
        },
        "code": code, "fingerprint": regra, "project_id": 1,
    }


def test_select_prefers_same_format_and_contabil(monkeypatch, tmp_path):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    treinador._save(treinador._examples_path(), {"items": [
        _example(True, "xlsx", "xlsx", "conciliação de razão contábil", code="A"),
        _example(False, "csv", "pdf", "relatório de vendas mensal", code="B"),
        _example(True, "xlsx", "xlsx", "aging de contas a receber", code="C"),
    ]})
    plan = {"contabil": True, "fonte": {"formato": "xlsx"},
            "saida": {"formato": "xlsx"}, "regra_negocio": "conciliação de razão"}
    picked = treinador.select_examples(plan, k=2)
    assert len(picked) == 2
    codes = {e["code"] for e in picked}
    assert "B" not in codes  # nada em comum, score 0 -> fora
    assert "A" in codes      # maior overlap de regra_negocio


def test_examples_context_empty_when_no_match(monkeypatch, tmp_path):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    treinador._save(treinador._examples_path(), {"items": []})
    assert treinador.examples_context({"contabil": False}) == ""
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd back && python -m pytest tests/test_treinador.py -k "select or examples_context" -v`
Expected: FAIL (`select_examples` não existe).

- [ ] **Step 3: Implementar `select_examples` e `examples_context`**

Adicionar em `back/app/services/treinador.py`:

```python
import json as _json


def _tokens(s: str) -> set:
    return {w for w in (s or "").lower().split() if len(w) > 3}


def _score(plan: dict, ex_plan: dict) -> int:
    score = 0
    if bool(plan.get("contabil")) == bool(ex_plan.get("contabil")) and plan.get("contabil"):
        score += 2
    if (plan.get("fonte") or {}).get("formato") and \
       (plan.get("fonte") or {}).get("formato") == (ex_plan.get("fonte") or {}).get("formato"):
        score += 2
    if (plan.get("saida") or {}).get("formato") and \
       (plan.get("saida") or {}).get("formato") == (ex_plan.get("saida") or {}).get("formato"):
        score += 1
    overlap = _tokens(plan.get("regra_negocio", "")) & _tokens(ex_plan.get("regra_negocio", ""))
    score += len(overlap)
    return score


def select_examples(plan: dict, k: int = 2) -> list[dict]:
    """Exemplos validados mais parecidos com o plano atual (heurística sobre o plano).
    Só retorna quem tem score >= 1 (evita injetar exemplo irrelevante)."""
    scored = [(_score(plan or {}, ex.get("plan") or {}), ex) for ex in _examples()]
    scored = [(s, ex) for s, ex in scored if s >= 1]
    scored.sort(key=lambda t: t[0], reverse=True)
    return [ex for _, ex in scored[:k]]


def examples_context(plan: dict) -> str:
    """Bloco de sistema com exemplos validados, para o Construtor/Planejador se
    espelharem no que já deu certo. Vazio quando não há exemplo relevante."""
    picked = select_examples(plan, k=2)
    if not picked:
        return ""
    blocks = []
    for i, ex in enumerate(picked, 1):
        blocks.append(
            f"EXEMPLO {i} (automação já publicada e validada em produção):\n"
            "PLANO:\n" + _json.dumps(ex.get("plan") or {}, ensure_ascii=False, indent=2)
            + "\nCÓDIGO:\n" + (ex.get("code") or "")[:3000]
        )
    return (
        "EXEMPLOS DE REFERÊNCIA (automações que foram ao ar e rodaram sem erro). "
        "Use-os como guia de estrutura e estilo; NÃO copie dados, apenas o padrão:\n\n"
        + "\n\n".join(blocks)
    )
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd back && python -m pytest tests/test_treinador.py -k "select or examples_context" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add back/app/services/treinador.py back/tests/test_treinador.py
git commit -m "feat(treinador): seleção heurística de exemplos e bloco de contexto few-shot"
```

---

## Task 5: Anonimização + colheita (`harvest_project`, best-effort)

**Files:**
- Modify: `back/app/services/treinador.py`
- Test: `back/tests/test_treinador.py`

**Interfaces:**
- Produces:
  - `treinador.anonymize_plan(plan: dict) -> dict | None` — via agente `treinador`; `None` em falha (não grava exemplo não anonimizado).
  - `treinador.harvest_project(project_id: int) -> bool` — best-effort, NUNCA lança. Abre sua própria sessão. Grava um exemplo se validado e ainda não colhido para o fingerprint atual. Retorna True se gravou.

- [ ] **Step 1: Teste — colheita respeita validação e dedup (sem IA)**

Adicionar em `back/tests/test_treinador.py`:

```python
from app.models import SourceFile


def test_harvest_skips_when_not_validated(monkeypatch, tmp_path):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    db = _mem_db()
    p = _proj(db, status="draft")  # não validado
    monkeypatch.setattr(treinador, "SessionLocal", lambda: db)
    assert treinador.harvest_project(p.id) is False
    assert treinador._examples() == []


def test_harvest_stores_once_then_dedups(monkeypatch, tmp_path):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    db = _mem_db()
    p = _proj(db, status="live")
    _exec(db, p.id, "success", 1)
    db.add(SourceFile(project_id=p.id, path="processar.py", content="print(1)"))
    p.plan = {"contabil": False, "fonte": {"formato": "xlsx"},
              "saida": {"formato": "xlsx"}, "regra_negocio": "somar colunas"}
    db.flush()
    monkeypatch.setattr(treinador, "SessionLocal", lambda: db)
    # anonimização mockada (sem IA de verdade nos testes)
    monkeypatch.setattr(treinador, "anonymize_plan", lambda plan: plan)
    assert treinador.harvest_project(p.id) is True
    assert len(treinador._examples()) == 1
    # segunda chamada com o mesmo código: dedup, não grava de novo
    assert treinador.harvest_project(p.id) is False
    assert len(treinador._examples()) == 1


def test_harvest_never_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    def _boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(treinador, "SessionLocal", _boom)
    # best-effort: engole tudo, retorna False
    assert treinador.harvest_project(1) is False
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd back && python -m pytest tests/test_treinador.py -k harvest -v`
Expected: FAIL (`harvest_project`/`anonymize_plan` não existem).

- [ ] **Step 3: Implementar `anonymize_plan` e `harvest_project`**

Adicionar em `back/app/services/treinador.py` (no topo, junto dos imports):

```python
from ..database import SessionLocal
```

E as funções:

```python
def anonymize_plan(plan: dict) -> dict | None:
    """Anonimiza o plano via agente Treinador. Retorna None se a IA falhar ou
    devolver algo inválido (nesse caso NÃO se grava exemplo — nunca vaza dado cru)."""
    from ..config import settings
    if not settings.ai_enabled:
        return None
    from .orchestrator import call_agent

    raw = call_agent(
        "treinador", TREINADOR_PROMPT,
        [{"role": "user", "content": "TAREFA: ANONIMIZAR\nPLANO:\n"
          + json.dumps(plan or {}, ensure_ascii=False)}],
        json_mode=True,
    )
    try:
        data = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return None
    # o modelo pode devolver o plano direto ou aninhado em "plan"
    result = data.get("plan") if isinstance(data.get("plan"), dict) else data
    return result if isinstance(result, dict) and result else None


def _entry_code(db, project_id: int) -> str:
    """Conteúdo do maior .py do projeto (o script principal da automação)."""
    from ..models import SourceFile

    pys = [
        f for f in db.query(SourceFile).filter(SourceFile.project_id == project_id).all()
        if f.path.endswith(".py") and not f.is_dir and (f.content or "").strip()
    ]
    if not pys:
        return ""
    return max(pys, key=lambda f: len(f.content or "")).content


def harvest_project(project_id: int) -> bool:
    """Best-effort: se o projeto está validado e ainda não foi colhido nesta versão
    de código, anonimiza o plano e grava um exemplo. NUNCA lança (é chamado por hook
    fora do caminho crítico). Retorna True se gravou um exemplo novo."""
    try:
        db = SessionLocal()
    except Exception:
        return False
    try:
        if not is_validated(db, project_id):
            return False
        from ..models import Project

        project = db.get(Project, project_id)
        fp = _source_fingerprint(db, project_id)
        if any(ex.get("fingerprint") == fp for ex in _examples()):
            return False  # dedup: mesma versão já colhida
        code = _entry_code(db, project_id)
        if not code:
            return False
        anon = anonymize_plan((project.plan if project else {}) or {})
        if anon is None:
            return False  # anonimização falhou -> não grava (confidencialidade)
        data = _load(_examples_path())
        items = data.get("items", [])
        items.append({"plan": anon, "code": code, "fingerprint": fp, "project_id": project_id})
        _save(_examples_path(), {"items": items})
        # sinaliza que há exemplos novos para a destilação por limiar (Task 8)
        _bump_new_examples()
        return True
    except Exception:
        return False
    finally:
        try:
            db.close()
        except Exception:
            pass


def _bump_new_examples() -> None:
    """Contador de exemplos novos desde a última destilação (limiar da Task 8)."""
    meta = _load(_meta_path())
    meta["new_examples"] = int(meta.get("new_examples", 0)) + 1
    _save(_meta_path(), meta)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd back && python -m pytest tests/test_treinador.py -k harvest -v`
Expected: PASS (os três).

- [ ] **Step 5: Commit**

```bash
git add back/app/services/treinador.py back/tests/test_treinador.py
git commit -m "feat(treinador): anonimização e colheita best-effort com dedup por fingerprint"
```

---

## Task 6: Hook de colheita no runner (task destacada, fora do caminho crítico)

**Files:**
- Modify: `back/app/runtime/runner.py:186-188` (após sucesso) + método novo
- Test: `back/tests/test_runner_harvest_hook.py` (criar)

**Interfaces:**
- Consumes: `treinador.harvest_project(project_id)`.
- Produces: `RuntimeManager._schedule_harvest(project_id: int) -> None` — dispara `_safe_harvest` via `run_in_executor`, sem bloquear nem propagar erro.

- [ ] **Step 1: Teste — hook não deixa o harvest afetar o resultado**

Criar `back/tests/test_runner_harvest_hook.py`:

```python
from app.runtime.runner import _safe_harvest
from app.services import treinador


def test_safe_harvest_swallows_exceptions(monkeypatch):
    def _boom(pid):
        raise RuntimeError("treino explodiu")
    monkeypatch.setattr(treinador, "harvest_project", _boom)
    # não pode lançar: o resultado da execução do usuário não pode ser afetado
    _safe_harvest(123)


def test_safe_harvest_calls_harvest(monkeypatch):
    calls = []
    monkeypatch.setattr(treinador, "harvest_project", lambda pid: calls.append(pid))
    _safe_harvest(7)
    assert calls == [7]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd back && python -m pytest tests/test_runner_harvest_hook.py -v`
Expected: FAIL (`ImportError: cannot import name '_safe_harvest'`).

- [ ] **Step 3: Adicionar hook em `back/app/runtime/runner.py`**

No topo do módulo (após os imports existentes, ~linha 20), adicionar a função best-effort:

```python
def _safe_harvest(project_id: int) -> None:
    """Colheita do Treinador, isolada do caminho crítico: roda numa thread (executor),
    NUNCA lança. Uma falha aqui não pode virar erro da execução do usuário."""
    try:
        from ..services import treinador

        treinador.harvest_project(project_id)
    except Exception:
        pass
```

Dentro de `RuntimeManager`, adicionar o método:

```python
    def _schedule_harvest(self, project_id: int) -> None:
        """Dispara a colheita como task destacada, sem bloquear nem propagar erro."""
        if self.loop is None:
            return
        try:
            fut = self.loop.run_in_executor(None, _safe_harvest, project_id)
            fut.add_done_callback(lambda f: f.exception())  # drena para não logar warning
        except Exception:
            pass
```

Em `_execute`, no bloco de sucesso (linhas 186-187), disparar ANTES do encadeamento (o `_chain_next` continua igual):

```python
            if execu.status == "success":
                self._schedule_harvest(project.id)
                await self._chain_next(db, project, stage, output_data, execu.build_id)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd back && python -m pytest tests/test_runner_harvest_hook.py -v`
Expected: PASS.

- [ ] **Step 5: Regressão — a suíte de runtime/execução continua verde**

Run: `cd back && python -m pytest tests/ -k "runner or runtime or execu" -v`
Expected: PASS (nenhuma regressão no caminho de execução).

- [ ] **Step 6: Commit**

```bash
git add back/app/runtime/runner.py back/tests/test_runner_harvest_hook.py
git commit -m "feat(runner): hook de colheita destacado após sucesso, isolado do caminho crítico"
```

---

## Task 7: Injeção do few-shot no chat (Construtor/Planejador)

**Files:**
- Modify: `back/app/routers/chat.py:383-385` (montagem de `_orch_ctx`)
- Test: `back/tests/test_chat_fewshot_injection.py` (criar)

**Interfaces:**
- Consumes: `treinador.examples_context(plan)`.
- Efeito: o bloco de exemplos entra em `_orch_ctx`, que flui para `run_construtor`/`run_planejador` via `orchestrate_turn(project_context=...)`. Sem mudança de assinatura.

- [ ] **Step 1: Teste — o contexto do orquestrador inclui os exemplos**

Criar `back/tests/test_chat_fewshot_injection.py`. O objetivo é garantir que, quando há exemplo relevante, o texto passado a `orchestrate_turn` contém o bloco de exemplos. Testamos a função de montagem isolando `orchestrate_turn` com um espião:

```python
import app.routers.chat as chat
from app.services import treinador


def test_fewshot_block_flows_into_orchestrator(monkeypatch):
    captured = {}

    def fake_orch(**kwargs):
        captured["ctx"] = kwargs.get("project_context", "")
        return {"mode": "answer", "phase": "", "plan": {}, "profile": {}}

    monkeypatch.setattr(chat, "orchestrate_turn", fake_orch, raising=False)
    monkeypatch.setattr(treinador, "examples_context",
                        lambda plan: "BLOCO_DE_EXEMPLOS_VALIDADOS")
    # helper que replica a montagem do _orch_ctx com o few-shot
    ctx = chat._build_orch_context_for_test(base="estado do projeto", plan={"contabil": True})
    assert "BLOCO_DE_EXEMPLOS_VALIDADOS" in ctx
```

> Nota ao implementador: para testar sem subir o endpoint SSE inteiro, extraia a concatenação do few-shot numa função pura `_build_orch_context_for_test` (abaixo) e chame-a tanto no teste quanto no endpoint.

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd back && python -m pytest tests/test_chat_fewshot_injection.py -v`
Expected: FAIL (`_build_orch_context_for_test` não existe).

- [ ] **Step 3: Implementar a injeção em `back/app/routers/chat.py`**

Adicionar uma função pura perto de `_source_context` (após linha 225):

```python
def _build_orch_context_for_test(base: str, plan: dict) -> str:
    """Anexa o bloco few-shot do Treinador ao contexto do orquestrador. Isolado numa
    função pura para ser testável sem subir o endpoint de streaming."""
    from ..services import treinador

    ctx = base
    ex_ctx = treinador.examples_context(plan or {})
    if ex_ctx:
        ctx = ctx + "\n\n" + ex_ctx
    return ctx
```

No `chat_stream`, após montar `_src_ctx` (linhas 383-385), anexar os exemplos usando o plano atual do projeto:

```python
        _src_ctx = _source_context(db, project_id)
        if _src_ctx:
            _orch_ctx = _orch_ctx + "\n\n" + _src_ctx
        # few-shot: automações validadas parecidas guiam o Construtor/Planejador.
        # best-effort: nunca pode derrubar o chat.
        try:
            from ..services import treinador

            _ex_ctx = treinador.examples_context(cur_plan)
            if _ex_ctx:
                _orch_ctx = _orch_ctx + "\n\n" + _ex_ctx
        except Exception:
            pass
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd back && python -m pytest tests/test_chat_fewshot_injection.py -v`
Expected: PASS.

- [ ] **Step 5: Regressão do chat**

Run: `cd back && python -m pytest tests/ -k "chat or construtor or workflow_inputs" -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add back/app/routers/chat.py back/tests/test_chat_fewshot_injection.py
git commit -m "feat(chat): injeta exemplos validados (few-shot) no contexto do Construtor/Planejador"
```

---

## Task 8: Captura de eventos de reparo (`erro → correção`)

**Files:**
- Modify: `back/app/schemas.py` (`RepairApplyIn`)
- Modify: `back/app/routers/repair.py:133-151` (`repair_apply`)
- Modify: `back/app/services/treinador.py` (`record_repair_event`)
- Test: `back/tests/test_treinador.py`

**Interfaces:**
- Produces: `treinador.record_repair_event(project_id: int, stage_id: int, error: str, code_before: str, code_after: str) -> None` — best-effort, NUNCA lança.
- `RepairApplyIn` ganha `execution_id: str | None = None` (opcional; usado só para linkar o erro).

**ponytail:** não correlacionamos automaticamente "a correção passou depois" (exigiria observar execuções futuras). Registramos o par `erro → antes/depois`; a validação do projeto (Task 3) já filtra o que vira exemplo. Upgrade path: cruzar `stage_id` com uma execução de sucesso posterior no distill, se a qualidade pedir.

- [ ] **Step 1: Teste — evento de reparo é gravado e nunca lança**

Adicionar em `back/tests/test_treinador.py`:

```python
def test_record_repair_event_stores(monkeypatch, tmp_path):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    treinador.record_repair_event(1, 2, "KeyError: 'x'", "cod velho", "cod novo")
    ev = treinador._repairs()
    assert len(ev) == 1
    assert ev[0]["error"] == "KeyError: 'x'"
    assert ev[0]["code_after"] == "cod novo"


def test_record_repair_event_never_raises(monkeypatch, tmp_path):
    # diretório inválido não pode derrubar o apply do usuário
    monkeypatch.setattr(treinador, "_save", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    treinador.record_repair_event(1, 2, "e", "a", "b")  # não lança
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd back && python -m pytest tests/test_treinador.py -k repair_event -v`
Expected: FAIL (`record_repair_event` não existe).

- [ ] **Step 3: Implementar `record_repair_event` em `treinador.py`**

```python
def record_repair_event(project_id: int, stage_id: int, error: str,
                         code_before: str, code_after: str) -> None:
    """Registra um par erro->correção do Reparador (material de destilação).
    Best-effort: NUNCA lança (é chamado dentro do apply do usuário)."""
    try:
        if (code_before or "").strip() == (code_after or "").strip():
            return
        data = _load(_repairs_path())
        items = data.get("items", [])
        items.append({
            "project_id": project_id, "stage_id": stage_id,
            "error": (error or "")[:2000],
            "code_before": (code_before or "")[:4000],
            "code_after": (code_after or "")[:4000],
        })
        _save(_repairs_path(), {"items": items[-500:]})  # teto: últimos 500
    except Exception:
        pass
```

- [ ] **Step 4: `RepairApplyIn` ganha `execution_id` opcional em `back/app/schemas.py`**

Localizar a classe `RepairApplyIn` e adicionar o campo (manter os campos existentes):

```python
class RepairApplyIn(BaseModel):
    code: str
    execution_id: str | None = None
```

> Verifique os campos atuais de `RepairApplyIn` antes de editar; adicione apenas `execution_id`, não remova nada.

- [ ] **Step 5: Capturar o evento no `repair_apply` (`back/app/routers/repair.py`)**

Em `repair_apply`, antes de sobrescrever o conteúdo (linha 146-149), capturar o "antes" e o erro linkado:

```python
    row = _stage_source(db, project_id, stage)
    code_before = row.content if row else ""
    # registra o par erro->correção para o Treinador (best-effort, fora do caminho crítico)
    error_text = ""
    if body.execution_id:
        execu = db.get(Execution, body.execution_id)
        if execu and execu.project_id == project_id:
            error_text = execu.stderr or ""
    from ..services import treinador
    treinador.record_repair_event(project_id, stage_id, error_text, code_before, body.code)
    if row:
        row.content = body.code
    else:
        db.add(SourceFile(project_id=project_id, path=stage.entry_file, content=body.code))
    db.commit()
    return {"ok": True}
```

`Execution` já está importado em `repair.py` (linha 16). `record_repair_event` é best-effort, então não precisa de try/except aqui.

- [ ] **Step 6: Rodar e ver passar**

Run: `cd back && python -m pytest tests/test_treinador.py -k repair_event -v`
Expected: PASS.

- [ ] **Step 7: Regressão do reparo**

Run: `cd back && python -m pytest tests/ -k repair -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add back/app/schemas.py back/app/routers/repair.py back/app/services/treinador.py back/tests/test_treinador.py
git commit -m "feat(repair): captura par erro->correção como evento de reparo para o Treinador"
```

---

## Task 9: Destilação por limiar + propostas de prompt

**Files:**
- Modify: `back/app/services/treinador.py`
- Test: `back/tests/test_treinador.py`

**Interfaces:**
- Produces:
  - `treinador.DISTILL_THRESHOLD: int = 10`
  - `treinador.new_examples_count() -> int`
  - `treinador.maybe_distill(agent_ids: list[str]) -> int` — se `new_examples_count() >= DISTILL_THRESHOLD`, roda `distill` e zera o contador; retorna nº de propostas geradas.
  - `treinador.distill(agent_ids: list[str]) -> list[dict]` — uma proposta por agente; grava em `proposals.json`. Cada proposta: `{"id","agent_id","current_prompt","proposed_prompt","rationale","status":"pending"}`.

- [ ] **Step 1: Teste — destilação gera proposta por agente (IA mockada)**

Adicionar em `back/tests/test_treinador.py`:

```python
def test_distill_creates_proposal_per_agent(monkeypatch, tmp_path):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    treinador._save(treinador._examples_path(), {"items": [
        _example(True, "xlsx", "xlsx", "conciliação de razão", code="C"),
    ]})
    # mocka a chamada de IA da destilação
    monkeypatch.setattr(
        treinador, "_distill_agent",
        lambda agent_id, examples, repairs: {
            "proposed_prompt": f"melhor prompt para {agent_id}",
            "rationale": "evita erro X",
        },
    )
    props = treinador.distill(["construtor", "planejador"])
    assert len(props) == 2
    assert {p["agent_id"] for p in props} == {"construtor", "planejador"}
    assert all(p["status"] == "pending" for p in props)
    assert treinador._proposals()  # persistiu


def test_maybe_distill_respects_threshold(monkeypatch, tmp_path):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    monkeypatch.setattr(treinador, "DISTILL_THRESHOLD", 3)
    monkeypatch.setattr(treinador, "distill", lambda ids: [{"id": "x"}])
    treinador._save(treinador._meta_path(), {"new_examples": 2})
    assert treinador.maybe_distill(["construtor"]) == 0  # abaixo do limiar
    treinador._save(treinador._meta_path(), {"new_examples": 3})
    assert treinador.maybe_distill(["construtor"]) == 1
    assert treinador.new_examples_count() == 0  # zerou após destilar
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd back && python -m pytest tests/test_treinador.py -k distill -v`
Expected: FAIL.

- [ ] **Step 3: Implementar destilação em `treinador.py`**

```python
DISTILL_THRESHOLD = 10


def new_examples_count() -> int:
    return int(_load(_meta_path()).get("new_examples", 0))


def _reset_new_examples() -> None:
    meta = _load(_meta_path())
    meta["new_examples"] = 0
    _save(_meta_path(), meta)


def _current_prompt(agent_id: str) -> str:
    """Prompt efetivo atual do agente (o que get_prompt devolveria)."""
    from . import ai_config
    from ..routers.ai import _DEFAULT_PROMPTS

    return ai_config.get_prompt(agent_id, _DEFAULT_PROMPTS.get(agent_id, ""))


def _distill_agent(agent_id: str, examples: list[dict], repairs: list[dict]) -> dict | None:
    """Chama o Treinador para propor um prompt melhor para um agente. None em falha."""
    from ..config import settings
    if not settings.ai_enabled:
        return None
    from .orchestrator import call_agent

    payload = {
        "agente": agent_id,
        "prompt_atual": _current_prompt(agent_id),
        "exemplos_validados": [{"plan": e.get("plan"), "code": (e.get("code") or "")[:1500]}
                               for e in examples[:5]],
        "reparos": [{"error": r.get("error"), "code_after": (r.get("code_after") or "")[:800]}
                    for r in repairs[:5]],
    }
    raw = call_agent(
        "treinador", TREINADOR_PROMPT,
        [{"role": "user", "content": "TAREFA: DESTILAR\n"
          + json.dumps(payload, ensure_ascii=False)}],
        json_mode=True,
    )
    try:
        data = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return None
    prompt = (data.get("proposed_prompt") or "").strip()
    if not prompt:
        return None
    return {"proposed_prompt": prompt, "rationale": (data.get("rationale") or "").strip()}


def _next_proposal_id(items: list[dict]) -> str:
    n = 1 + max((int(p.get("id", "0")) for p in items if str(p.get("id", "")).isdigit()), default=0)
    return str(n)


def distill(agent_ids: list[str]) -> list[dict]:
    """Gera uma proposta de prompt por agente, a partir dos exemplos e reparos.
    Persiste em proposals.json com status 'pending'. Best-effort por agente."""
    examples = _examples()
    repairs = _repairs()
    data = _load(_proposals_path())
    items = data.get("items", [])
    created = []
    for agent_id in agent_ids:
        try:
            out = _distill_agent(agent_id, examples, repairs)
        except Exception:
            out = None
        if not out:
            continue
        prop = {
            "id": _next_proposal_id(items + created),
            "agent_id": agent_id,
            "current_prompt": _current_prompt(agent_id),
            "proposed_prompt": out["proposed_prompt"],
            "rationale": out["rationale"],
            "status": "pending",
        }
        created.append(prop)
    if created:
        _save(_proposals_path(), {"items": items + created})
    return created


def maybe_distill(agent_ids: list[str]) -> int:
    """Roda a destilação só quando acumulou exemplos novos suficientes (limiar).
    Zera o contador ao destilar. Retorna nº de propostas geradas. NUNCA lança."""
    try:
        if new_examples_count() < DISTILL_THRESHOLD:
            return 0
        props = distill(agent_ids)
        _reset_new_examples()
        return len(props)
    except Exception:
        return 0
```

- [ ] **Step 4: Disparar `maybe_distill` após colher (no `harvest_project`)**

Em `harvest_project`, logo após `_bump_new_examples()` e antes de `return True`, adicionar o gatilho por limiar (best-effort):

```python
        _bump_new_examples()
        maybe_distill(["construtor", "planejador", "reparador", "classificador", "nomeador", "assistente"])
        return True
```

- [ ] **Step 5: Rodar e ver passar**

Run: `cd back && python -m pytest tests/test_treinador.py -k distill -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add back/app/services/treinador.py back/tests/test_treinador.py
git commit -m "feat(treinador): destilação por limiar gera propostas de prompt por agente"
```

---

## Task 10: Aprovação de propostas — API

**Files:**
- Modify: `back/app/services/treinador.py` (`list_proposals`, `resolve_proposal`)
- Modify: `back/app/routers/ai.py` (endpoints)
- Test: `back/tests/test_treinador.py`, `back/tests/test_ai_proposals_api.py` (criar)

**Interfaces:**
- Produces:
  - `treinador.list_proposals(status: str = "pending") -> list[dict]`
  - `treinador.resolve_proposal(proposal_id: str, approved: bool) -> dict | None` — se aprovado, chama `ai_config.apply_prompt(agent_id, proposed_prompt)`; marca status; retorna a proposta.
  - Endpoints (admin): `GET /api/ai/treinador/proposals`, `POST /api/ai/treinador/proposals/{id}/approve`, `POST /api/ai/treinador/proposals/{id}/reject`, `POST /api/ai/treinador/distill` (dispara destilação manual).

- [ ] **Step 1: Teste — aprovar aplica o prompt e marca a proposta**

Adicionar em `back/tests/test_treinador.py`:

```python
def test_approve_applies_prompt(monkeypatch, tmp_path):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    treinador._save(treinador._proposals_path(), {"items": [
        {"id": "1", "agent_id": "construtor", "current_prompt": "velho",
         "proposed_prompt": "novo", "rationale": "r", "status": "pending"},
    ]})
    applied = {}
    from app.services import ai_config
    monkeypatch.setattr(ai_config, "apply_prompt",
                        lambda aid, p: applied.setdefault(aid, p))
    out = treinador.resolve_proposal("1", approved=True)
    assert out["status"] == "approved"
    assert applied == {"construtor": "novo"}
    # não aparece mais em pendentes
    assert treinador.list_proposals("pending") == []


def test_reject_does_not_apply(monkeypatch, tmp_path):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    treinador._save(treinador._proposals_path(), {"items": [
        {"id": "1", "agent_id": "construtor", "current_prompt": "v",
         "proposed_prompt": "n", "rationale": "r", "status": "pending"},
    ]})
    from app.services import ai_config
    called = []
    monkeypatch.setattr(ai_config, "apply_prompt", lambda aid, p: called.append(aid))
    out = treinador.resolve_proposal("1", approved=False)
    assert out["status"] == "rejected"
    assert called == []
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd back && python -m pytest tests/test_treinador.py -k "approve or reject" -v`
Expected: FAIL.

- [ ] **Step 3: Implementar `list_proposals` e `resolve_proposal`**

```python
def list_proposals(status: str = "pending") -> list[dict]:
    return [p for p in _proposals() if p.get("status") == status]


def resolve_proposal(proposal_id: str, approved: bool) -> dict | None:
    """Aprova (aplica o prompt na fonte certa) ou rejeita uma proposta. Retorna a
    proposta atualizada, ou None se não existe / já resolvida."""
    data = _load(_proposals_path())
    items = data.get("items", [])
    target = next((p for p in items if str(p.get("id")) == str(proposal_id)), None)
    if target is None or target.get("status") != "pending":
        return None
    if approved:
        from . import ai_config

        ai_config.apply_prompt(target["agent_id"], target["proposed_prompt"])
        target["status"] = "approved"
    else:
        target["status"] = "rejected"
    _save(_proposals_path(), {"items": items})
    return target
```

- [ ] **Step 4: Endpoints em `back/app/routers/ai.py`**

Adicionar ao final do arquivo (o `router` e `_require_admin` já existem):

```python
from ..services import treinador as _treinador


@router.get("/treinador/proposals")
def treinador_proposals(user: User = Depends(get_current_user)):
    _require_admin(user)
    return {"proposals": _treinador.list_proposals("pending")}


@router.post("/treinador/proposals/{proposal_id}/approve")
def treinador_approve(proposal_id: str, user: User = Depends(get_current_user)):
    _require_admin(user)
    out = _treinador.resolve_proposal(proposal_id, approved=True)
    if out is None:
        raise HTTPException(status_code=404, detail="Proposta não encontrada ou já resolvida.")
    return {"ok": True, "proposal": out}


@router.post("/treinador/proposals/{proposal_id}/reject")
def treinador_reject(proposal_id: str, user: User = Depends(get_current_user)):
    _require_admin(user)
    out = _treinador.resolve_proposal(proposal_id, approved=False)
    if out is None:
        raise HTTPException(status_code=404, detail="Proposta não encontrada ou já resolvida.")
    return {"ok": True, "proposal": out}


@router.post("/treinador/distill")
def treinador_distill(user: User = Depends(get_current_user)):
    """Dispara a destilação manualmente (além do gatilho automático por limiar)."""
    _require_admin(user)
    props = _treinador.distill(
        ["construtor", "planejador", "reparador", "classificador", "nomeador", "assistente"]
    )
    return {"ok": True, "created": len(props)}
```

- [ ] **Step 5: Teste dos endpoints (criar `back/tests/test_ai_proposals_api.py`)**

Seguir o padrão de teste de API já usado no projeto (client autenticado como admin). Exemplo mínimo:

```python
from app.services import treinador


def test_list_proposals_requires_admin(client_admin, monkeypatch, tmp_path):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    treinador._save(treinador._proposals_path(), {"items": [
        {"id": "1", "agent_id": "construtor", "current_prompt": "v",
         "proposed_prompt": "n", "rationale": "r", "status": "pending"},
    ]})
    r = client_admin.get("/api/ai/treinador/proposals")
    assert r.status_code == 200
    assert len(r.json()["proposals"]) == 1
```

> Reutilize a fixture de client admin existente na suíte (ver `back/tests/` — mesma usada para `PUT /api/ai/graph`, que exige admin). Se não houver, o teste do Step 1/3 (nível de serviço) já cobre a lógica; este é complementar.

- [ ] **Step 6: Rodar e ver passar**

Run: `cd back && python -m pytest tests/test_treinador.py -k "approve or reject" tests/test_ai_proposals_api.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add back/app/services/treinador.py back/app/routers/ai.py back/tests/
git commit -m "feat(treinador): API de propostas (listar/aprovar/rejeitar/destilar)"
```

---

## Task 11: UI de propostas na tela de Agentes

**Files:**
- Modify: `front/src/pages/Agents.tsx` (nova seção admin "Propostas do Treinador")

**Interfaces:**
- Consumes: `GET /api/ai/treinador/proposals`, `POST /api/ai/treinador/proposals/{id}/approve|reject`, `POST /api/ai/treinador/distill`.

- [ ] **Step 1: Componente `TreinadorProposals` no `Agents.tsx`**

Adicionar o componente (antes do `export default` ou como função no mesmo arquivo, seguindo o padrão dos outros painéis):

```tsx
interface Proposal {
  id: string;
  agent_id: string;
  current_prompt: string;
  proposed_prompt: string;
  rationale: string;
  status: string;
}

function TreinadorProposals({ isAdmin }: { isAdmin: boolean }) {
  const [items, setItems] = useState<Proposal[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  async function load() {
    try {
      const d = await api.get<{ proposals: Proposal[] }>("/api/ai/treinador/proposals");
      setItems(d.proposals);
    } catch {
      /* silencioso: seção é opcional */
    }
  }
  useEffect(() => {
    if (isAdmin) load();
  }, [isAdmin]);

  async function resolve(id: string, action: "approve" | "reject") {
    setBusy(id);
    try {
      await api.post(`/api/ai/treinador/proposals/${id}/${action}`, {});
      await load();
    } finally {
      setBusy(null);
    }
  }

  if (!isAdmin || items.length === 0) return null;
  return (
    <div className="card mt-5 overflow-hidden">
      <div className="border-b border-line px-5 py-3" style={{ background: "var(--surface-glass)" }}>
        <span className="text-xs font-bold text-ink">
          Propostas do Treinador ({items.length})
        </span>
        <p className="mt-0.5 text-[11px] text-ink3">
          Melhorias de prompt sugeridas a partir de automações validadas. Aprovar aplica de verdade.
        </p>
      </div>
      <div className="flex flex-col gap-4 p-4">
        {items.map((p) => (
          <div key={p.id} className="rounded-xl border border-line p-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-bold text-ink">{p.agent_id}</span>
              <div className="flex gap-2">
                <button
                  onClick={() => resolve(p.id, "approve")}
                  disabled={busy === p.id}
                  className="btn-accent py-1.5 text-xs disabled:opacity-40"
                >
                  Aprovar
                </button>
                <button
                  onClick={() => resolve(p.id, "reject")}
                  disabled={busy === p.id}
                  className="btn-outline py-1.5 text-xs disabled:opacity-40"
                >
                  Rejeitar
                </button>
              </div>
            </div>
            <p className="mb-2 text-[12.5px] text-ink2">{p.rationale}</p>
            <div className="grid gap-2 md:grid-cols-2">
              <div>
                <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-ink3">Atual</div>
                <textarea readOnly rows={6} value={p.current_prompt}
                  className="input resize-y font-mono text-[11px] leading-relaxed"
                  style={{ background: "var(--surface-2)", color: "var(--text-2)" }} />
              </div>
              <div>
                <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-ink3">Proposto</div>
                <textarea readOnly rows={6} value={p.proposed_prompt}
                  className="input resize-y font-mono text-[11px] leading-relaxed"
                  style={{ borderColor: "var(--accent)", background: "var(--accent-soft)" }} />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Renderizar a seção**

No `Agents()`, logo após o `<div className="flex flex-col gap-5 lg:flex-row ...">...</div>` que fecha o board+painel (após linha 436, antes de fechar o `<main>`), inserir:

```tsx
        <TreinadorProposals isAdmin={isAdmin} />
```

- [ ] **Step 3: Verificar `api.post` existe em `front/src/lib/api.ts`**

Run: `cd front && node -e "const s=require('fs').readFileSync('src/lib/api.ts','utf8'); if(!/post\b/.test(s)) { console.error('FALTA api.post'); process.exit(1)} console.log('ok')"`
Expected: `ok`. Se faltar, adicionar um método `post(path, body)` espelhando o `put` existente.

- [ ] **Step 4: Build do frontend**

Run: `cd front && npm run build`
Expected: build sem erros.

- [ ] **Step 5: Commit**

```bash
git add front/src/pages/Agents.tsx front/src/lib/api.ts
git commit -m "feat(agents): UI de propostas do Treinador (diff + aprovar/rejeitar)"
```

---

## Task 12: Verificação de ponta a ponta (regressão do backend)

**Files:** nenhum (verificação).

- [ ] **Step 1: Suíte completa do backend**

Run: `cd back && python -m pytest -q`
Expected: toda a suíte verde (nenhuma regressão nos caminhos existentes: chat, orchestrator, runner, repair, wizard, projects).

- [ ] **Step 2: Sanidade de import da app**

Run: `cd back && python -c "import main; print('app importou ok')"`
Expected: sem erro de import (roster, endpoints e hooks carregam).

- [ ] **Step 3: Health check manual do fluxo (opcional, com IA ligada)**

Com o backend rodando localmente, publicar uma automação de exemplo, executá-la com sucesso, e confirmar que `back/storage/treinador/examples.json` ganhou um item com `plan` anonimizado e `code`. Confirmar que uma segunda execução da mesma versão NÃO duplica o exemplo.

- [ ] **Step 4: Commit final (se algo foi ajustado na verificação)**

```bash
git add -A
git commit -m "test: verificação de ponta a ponta da auto-evolução dos agentes"
```

---

## Self-Review (cobertura x decisões fechadas)

- **Mecanismo (few-shot + destilação):** Tasks 4/7 (few-shot) e 9/10/11 (destilação + aprovação). ✓
- **Sinal de validado (live + sucesso + sem erro recente):** Task 3 (`is_validated`). ✓
- **Confidencialidade (só plano+código, plano anonimizado, falha => não grava):** Task 5 (`anonymize_plan` retorna None em falha; `harvest_project` só grava com anon válido; nunca inclui dados/IO). ✓
- **Seleção heurística K=2:** Task 4 (`select_examples`). ✓
- **Escopo (7 agentes, Reparador incluído):** Task 1 (roster), Task 8 (eventos de reparo), Task 9 (`reparador` na lista de destilação). ✓
- **Agente Treinador fora do caminho crítico:** Tasks 1/5/6 (best-effort, task destacada). ✓
- **Gatilho (colher auto ao validar; destilar por limiar):** Task 6 (hook no runner) + Task 9 (`maybe_distill` threshold). ✓
- **Aprovação (diff em AI Instructions; aplica na fonte que get_prompt lê):** Task 2 (`apply_prompt`), Task 10 (API), Task 11 (UI). ✓
- **Armazenamento (JSON em STORAGE_DIR):** Task 1 (store). ✓
- **Organograma (pipeline honesto + camada meta):** Task 0. ✓

**Placeholder scan:** nenhum "TBD/TODO/implementar depois" — todo passo tem código ou comando concreto. ✓
**Consistência de tipos:** `harvest_project`, `is_validated`, `select_examples`, `examples_context`, `record_repair_event`, `distill`, `maybe_distill`, `list_proposals`, `resolve_proposal`, `apply_prompt` usados com as mesmas assinaturas entre tasks. ✓

**Nota de ponytail (simplificações deliberadas):**
- Correlação "a correção passou depois" não é automática (Task 8) — teto conhecido, upgrade path descrito.
- Sem embeddings; heurística sobre o plano (Task 4) — trocar por vetor só se a heurística provar fraca.
- Dedup por fingerprint de código, não por `Build.hash` — evita depender da semântica de build; re-colhe quando o código muda.
