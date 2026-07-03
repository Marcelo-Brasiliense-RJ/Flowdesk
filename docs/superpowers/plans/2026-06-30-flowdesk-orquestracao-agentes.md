# Orquestração de Agentes do FlowDesk — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar a "equipe de agentes" (hoje um assistente único que alterna fases) num pipeline determinístico real, onde Assistente, Planejador, Construtor, Nomeador, Classificador e Reparador são chamadas de IA separadas, encadeadas em código, lendo prompt/modelo/temperatura do grafo editável.

**Architecture:** Máquina de estados por projeto (`Project.phase`). Um Assistente fino (roteador) classifica a intenção e direciona: nova automação → Planejador (entrevista que preenche um PLANO em JSON) → confirmação humana → Construtor (lê o plano, não a transcrição) → Nomeador (grava nome/descrição no card). O Classificador é um cérebro contábil que atua em design (enriquece o plano) e em runtime (classify.py), ambos lendo um perfil contábil único por projeto. O Reparador mantém seu loop, agora recebendo o plano + perfil. Cada agente lê prompt/modelo/temperatura de `ai_config` (grafo do builder).

**Tech Stack:** FastAPI + SQLAlchemy + SQLite (back), React 18 + TypeScript + Vite + Vitest (front), OpenAI client (compatível), pytest.

## Global Constraints

- Sem travessão "em dash" em nenhum texto de produto ou prompt. Use vírgula.
- Português correto e acentuado em prompts, descrições e mensagens ao usuário.
- Integridade fiscal: NUNCA inferir regime tributário ou regra fiscal sem confirmação humana. Campo inferido de arquivo só entra no perfil após o usuário confirmar.
- O código gerado pelo Construtor segue as regras já vigentes do `SYSTEM_PROMPT` (SDK flowdesk_sdk, pandas 2.x sem `df.append`, proibido placeholder/TODO, sempre gravar o arquivo de saída).
- Modelo por agente é lido do grafo (`ai_config`); jamais hardcode o modelo nas chamadas.
- Persistência de config continua em `STORAGE_DIR/ai_config.json` (sem migração de schema para a config de IA).
- Compatibilidade: projetos antigos (sem `phase`/`plan`) continuam funcionando — `phase` vazio cai no fluxo de chat atual até a primeira intenção roteada.

---

## Decisões de design (referência, vindas do grill)

| Tema | Decisão |
|------|---------|
| Escopo | Orquestração total: cada agente é chamada de IA separada e encadeada |
| Motor | Pipeline determinístico (FSM em código); prompts/modelo/temp do grafo |
| Assistente | Porta + roteador fino (classifica intenção, não entrevista) |
| Plano | JSON com schema fixo, persistido no projeto |
| Transição Planejador→Construtor | Schema completo + confirmação humana |
| Classificador | Cérebro contábil em design + runtime (os dois) |
| Perfil contábil | Único por projeto, fonte única para design e runtime |
| Nomeador | Roda após o Construtor, grava nome/descrição na hora, respeita nome do usuário |
| Reparador | Mantém o loop; passa a receber plano + perfil |
| Board | Tudo do grafo, incl. modelo por agente |
| Ajustes | Router com 3 destinos: nova / ajuste→Construtor / dúvida→Assistente |
| Bootstrap perfil | Na entrevista, quando contábil; inferidos só após confirmação |
| UX | Voz única + selos de fase + plano consolidado na confirmação |

---

## Mapa de dependências e estratégia de subagentes

```
Stage 1  Fundação (estado + schemas + ai_config)          [SEQUENCIAL — raiz]
   │
   ▼
Stage 2  Motor (FSM + roteador + selagem)                 [SEQUENCIAL — espera Stage 1]
   │
   ├──────────────┬──────────────┬──────────────┬──────────────┐
   ▼              ▼              ▼              ▼              ▼
 Stage 3a       Stage 3b       Stage 3c       Stage 3d       Stage 3e        Stage 4
 Planejador     Construtor     Nomeador       Classificador  Reparador       Frontend + Board
 [PARALELO]     [PARALELO]     [PARALELO]     [PARALELO]     [PARALELO]      [PARALELO c/ Stage 3]
   └──────────────┴──────────────┴──────────────┴──────────────┴──────────────┘
                                      │
                                      ▼
                            Stage 5  Integração + reset do seed + E2E   [SEQUENCIAL — espera 3a-e e 4]
```

**Regras de dispatch (conforme pedido do usuário):**
- **Stage 1** roda sozinho e precisa fechar (testes verdes, commit) antes de qualquer outra coisa: todos consomem o schema e o estado.
- **Stage 2** roda depois do 1, sozinho. Define o CONTRATO de chamada de agente que as etapas 3 consomem.
- **Stages 3a–3e e Stage 4** são independentes entre si (tocam arquivos/funções diferentes) → **um subagente por etapa, em paralelo**. A dependência entre Planejador (produz plano) e Construtor (consome plano) é de DADO em runtime, não de código: como o schema do plano já está congelado no Stage 1, os dois podem ser construídos ao mesmo tempo.
- **Stage 5** é o ponto de encontro: um subagente que **só inicia quando 3a–3e e 4 estiverem fechados** (verdes + commitados), faz a fiação final, reseta o grafo-semente e roda o teste E2E.

**Para tarefas dependentes (1→2→{3,4}→5):** o subagente da etapa seguinte aguarda a confirmação de que a anterior fechou corretamente (suite verde + commit na branch). Não inicie a próxima sobre uma etapa que ainda está rodando ou falhou.

---

## Estrutura de arquivos

**Backend**
- Modificar `back/app/models.py` — novas colunas em `Project`: `phase`, `plan`, `accounting_profile`.
- Criar `back/app/services/plan_schema.py` — schema/validação do plano e do perfil contábil (Pydantic), fonte única.
- Modificar `back/app/services/ai_config.py` — `get_temp(agent_id, default)` e `get_agent_model(agent_id)`.
- Criar `back/app/routers/orchestrator.py` — FSM + roteador + funções de chamada por agente (Planejador, Construtor, Nomeador, enriquecimento contábil). Centraliza o que hoje está espalhado em `chat.py`.
- Modificar `back/app/routers/chat.py` — `chat_stream` delega ao orquestrador; remover `_is_build_intent` como gatilho único.
- Modificar `back/app/routers/classify.py` — ler `accounting_profile` (plano de contas) do projeto.
- Modificar `back/app/routers/repair.py` — injetar plano + perfil no contexto.
- Modificar `back/app/routers/projects.py` e `back/app/routers/wizard.py` — Nomeador passa a chamar a função única do orquestrador.
- Modificar `back/app/schemas.py` — schemas de saída do plano/perfil/fase.

**Frontend**
- Modificar `front/src/components/SmartChat.tsx` — selos de fase + render do plano consolidado na confirmação.
- Modificar `front/src/pages/Agents.tsx` — seletor de modelo por agente.

**Migração de dados**
- `Project.phase/plan/accounting_profile` novos (SQLite: colunas nullable com default; sem Alembic no projeto, usar `Base.metadata.create_all` + backfill defensivo no acesso).
- Reset do grafo salvo no banco (que ainda mostra "Descritor") em Stage 5.

---

## Stage 1 — Fundação: estado, schema do plano, perfil contábil, ai_config

**Objetivo:** congelar o contrato de dados que todas as outras etapas consomem.

### Task 1.1: Schema do plano e do perfil contábil

**Files:**
- Create: `back/app/services/plan_schema.py`
- Test: `back/tests/test_plan_schema.py`

**Interfaces:**
- Produces:
  - `class PlanColuna(BaseModel): nome: str; significado: str = ""`
  - `class PlanFonte(BaseModel): formato: str = ""; descricao: str = ""; colunas: list[PlanColuna] = []`
  - `class PlanSaida(BaseModel): formato: str = ""; contrato: str = ""; colunas: list[PlanColuna] = []; destino_sistema: str | None = None`
  - `class Plan(BaseModel): fonte: PlanFonte = PlanFonte(); regra_negocio: str = ""; saida: PlanSaida = PlanSaida(); gatilho: str = ""; tratamento_erros: str = ""; contabil: bool = False; notas: str = ""; selado: bool = False`
  - `class ContaContabil(BaseModel): codigo: str; nome: str = ""`
  - `class AccountingProfile(BaseModel): regime: str | None = None; plano_de_contas: list[ContaContabil] = []; erp_destino: str | None = None; layout_destino: str | None = None; regras_fiscais: list[str] = []; confirmado: bool = False`
  - `CAMPOS_CRITICOS = ("fonte.formato", "regra_negocio", "saida.formato", "gatilho")`
  - `def plan_missing_fields(plan: Plan) -> list[str]` — retorna os campos críticos vazios (caminho pontilhado).
  - `def plan_is_complete(plan: Plan) -> bool` — `not plan_missing_fields(plan)`.

- [ ] **Step 1: Write the failing test**

```python
# back/tests/test_plan_schema.py
from app.services.plan_schema import Plan, PlanFonte, PlanSaida, plan_missing_fields, plan_is_complete

def test_empty_plan_lists_all_critical_fields():
    assert plan_missing_fields(Plan()) == ["fonte.formato", "regra_negocio", "saida.formato", "gatilho"]
    assert plan_is_complete(Plan()) is False

def test_full_plan_is_complete():
    p = Plan(
        fonte=PlanFonte(formato="xlsx"),
        regra_negocio="somar valores por cliente",
        saida=PlanSaida(formato="xlsx"),
        gatilho="manual",
    )
    assert plan_missing_fields(p) == []
    assert plan_is_complete(p) is True

def test_partial_plan_reports_only_missing():
    p = Plan(fonte=PlanFonte(formato="csv"), gatilho="manual")
    assert plan_missing_fields(p) == ["regra_negocio", "saida.formato"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd back && python -m pytest tests/test_plan_schema.py -v`
Expected: FAIL com `ModuleNotFoundError: app.services.plan_schema`.

- [ ] **Step 3: Write minimal implementation**

```python
# back/app/services/plan_schema.py
"""Schema único do PLANO (contrato Planejador -> Construtor) e do PERFIL contábil.

Fonte única de verdade: o Construtor lê o Plan (não a transcrição do chat) e o
Classificador (design e runtime) lê o AccountingProfile.
"""
from __future__ import annotations

from pydantic import BaseModel


class PlanColuna(BaseModel):
    nome: str
    significado: str = ""


class PlanFonte(BaseModel):
    formato: str = ""          # xlsx | csv | pdf | sheets
    descricao: str = ""
    colunas: list[PlanColuna] = []


class PlanSaida(BaseModel):
    formato: str = ""
    contrato: str = ""          # regras do destino (ex.: layout de importação do Domínio)
    colunas: list[PlanColuna] = []
    destino_sistema: str | None = None  # ex.: "Domínio", "SAP"


class Plan(BaseModel):
    fonte: PlanFonte = PlanFonte()
    regra_negocio: str = ""
    saida: PlanSaida = PlanSaida()
    gatilho: str = ""           # manual | agendado | webhook
    tratamento_erros: str = ""
    contabil: bool = False
    notas: str = ""
    selado: bool = False


class ContaContabil(BaseModel):
    codigo: str
    nome: str = ""


class AccountingProfile(BaseModel):
    regime: str | None = None   # simples | presumido | real
    plano_de_contas: list[ContaContabil] = []
    erp_destino: str | None = None
    layout_destino: str | None = None
    regras_fiscais: list[str] = []
    confirmado: bool = False


CAMPOS_CRITICOS = ("fonte.formato", "regra_negocio", "saida.formato", "gatilho")


def _get_path(plan: Plan, dotted: str):
    obj = plan
    for part in dotted.split("."):
        obj = getattr(obj, part)
    return obj


def plan_missing_fields(plan: Plan) -> list[str]:
    return [c for c in CAMPOS_CRITICOS if not str(_get_path(plan, c) or "").strip()]


def plan_is_complete(plan: Plan) -> bool:
    return not plan_missing_fields(plan)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd back && python -m pytest tests/test_plan_schema.py -v`
Expected: PASS (3 testes).

- [ ] **Step 5: Commit**

```bash
git add back/app/services/plan_schema.py back/tests/test_plan_schema.py
git commit -m "feat(orchestrator): schema do plano e do perfil contabil (fonte unica)"
```

### Task 1.2: Estado por projeto (phase, plan, accounting_profile)

**Files:**
- Modify: `back/app/models.py:70-99` (classe `Project`)
- Modify: `back/app/schemas.py` (ProjectOut)
- Test: `back/tests/test_project_state.py`

**Interfaces:**
- Produces: colunas `Project.phase: str` (default `""`), `Project.plan: dict` (default `{}`), `Project.accounting_profile: dict` (default `{}`). Fases válidas: `"" | "planning" | "building" | "naming" | "done"`.

- [ ] **Step 1: Write the failing test**

```python
# back/tests/test_project_state.py
from app.models import Project

def test_project_has_orchestration_state():
    p = Project(org_id=1, name="x", subdomain="x")
    assert p.phase == ""
    assert p.plan == {}
    assert p.accounting_profile == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd back && python -m pytest tests/test_project_state.py -v`
Expected: FAIL (`AttributeError` em `phase`).

- [ ] **Step 3: Add the columns**

Em `back/app/models.py`, dentro da classe `Project`, após `wizard_dirty` (linha ~95):

```python
    # orquestração de agentes (Fase 2): estado da máquina + artefatos
    # phase: "" (não iniciado) | planning | building | naming | done
    phase: Mapped[str] = mapped_column(String(20), default="")
    # plano selado (contrato Planejador -> Construtor) — schema em services/plan_schema.Plan
    plan: Mapped[dict] = mapped_column(JSON, default=dict)
    # perfil contábil/fiscal do projeto — schema em services/plan_schema.AccountingProfile
    accounting_profile: Mapped[dict] = mapped_column(JSON, default=dict)
```

Em `back/app/schemas.py`, classe `ProjectOut`, adicionar:

```python
    phase: str = ""
    plan: dict = {}
    accounting_profile: dict = {}
```

- [ ] **Step 4: Run test + verificar criação de tabela**

Run: `cd back && python -m pytest tests/test_project_state.py -v`
Expected: PASS.
Run: `cd back && python -c "from app.database import Base, engine; Base.metadata.create_all(engine); print('ok')"`
Expected: `ok` (cria colunas em DB novo). Para DB existente, ver Task 1.3.

- [ ] **Step 5: Commit**

```bash
git add back/app/models.py back/app/schemas.py back/tests/test_project_state.py
git commit -m "feat(orchestrator): estado de orquestracao no Project (phase/plan/accounting_profile)"
```

### Task 1.3: Backfill defensivo para bancos existentes

**Files:**
- Modify: `back/app/database.py` (ou o módulo onde roda `create_all` no startup)
- Test: `back/tests/test_migration_backfill.py`

**Contexto:** o projeto não usa Alembic. SQLite não adiciona colunas via `create_all` em tabela já existente. Adicionar um `ALTER TABLE` idempotente no startup.

**Interfaces:**
- Produces: `def ensure_project_columns(engine) -> None` — adiciona `phase`, `plan`, `accounting_profile` se faltarem.

- [ ] **Step 1: Write the failing test**

```python
# back/tests/test_migration_backfill.py
import sqlalchemy as sa
from app.database import ensure_project_columns

def test_ensure_columns_idempotent(tmp_path):
    eng = sa.create_engine(f"sqlite:///{tmp_path/'t.db'}")
    with eng.begin() as c:
        c.execute(sa.text("CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT)"))
    ensure_project_columns(eng)   # adiciona
    ensure_project_columns(eng)   # idempotente, não quebra
    with eng.begin() as c:
        cols = {r[1] for r in c.execute(sa.text("PRAGMA table_info(projects)"))}
    assert {"phase", "plan", "accounting_profile"} <= cols
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd back && python -m pytest tests/test_migration_backfill.py -v`
Expected: FAIL (`ImportError: ensure_project_columns`).

- [ ] **Step 3: Implement**

Em `back/app/database.py`:

```python
import sqlalchemy as sa

def ensure_project_columns(engine) -> None:
    """Adiciona colunas de orquestração a bancos pré-existentes (sem Alembic)."""
    wanted = {"phase": "VARCHAR(20) DEFAULT ''",
              "plan": "JSON DEFAULT '{}'",
              "accounting_profile": "JSON DEFAULT '{}'"}
    with engine.begin() as conn:
        existing = {r[1] for r in conn.execute(sa.text("PRAGMA table_info(projects)"))}
        for name, ddl in wanted.items():
            if name not in existing:
                conn.execute(sa.text(f"ALTER TABLE projects ADD COLUMN {name} {ddl}"))
```

Chamar `ensure_project_columns(engine)` logo após o `create_all` no startup do app (onde já se inicializa o schema).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd back && python -m pytest tests/test_migration_backfill.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add back/app/database.py back/tests/test_migration_backfill.py
git commit -m "feat(orchestrator): backfill idempotente das colunas de orquestracao"
```

### Task 1.4: ai_config — temperatura e modelo por agente

**Files:**
- Modify: `back/app/services/ai_config.py`
- Test: `back/tests/test_ai_config_per_agent.py`

**Interfaces:**
- Produces:
  - `def get_temp(agent_id: str, default: float = 0.2) -> float` — lê `temp` do nó no grafo; `"padrão"`/inválido → `default`.
  - `def get_agent_model(agent_id: str) -> str` — lê `model` do nó; vazio → `get_model()`.

- [ ] **Step 1: Write the failing test**

```python
# back/tests/test_ai_config_per_agent.py
from app.services import ai_config

def test_temp_parses_string_and_falls_back(monkeypatch):
    monkeypatch.setattr(ai_config, "_load", lambda: {"graph": {"agents": [
        {"id": "construtor", "temp": "0.2", "model": "gpt-4.1"},
        {"id": "nomeador", "temp": "padrão"},
    ]}})
    assert ai_config.get_temp("construtor") == 0.2
    assert ai_config.get_temp("nomeador", default=0.3) == 0.3   # "padrão" -> default
    assert ai_config.get_temp("inexistente", default=0.1) == 0.1

def test_agent_model_falls_back_to_shared(monkeypatch):
    monkeypatch.setattr(ai_config, "_load", lambda: {"model": "gpt-4o", "graph": {"agents": [
        {"id": "construtor", "model": "gpt-4.1"},
        {"id": "nomeador", "model": ""},
    ]}})
    assert ai_config.get_agent_model("construtor") == "gpt-4.1"
    assert ai_config.get_agent_model("nomeador") == "gpt-4o"   # vazio -> compartilhado
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd back && python -m pytest tests/test_ai_config_per_agent.py -v`
Expected: FAIL (`AttributeError: get_temp`).

- [ ] **Step 3: Implement** (adicionar ao final de `ai_config.py`)

```python
def get_temp(agent_id: str, default: float = 0.2) -> float:
    """Temperatura efetiva do agente (lida do grafo; 'padrão'/inválido -> default)."""
    a = _graph_agent(agent_id)
    raw = (a or {}).get("temp")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def get_agent_model(agent_id: str) -> str:
    """Modelo efetivo do agente: modelo do nó no grafo -> modelo compartilhado."""
    a = _graph_agent(agent_id)
    if a and isinstance(a.get("model"), str) and a["model"].strip():
        return a["model"].strip()
    return get_model()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd back && python -m pytest tests/test_ai_config_per_agent.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add back/app/services/ai_config.py back/tests/test_ai_config_per_agent.py
git commit -m "feat(orchestrator): get_temp/get_agent_model por agente em ai_config"
```

**Gate da Stage 1:** `cd back && python -m pytest tests/test_plan_schema.py tests/test_project_state.py tests/test_migration_backfill.py tests/test_ai_config_per_agent.py -v` todos verdes. Só então liberar Stage 2.

---

## Stage 2 — Motor: roteador + FSM + selagem (espera Stage 1)

**Objetivo:** o coração determinístico. Define o CONTRATO de chamada de agente que a Stage 3 consome.

### Task 2.1: Função genérica de chamada de agente

**Files:**
- Create: `back/app/routers/orchestrator.py`
- Test: `back/tests/test_orchestrator_call.py`

**Interfaces:**
- Consumes: `ai_config.get_prompt`, `ai_config.get_agent_model`, `ai_config.get_temp`.
- Produces:
  - `def call_agent(agent_id: str, default_prompt: str, messages: list[dict], *, json_mode: bool = False) -> str` — monta `[{system: prompt do agente}, *messages]`, usa modelo/temp do agente, retorna o texto (ou string JSON se `json_mode`). Em `settings.ai_enabled = False`, retorna `""` (os call-sites tratam o mock).

- [ ] **Step 1: Write the failing test**

```python
# back/tests/test_orchestrator_call.py
from app.routers import orchestrator

def test_call_agent_uses_agent_prompt_and_model(monkeypatch):
    captured = {}
    class FakeResp:
        choices = [type("C", (), {"message": type("M", (), {"content": "oi"})()})()]
    class FakeClient:
        def __init__(self, **k): pass
        class chat:
            class completions:
                @staticmethod
                def create(**kw): captured.update(kw); return FakeResp()
    monkeypatch.setattr(orchestrator, "_client", lambda: FakeClient())
    monkeypatch.setattr(orchestrator.settings, "ai_enabled", True)
    monkeypatch.setattr(orchestrator.ai_config, "get_agent_model", lambda a: "gpt-test")
    monkeypatch.setattr(orchestrator.ai_config, "get_temp", lambda a, default=0.2: 0.0)
    monkeypatch.setattr(orchestrator.ai_config, "get_prompt", lambda a, d: "PROMPT-PLAN")
    out = orchestrator.call_agent("planejador", "def", [{"role": "user", "content": "x"}])
    assert out == "oi"
    assert captured["model"] == "gpt-test"
    assert captured["temperature"] == 0.0
    assert captured["messages"][0] == {"role": "system", "content": "PROMPT-PLAN"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd back && python -m pytest tests/test_orchestrator_call.py -v`
Expected: FAIL (`ModuleNotFoundError: app.routers.orchestrator`).

- [ ] **Step 3: Implement**

```python
# back/app/routers/orchestrator.py
"""Orquestrador determinístico dos agentes (Fase 2).

FSM por projeto (Project.phase) + roteador de intenção. Cada agente é uma chamada
de IA separada, com prompt/modelo/temperatura lidos do grafo do builder (ai_config).
"""
from __future__ import annotations

from ..config import settings
from ..services import ai_config


def _client():
    from openai import OpenAI
    return OpenAI(api_key=settings.openai_api_key)


def call_agent(agent_id: str, default_prompt: str, messages: list[dict], *, json_mode: bool = False) -> str:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd back && python -m pytest tests/test_orchestrator_call.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add back/app/routers/orchestrator.py back/tests/test_orchestrator_call.py
git commit -m "feat(orchestrator): call_agent generico (prompt/modelo/temp por agente)"
```

### Task 2.2: Roteador de intenção (Assistente fino)

**Files:**
- Modify: `back/app/routers/orchestrator.py`
- Test: `back/tests/test_orchestrator_router.py`

**Interfaces:**
- Consumes: `call_agent`, estado `Project.phase`, existência de stage `script`.
- Produces:
  - `ROUTER_PROMPT: str` — classifica a última mensagem do usuário em `nova | ajuste | duvida` (JSON `{"intent": "..."}`).
  - `def route_intent(last_user: str, has_workflow: bool) -> str` — devolve `"nova" | "ajuste" | "duvida"`. Heurística determinística primeiro (sem workflow + verbo de criação → `nova`; com workflow + verbo de edição → `ajuste`), IA só no caso ambíguo. Mantém `_is_build_intent` como sinal auxiliar.

- [ ] **Step 1: Write the failing test**

```python
# back/tests/test_orchestrator_router.py
from app.routers import orchestrator

def test_route_no_workflow_creation_is_nova(monkeypatch):
    monkeypatch.setattr(orchestrator.settings, "ai_enabled", False)
    assert orchestrator.route_intent("quero conciliar duas planilhas", has_workflow=False) == "nova"

def test_route_with_workflow_edit_is_ajuste(monkeypatch):
    monkeypatch.setattr(orchestrator.settings, "ai_enabled", False)
    assert orchestrator.route_intent("muda a coluna de data para dd/mm/aaaa", has_workflow=True) == "ajuste"

def test_route_question_is_duvida(monkeypatch):
    monkeypatch.setattr(orchestrator.settings, "ai_enabled", False)
    assert orchestrator.route_intent("o que essa automação faz?", has_workflow=True) == "duvida"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd back && python -m pytest tests/test_orchestrator_router.py -v`
Expected: FAIL (`AttributeError: route_intent`).

- [ ] **Step 3: Implement** — heurística determinística + fallback IA. Reusar `_BUILD_VERB`/`_is_build_intent` de `chat.py` (importar). Verbos de edição: `mud|alter|ajust|troc|corrig|renome|adicion|remov`. Padrão de pergunta: termina com `?` ou começa com `o que|como|porque|por que|qual|quando|quem`. Sem workflow → `nova` salvo se for pergunta. Com workflow → `ajuste` se verbo de edição, `duvida` se pergunta, senão IA (`call_agent("assistente", ROUTER_PROMPT, ..., json_mode=True)` lendo `intent`). Em `ai_enabled=False`, o ambíguo cai em `nova` se sem workflow, senão `ajuste`.

```python
import re

ROUTER_PROMPT = (
    "Você é a porta de entrada do FlowDesk. Classifique a intenção da última "
    'mensagem do usuário em JSON {"intent": "nova|ajuste|duvida"}: '
    "nova = criar uma automação nova; ajuste = mudar uma automação existente; "
    "duvida = pergunta ou conversa que não pede mudança. Responda só o JSON."
)
_EDIT_VERB = re.compile(r"\b(mud\w*|alter\w*|ajust\w*|troc\w*|corrig\w*|renome\w*|adicion\w*|remov\w*)\b", re.I)
_QUESTION = re.compile(r"\?\s*$|^\s*(o que|como|por ?que|qual|quando|quem)\b", re.I)


def route_intent(last_user: str, has_workflow: bool) -> str:
    c = (last_user or "").strip().lower()
    is_question = bool(_QUESTION.search(c))
    if not has_workflow:
        return "duvida" if is_question and not _is_build_intent(c) else "nova"
    if _EDIT_VERB.search(c):
        return "ajuste"
    if is_question:
        return "duvida"
    if not settings.ai_enabled:
        return "ajuste"
    import json
    raw = call_agent("assistente", ROUTER_PROMPT, [{"role": "user", "content": last_user}], json_mode=True)
    try:
        intent = (json.loads(raw or "{}").get("intent") or "").strip()
    except Exception:
        intent = ""
    return intent if intent in ("nova", "ajuste", "duvida") else "ajuste"
```

(Importar `_is_build_intent` de `.chat` no topo; evitar import circular movendo `_is_build_intent` para `orchestrator.py` se necessário — ver Task 5.1.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd back && python -m pytest tests/test_orchestrator_router.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add back/app/routers/orchestrator.py back/tests/test_orchestrator_router.py
git commit -m "feat(orchestrator): roteador de intencao nova/ajuste/duvida"
```

### Task 2.3: Transições de fase e selagem do plano

**Files:**
- Modify: `back/app/routers/orchestrator.py`
- Test: `back/tests/test_orchestrator_phase.py`

**Interfaces:**
- Consumes: `plan_schema.Plan`, `plan_schema.plan_is_complete`.
- Produces:
  - `def next_phase(current: str, intent: str, plan: Plan, user_confirmed: bool) -> str` — FSM pura. Regras:
    - intent `nova` → `planning`.
    - `planning` + plano completo + `user_confirmed` → `building`.
    - `building` (código gerado) → `naming`.
    - `naming` (nome gravado) → `done`.
    - intent `ajuste` → `building` (vai direto ao Construtor).
    - intent `duvida` → mantém `current`.

- [ ] **Step 1: Write the failing test**

```python
# back/tests/test_orchestrator_phase.py
from app.routers.orchestrator import next_phase
from app.services.plan_schema import Plan, PlanFonte, PlanSaida

FULL = Plan(fonte=PlanFonte(formato="xlsx"), regra_negocio="x", saida=PlanSaida(formato="xlsx"), gatilho="manual")

def test_nova_enters_planning():
    assert next_phase("", "nova", Plan(), False) == "planning"

def test_planning_seals_only_when_complete_and_confirmed():
    assert next_phase("planning", "nova", Plan(), True) == "planning"      # incompleto
    assert next_phase("planning", "nova", FULL, False) == "planning"        # não confirmado
    assert next_phase("planning", "nova", FULL, True) == "building"         # sela

def test_ajuste_goes_straight_to_building():
    assert next_phase("done", "ajuste", FULL, False) == "building"

def test_duvida_keeps_phase():
    assert next_phase("planning", "duvida", Plan(), False) == "planning"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd back && python -m pytest tests/test_orchestrator_phase.py -v`
Expected: FAIL (`ImportError: next_phase`).

- [ ] **Step 3: Implement**

```python
from ..services.plan_schema import Plan, plan_is_complete


def next_phase(current: str, intent: str, plan: Plan, user_confirmed: bool) -> str:
    if intent == "duvida":
        return current
    if intent == "ajuste":
        return "building"
    if intent == "nova" and current in ("", "done", "naming"):
        return "planning"
    if current == "planning":
        return "building" if (plan_is_complete(plan) and user_confirmed) else "planning"
    return current
```

(As transições `building -> naming -> done` são disparadas pelos call-sites do Construtor/Nomeador na Stage 3, não pelo roteamento de mensagem.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd back && python -m pytest tests/test_orchestrator_phase.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add back/app/routers/orchestrator.py back/tests/test_orchestrator_phase.py
git commit -m "feat(orchestrator): FSM de fases e selagem do plano"
```

**Gate da Stage 2:** suite `tests/test_orchestrator_*.py` verde + commit. O CONTRATO para a Stage 3 é: `call_agent(agent_id, default_prompt, messages, json_mode=)`, `route_intent`, `next_phase`, e o schema `Plan`/`AccountingProfile`. Liberar 3a–3e e 4 em paralelo.

---

## Stage 3 — Agentes especializados (PARALELO; cada um é um subagente; todos esperam Stage 2)

Cada etapa abaixo toca arquivos/funções distintos e pode ser feita por um subagente independente. O contrato comum é o da Stage 2. Onde a tarefa toca o front, o subagente DEVE ler o arquivo alvo antes de editar.

### Stage 3a — Planejador (entrevista que preenche o plano)

**Files:**
- Modify: `back/app/routers/orchestrator.py` (add `run_planejador`)
- Test: `back/tests/test_planejador.py`

**Interfaces:**
- Consumes: `call_agent`, `Plan`, `AccountingProfile`, `plan_missing_fields`.
- Produces:
  - `PLANEJADOR_PROMPT` — a partir do prompt-semente `_PLANEJADOR_PROMPT` (ai.py:36), instruído a devolver JSON `{"questions": [...], "plan": {...parcial...}, "contabil": bool, "perfil_perguntas": [...]}`: continua a entrevista (uma pergunta por vez via `questions`) E devolve o `plan` parcial preenchido até aqui. Quando `contabil=true`, inclui perguntas de regime/plano de contas/ERP destino em `perfil_perguntas`.
  - `def run_planejador(messages: list[dict], plan: dict) -> dict` — retorna `{"questions": [...], "plan": {...mesclado...}, "missing": [...], "profile_updates": {...}}`. Mescla o `plan` devolvido sobre o atual; calcula `missing = plan_missing_fields`.

- [ ] **Step 1: Write the failing test** (com `call_agent` mockado devolvendo JSON fixo)

```python
# back/tests/test_planejador.py
import json
from app.routers import orchestrator

def test_planejador_merges_plan_and_reports_missing(monkeypatch):
    fake = json.dumps({"questions": [{"id": "saida", "label": "Qual o formato de saída?",
                       "options": ["Excel", "CSV"], "recommended": "Excel"}],
                       "plan": {"fonte": {"formato": "xlsx"}, "regra_negocio": "somar por cliente"},
                       "contabil": False})
    monkeypatch.setattr(orchestrator, "call_agent", lambda *a, **k: fake)
    out = orchestrator.run_planejador([{"role": "user", "content": "somar planilha"}], {})
    assert out["plan"]["fonte"]["formato"] == "xlsx"
    assert "saida.formato" in out["missing"] and "gatilho" in out["missing"]
    assert out["questions"][0]["id"] == "saida"
```

- [ ] **Step 2-4:** rodar (falha por `AttributeError: run_planejador`), implementar mesclando dicts (deep-merge raso suficiente para o schema), parsear com `Plan(**merged)` para validar e recomputar `missing`, devolver. PASS.

- [ ] **Step 5: Commit**

```bash
git add back/app/routers/orchestrator.py back/tests/test_planejador.py
git commit -m "feat(orchestrator): Planejador preenche o plano e reporta campos faltando"
```

### Stage 3b — Construtor (lê o plano, não a transcrição)

**Files:**
- Modify: `back/app/routers/orchestrator.py` (add `run_construtor`)
- Modify: `back/app/routers/chat.py` (`_generate_build` passa a receber o plano)
- Test: `back/tests/test_construtor.py`

**Interfaces:**
- Consumes: `call_agent` (json_mode), `Plan` selado, `AccountingProfile` (quando `plan.contabil`).
- Produces:
  - `CONSTRUTOR_PROMPT` — base `_CONSTRUTOR_PROMPT` (ai.py:55) + regras de código do `SYSTEM_PROMPT`. Recebe o PLANO em JSON como contexto primário (não a transcrição) + perfil contábil quando aplicável.
  - `def run_construtor(plan: dict, profile: dict, project_context: str) -> dict` — retorna `{"message": str, "actions": [...]}` (mesmo formato de actions que `_apply_action` consome). Garante ao menos um `create_file` com script completo.

- [ ] **Step 1: Write the failing test** (mock `call_agent` devolvendo JSON com `actions`)

```python
# back/tests/test_construtor.py
import json
from app.routers import orchestrator

def test_construtor_consumes_plan_and_returns_actions(monkeypatch):
    captured = {}
    def fake_call(agent_id, default, messages, **k):
        captured["agent"] = agent_id
        captured["sees_plan"] = any("regra_negocio" in m["content"] for m in messages)
        return json.dumps({"message": "feito", "actions": [
            {"kind": "create_file", "title": "x", "path": "p.py", "content": "set_output({})"}]})
    monkeypatch.setattr(orchestrator, "call_agent", fake_call)
    out = orchestrator.run_construtor(
        {"regra_negocio": "somar por cliente", "saida": {"formato": "xlsx"}}, {}, "ctx")
    assert captured["agent"] == "construtor"
    assert captured["sees_plan"] is True
    assert out["actions"][0]["kind"] == "create_file"
```

- [ ] **Step 2-4:** falha, implementar (serializa o plano em JSON dentro de uma mensagem `user`/`system`; chama `call_agent("construtor", CONSTRUTOR_PROMPT, ..., json_mode=True)`; parseia `message`/`actions`). PASS.

- [ ] **Step 5: Commit**

```bash
git add back/app/routers/orchestrator.py back/app/routers/chat.py back/tests/test_construtor.py
git commit -m "feat(orchestrator): Construtor le o plano selado (nao a transcricao)"
```

### Stage 3c — Nomeador (chamada separada após o Construtor)

**Files:**
- Modify: `back/app/routers/orchestrator.py` (add `run_nomeador`)
- Modify: `back/app/routers/projects.py` (`auto_name` delega) e `back/app/routers/wizard.py` (`_describe_automation` delega)
- Test: `back/tests/test_nomeador.py`

**Interfaces:**
- Consumes: `call_agent` (json_mode), plano + código gerado.
- Produces:
  - `NOMEADOR_PROMPT` — base `_NOMEADOR_PROMPT` (ai.py:68). Devolve JSON `{"name": str, "description": str}`.
  - `def run_nomeador(plan: dict, code: str) -> dict` — `{"name": str, "description": str}`.
  - `def apply_name(db, project_id, name, description) -> None` — grava no Project SÓ se nome/descrição forem placeholder (`description == "Criado pelo Chat"` ou nome vazio/igual ao prompt cru); nunca sobrescreve nome definido pelo usuário.

- [ ] **Step 1: Write the failing test**

```python
# back/tests/test_nomeador.py
import json
from app.routers import orchestrator

def test_nomeador_returns_name_and_description(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_agent",
        lambda *a, **k: json.dumps({"name": "Conciliação de Razão", "description": "Concilia o razão."}))
    out = orchestrator.run_nomeador({"regra_negocio": "conciliar"}, "code")
    assert out["name"] == "Conciliação de Razão"
    assert out["description"].startswith("Concilia")
```

- [ ] **Step 2-5:** falha, implementar, PASS, commit. `apply_name` testar separado (não sobrescreve nome do usuário) com DB em memória se houver fixture; senão teste unitário da regra de guarda.

```bash
git add back/app/routers/orchestrator.py back/app/routers/projects.py back/app/routers/wizard.py back/tests/test_nomeador.py
git commit -m "feat(orchestrator): Nomeador como chamada separada, grava nome/descricao"
```

### Stage 3d — Classificador (cérebro contábil: design + runtime)

**Files:**
- Modify: `back/app/routers/orchestrator.py` (add `enrich_accounting`)
- Modify: `back/app/routers/classify.py` (`classificar_grupos` lê `accounting_profile`)
- Test: `back/tests/test_classificador_design.py`, `back/tests/test_classify_uses_profile.py`

**Interfaces:**
- Consumes: `call_agent`, `AccountingProfile`, `Plan`.
- Produces:
  - `CLASSIFICADOR_PROMPT` — base `_CLASSIFICADOR_PROMPT` (ai.py:76), ampliado para cérebro contábil de design: dado o plano + perfil, devolve `{"plan_patch": {...}, "perfil_updates": {...}, "avisos_fiscais": [...]}` enriquecendo o contrato de saída com regras contábeis/fiscais (ex.: layout do Domínio).
  - `def enrich_accounting(plan: dict, profile: dict) -> dict` — só roda quando `plan.contabil`; mescla `plan_patch` no plano e `perfil_updates` no perfil (sem confirmar regime sozinho: campos sensíveis vão para confirmação, não direto).
  - `classify.py`: `classificar_grupos` usa `project.accounting_profile["plano_de_contas"]` como fonte de contas quando o request não trouxer contas, mantendo o comportamento atual como fallback.

- [ ] **Step 1: Write the failing test** (design)

```python
# back/tests/test_classificador_design.py
import json
from app.routers import orchestrator

def test_enrich_only_when_contabil(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_agent", lambda *a, **k: json.dumps(
        {"plan_patch": {"saida": {"contrato": "layout Domínio: Inicia Lote reinicia por data"}},
         "perfil_updates": {}, "avisos_fiscais": ["Confirmar regime antes de gerar guia"]}))
    out = orchestrator.enrich_accounting({"contabil": True, "saida": {}}, {})
    assert "Domínio" in out["plan"]["saida"]["contrato"]
    # não-contábil não chama IA nem altera o plano
    same = orchestrator.enrich_accounting({"contabil": False}, {})
    assert same["plan"] == {"contabil": False}
```

- [ ] **Step 2-5:** falha, implementar `enrich_accounting` + ajuste em `classify.py` (com teste `test_classify_uses_profile.py` validando que, sem `contas` no request, usa `plano_de_contas` do perfil). PASS, commit.

```bash
git add back/app/routers/orchestrator.py back/app/routers/classify.py back/tests/test_classificador_design.py back/tests/test_classify_uses_profile.py
git commit -m "feat(orchestrator): cerebro contabil enriquece plano (design) + runtime le perfil"
```

### Stage 3e — Reparador (recebe plano + perfil)

**Files:**
- Modify: `back/app/routers/repair.py:87-93` (montagem das `messages`)
- Test: `back/tests/test_repair_context.py`

**Interfaces:**
- Consumes: `Project.plan`, `Project.accounting_profile`.
- Produces: `repair_propose` injeta, antes do `user_msg`, um bloco system com o plano selado e o perfil contábil (quando existir), para a correção respeitar o contrato. Mantém o `_REPAIR_INSTR` e o loop propõe/aplica intactos.

- [ ] **Step 1: Write the failing test** — chamar `repair_propose` com `ai_enabled` mockado e capturar as `messages` passadas ao client; asseverar que o conteúdo do plano aparece quando `project.plan` está preenchido.

- [ ] **Step 2-5:** falha, implementar (ler `project.plan`/`accounting_profile` via `get_project`; se não vazios, `messages.insert(1, {"role": "system", "content": "PLANO SELADO:\n" + json.dumps(...) })`). PASS, commit.

```bash
git add back/app/routers/repair.py back/tests/test_repair_context.py
git commit -m "feat(orchestrator): Reparador recebe plano selado + perfil contabil"
```

---

## Stage 4 — Frontend: selos de fase + plano consolidado + modelo por agente (PARALELO; espera Stage 2)

O subagente DEVE ler `SmartChat.tsx` e `Agents.tsx` inteiros antes de editar (não há diff completo aqui porque dependem de estrutura JSX existente).

### Task 4.1: Selos de fase e plano consolidado no chat

**Files:**
- Modify: `front/src/components/SmartChat.tsx`
- Test: `front/src/components/SmartChat.test.tsx` (Vitest) — criar se não existir.

**Interfaces:**
- Consumes: o evento `done` do stream passa a incluir `phase` e, quando `phase` muda para `building`, um `plan` consolidado (objeto). O backend (Stage 5) adiciona esses campos ao payload `done`.
- Produces: um selo discreto acima da última mensagem do assistente mostrando a fase atual (`Planejando` / `Construindo` / `Nomeando`), e, quando o backend envia o plano consolidado para confirmação, um card "Confira o plano" com os campos do plano e botões Confirmar/Ajustar (reusa o padrão de `questions`/approve já existente em `SmartChat.tsx:193`).

- [ ] **Steps:** teste de render (Vitest) verificando que, dado `meta.phase = "building"`, aparece o selo "Construindo"; dado `meta.plan`, aparece o card do plano. Implementar o componente de selo + card. Commit.

```bash
git add front/src/components/SmartChat.tsx front/src/components/SmartChat.test.tsx
git commit -m "feat(chat): selos de fase e card de plano consolidado"
```

### Task 4.2: Seletor de modelo por agente no board

**Files:**
- Modify: `front/src/pages/Agents.tsx`
- Test: `front/src/pages/Agents.test.tsx` (já existe — estender)

**Interfaces:**
- Consumes: `model_catalog` já retornado por `GET /api/ai/agents` (ai.py:189) e o campo `model` por agente no grafo.
- Produces: cada nó do board ganha um `<select>` de modelo (opções de `model_catalog`); ao salvar (`PUT /api/ai/graph`), o `model` por agente é persistido. Default visual = modelo compartilhado quando o nó não tem override.

- [ ] **Steps:** estender `Agents.test.tsx` para asseverar que o select por agente aparece e que o valor escolhido entra no payload do `PUT /graph`. Implementar. Commit.

```bash
git add front/src/pages/Agents.tsx front/src/pages/Agents.test.tsx
git commit -m "feat(agents): seletor de modelo por agente no board"
```

---

## Stage 5 — Integração, reset do seed e E2E (SEQUENCIAL; só inicia com 3a–3e e 4 fechados)

### Task 5.1: Ligar o orquestrador ao chat_stream

**Files:**
- Modify: `back/app/routers/chat.py` (`chat_stream`, `event_stream`)
- Test: `back/tests/test_chat_orchestrated.py`

**Interfaces:**
- Substitui o gatilho único `_is_build_intent` por: `intent = route_intent(...)`; carrega `project.phase`/`plan`/`accounting_profile`; aplica `next_phase`; despacha para `run_planejador` / `run_construtor` (+ `enrich_accounting` quando contábil) / `run_nomeador`; grava `phase`/`plan`/`accounting_profile`; emite no `done` os campos `phase` e (na confirmação) `plan`. Se `phase == ""` e intent `duvida`, mantém o caminho de chat atual (`_generate`).
- Resolver import circular: mover `_is_build_intent`, `_BUILD_VERB`, `_INTEGRATION_INTENT`, `_is_pathlike_env` para `orchestrator.py` e reimportar em `chat.py` (ou deixar em `chat.py` e o orquestrador importar tardiamente dentro da função).

- [ ] **Steps:** teste de integração com IA mockada cobrindo o caminho feliz: mensagem "nova" → `phase=planning` + questions; "Respostas da entrevista..." com plano completo + confirmação → `phase=building` + actions; após aprovar → Nomeador grava nome. Implementar a fiação. Rodar a suite inteira do back. Commit.

```bash
git add back/app/routers/chat.py back/app/routers/orchestrator.py back/tests/test_chat_orchestrated.py
git commit -m "feat(orchestrator): chat_stream delega ao pipeline determinístico"
```

### Task 5.2: applied.orchestration = True e reset do grafo-semente

**Files:**
- Modify: `back/app/routers/ai.py:194` (`applied`), `back/app/routers/ai.py:131-138` (`_COLORS`: trocar `descritor` por `planejador`)
- Test: `back/tests/test_ai_applied.py`

**Interfaces:**
- `applied` passa a `{"assistant_prompt": True, "shared_model": True, "orchestration": True}`.
- Garantir que `_default_graph` reflete modelo por agente (campo `model` já existe; manter o compartilhado como default por nó).
- Operação de reset do grafo salvo "Descritor": documentar que o admin clica em "Restaurar seed" (`DELETE /api/ai/graph`) OU rodar uma vez `ai_config.clear_graph()`. Não migrar automaticamente (decisão de admin).

- [ ] **Steps:** teste asseverando `applied["orchestration"] is True` e que `_default_graph()` não contém id `descritor`. Implementar. Commit.

```bash
git add back/app/routers/ai.py back/tests/test_ai_applied.py
git commit -m "feat(agents): orchestration aplicada de verdade + seed sem Descritor"
```

### Task 5.3: Verificação E2E manual

- [ ] Subir back + front. Criar projeto novo via Chat: "quero conciliar duas planilhas de razão".
- [ ] Conferir: selo "Planejando", entrevista uma pergunta por vez, perguntas contábeis quando o tema é contábil.
- [ ] Completar o plano → card "Confira o plano" → Confirmar → selo "Construindo" → código gerado → card nomeado no Console.
- [ ] Forçar um erro de execução → Reparador propõe correção coerente com o plano.
- [ ] No board, trocar o modelo do Construtor, salvar, refazer um build e confirmar que o modelo escolhido foi usado (log/consumo de IA).
- [ ] Rodar `cd back && python -m pytest -q` (tudo verde) e o teste do front (`cd front && npm test`).

---

## Self-Review (executado contra as decisões do grill)

- **Escopo orquestração total:** Stages 2+3 fazem cada agente uma chamada separada (`call_agent`). ✔
- **Pipeline determinístico:** `next_phase` (FSM) + `route_intent`, sem LLM-router no caminho feliz. ✔
- **Assistente fino:** `route_intent` classifica e roteia, não entrevista. ✔
- **Plano JSON com schema:** `plan_schema.Plan` + `plan_missing_fields`. ✔
- **Selagem com schema completo + confirmação:** `next_phase("planning", ..., plan, user_confirmed)`. ✔
- **Classificador design + runtime, perfil único:** `enrich_accounting` (design) + `classificar_grupos` lendo `accounting_profile` (runtime). ✔
- **Perfil por projeto:** coluna `Project.accounting_profile`. ✔
- **Nomeador após Construtor, respeita nome do usuário:** `run_nomeador` + `apply_name` com guarda. ✔
- **Reparador + plano:** Stage 3e. ✔
- **Modelo por agente do grafo:** `get_agent_model` + Task 4.2. ✔
- **Router 3 destinos:** `route_intent` → nova/ajuste/duvida; ajuste vai a `building`. ✔
- **Bootstrap perfil na entrevista, confirmação de campos sensíveis:** Planejador `perfil_perguntas` + `enrich_accounting` não confirma regime sozinho. ✔
- **UX voz única + selos + plano consolidado:** Task 4.1. ✔

**Gap consciente:** o nível "perfil por organização/cliente" foi adiado (decisão: por projeto agora). Quando "cliente" for modelado, herdar o perfil é uma evolução, não um requisito desta entrega.
