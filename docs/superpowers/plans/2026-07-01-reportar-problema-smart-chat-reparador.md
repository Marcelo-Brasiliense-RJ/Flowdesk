# Reportar problema no Smart Chat com o reparador — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um botão "Reportar problema" na tela de resultado (Wizard e app publicado, só dono logado) que fixa a execução no Smart Chat; o dono descreve o que ficou errado e o reparador propõe a correção do script como ação aprovável, valendo para erro e para "falso sucesso".

**Architecture:** Reaproveita o reparador existente (`repair.py`) e o mecanismo de `PendingAction` + aprovação do chat. Dois endpoints novos em `repair.py` (não em `chat.py`, para evitar import circular, já que `repair.py` importa de `chat.py`): um fixa a execução como mensagem de chat, outro roda o reparador a partir da execução + descrição do usuário e cria a ação de correção. No frontend, o botão leva a `/projects/:id/chat?report=<execution_id>`; o `SmartChat` entra em "modo reporte", renderiza o card da execução e roteia o próximo envio ao endpoint de reparo.

**Tech Stack:** Backend FastAPI + SQLAlchemy (Python 3.11), pytest. Frontend React + TypeScript + Vite, vitest.

## Global Constraints

- Copy em português, sem travessão em dash (—); usar vírgula. Sem emojis em texto novo de produto.
- Backend: autenticação via `Depends(get_current_user)` + `get_project(db, project_id, user)` para validar posse; nunca confiar em ids sem checar `project_id`.
- Persistência de coluna JSON (`Stage.config`, `ChatMessage.meta`, `PendingAction.payload`): reatribuir um dict novo ao atributo (o codebase não usa `MutableDict`).
- Reparador só edita o script Python da automação; problemas de plataforma/renderização não são escopo. A UI deve deixar isso claro.
- Reusar, não duplicar: o núcleo do reparador vira uma função única usada pelo endpoint atual e pelos novos.
- Rodar testes do backend com `cwd=back`, `PYTHONPATH=$(pwd)`, interpretador `.venv/Scripts/python.exe`. Frontend com `npx vitest run` em `front`.

---

## File Structure

- `back/app/routers/repair.py` — Modificar. Extrai `run_repair(...)`; adiciona `output_data` ao contexto; adiciona endpoints `chat/report` e `chat/report-repair`.
- `back/app/schemas.py` — Modificar. Novos schemas `ReportSeedIn`, `ReportRepairIn`.
- `back/tests/test_repair_report.py` — Criar. Testes dos dois endpoints e do contexto com output.
- `front/src/pages/Wizard.tsx` — Modificar. Guarda `execution_id`; botão "Reportar problema" na tela de resultado do teste; navega para `/projects/:id/chat?report=<id>`.
- `front/src/pages/PublishedApp.tsx` — Modificar. Guarda `execution_id`; botão só quando há sessão do app principal (`getToken()`); deep-link para o chat.
- `front/src/components/SmartChat.tsx` — Modificar. Lê `?report=`, chama `chat/report`, renderiza o card `execution_report`, roteia envio em modo reporte para `chat/report-repair`.
- `front/src/pages/reportCard.tsx` — Criar. Componente puro `ReportCard` que renderiza `meta.execution_report`.
- `front/src/test/reportCard.test.tsx` — Criar. Testa render do card (sucesso e erro).

---

## Task 1: Núcleo do reparador reutilizável, com o resultado no contexto

**Files:**
- Modify: `back/app/routers/repair.py`
- Test: `back/tests/test_repair_report.py`

**Interfaces:**
- Produces: `run_repair(db, project, stage, execution_id: str, hint: str | None) -> RepairProposeOut` e `_execution_context(execu) -> str` (bloco de texto com stderr + resumo do output). `repair_propose` passa a chamar `run_repair`.

- [ ] **Step 1: Escrever o teste falhando (contexto inclui o output)**

Criar `back/tests/test_repair_report.py`:

```python
from app.routers.repair import _execution_context


class _Exec:
    def __init__(self, stderr="", output_data=None):
        self.stderr = stderr
        self.output_data = output_data or {}


def test_contexto_inclui_stderr_e_resumo_do_output():
    ex = _Exec(stderr="Traceback: KeyError 'Valor'",
               output_data={"resumo": "10 casados, 3 nao casados", "arquivo_resultado": "x.xlsx"})
    ctx = _execution_context(ex)
    assert "KeyError 'Valor'" in ctx
    assert "10 casados, 3 nao casados" in ctx


def test_contexto_em_falso_sucesso_sem_stderr():
    # rodou sem erro, mas o resultado esta errado: o contexto ainda traz o output
    ex = _Exec(stderr="", output_data={"resumo": "0 casados"})
    ctx = _execution_context(ex)
    assert "0 casados" in ctx
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `PYTHONPATH="$(pwd)" .venv/Scripts/python.exe -m pytest tests/test_repair_report.py::test_contexto_inclui_stderr_e_resumo_do_output -v`
Expected: FAIL com `ImportError`/`AttributeError` (`_execution_context` não existe).

- [ ] **Step 3: Implementar `_execution_context` e `run_repair`**

Em `back/app/routers/repair.py`, adicionar helper e extrair o núcleo. `_execution_context` monta um bloco textual truncado com stderr e um resumo do `output_data`:

```python
def _execution_context(execu) -> str:
    """Bloco com o ERRO (stderr) e o RESULTADO (output_data) da execucao. Em falso
    sucesso nao ha stderr, entao o resultado e o unico sinal do que ficou errado."""
    parts = []
    stderr = (getattr(execu, "stderr", "") or "").strip()
    if stderr:
        parts.append("ERRO (stderr):\n" + stderr[:3000])
    output = getattr(execu, "output_data", None) or {}
    if output:
        resumo = output.get("resumo")
        if isinstance(resumo, str) and resumo.strip():
            parts.append("RESUMO DO RESULTADO:\n" + resumo[:1500])
        outras = {k: v for k, v in output.items() if k not in ("resumo",) and not str(k).startswith("_")}
        if outras:
            parts.append("SAIDA (chaves):\n" + json.dumps(outras, ensure_ascii=False, default=str)[:1500])
    return "\n\n".join(parts)


def run_repair(db: Session, project, stage: Stage, execution_id: str, hint: str | None) -> RepairProposeOut:
    """Nucleo do reparador: monta o contexto (codigo + execucao + plano + anexos),
    chama a IA e devolve a proposta. Reusado pelo endpoint /repair/propose e pelo
    fluxo de reporte no chat."""
    row = _stage_source(db, project.id, stage)
    code = row.content if row else ""

    execu = db.get(Execution, execution_id)
    if execu is not None and execu.project_id != project.id:
        execu = None
    exec_ctx = _execution_context(execu) if execu is not None else ""
    input_data = (execu.input_data if execu else {}) or {}

    paths = [v for v in input_data.values() if isinstance(v, str) and v]
    ctx = _attachment_context(project.id, paths) if paths else ""

    messages = [{"role": "system", "content": _REPAIR_INSTR}]
    if ctx:
        messages.append({"role": "system", "content": ctx})
    pp_ctx = _plan_profile_context(project.plan, project.accounting_profile)
    if pp_ctx:
        messages.append({"role": "system", "content": pp_ctx})
    user_msg = f"CODIGO ATUAL:\n\n{code[:6000]}\n\n{exec_ctx}"
    if hint and hint.strip():
        user_msg += f"\n\nO QUE O USUARIO DIZ QUE ESTA ERRADO: {hint.strip()}"
    messages.append({"role": "user", "content": user_msg})

    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model=ai_config.get_model(),
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    data = json.loads(resp.choices[0].message.content or "{}")
    fixed = (data.get("fixed_code") or "").strip()
    return RepairProposeOut(
        diagnosis=(data.get("diagnosis") or "").strip(),
        change_summary=(data.get("change_summary") or "").strip(),
        fixed_code=fixed,
        has_changes=bool(fixed) and fixed != (code or "").strip(),
    )
```

Refatorar `repair_propose` para reusar (mantém o contrato HTTP e o tratamento de erro atual):

```python
    if not settings.ai_enabled:
        raise HTTPException(status_code=400, detail="IA indisponível para reparo.")
    stage = _script_stage(db, project_id, stage_id)
    try:
        return run_repair(db, project, stage, body.execution_id, body.hint)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Falha ao consultar a IA: {exc}")
```

- [ ] **Step 4: Rodar os testes e ver passar**

Run: `PYTHONPATH="$(pwd)" .venv/Scripts/python.exe -m pytest tests/test_repair_report.py -v`
Expected: PASS nos dois testes de contexto.

- [ ] **Step 5: Rodar a suíte de reparo existente para não regredir**

Run: `PYTHONPATH="$(pwd)" .venv/Scripts/python.exe -m pytest tests/ -k repair -q`
Expected: PASS (nenhuma regressão no `repair_propose`).

- [ ] **Step 6: Commit**

```bash
git add back/app/routers/repair.py back/tests/test_repair_report.py
git commit -m "refactor(repair): nucleo run_repair reutilizavel + resultado no contexto"
```

---

## Task 2: Endpoint que fixa a execução no chat (`chat/report`)

**Files:**
- Modify: `back/app/routers/repair.py`, `back/app/schemas.py`
- Test: `back/tests/test_repair_report.py`

**Interfaces:**
- Consumes: `Execution`, `ChatMessage` (de `..models`), `get_project`.
- Produces: `POST /api/projects/{project_id}/chat/report` body `{execution_id}` → cria `ChatMessage` role=assistant com `meta.execution_report` e retorna `ChatMessageOut`. Helper `_execution_report_snapshot(execu) -> dict`.

- [ ] **Step 1: Adicionar schema**

Em `back/app/schemas.py`, após `RepairApplyIn`:

```python
class ReportSeedIn(BaseModel):
    execution_id: str


class ReportRepairIn(BaseModel):
    execution_id: str
    message: str
```

- [ ] **Step 2: Escrever o teste do snapshot**

Em `back/tests/test_repair_report.py`, adicionar:

```python
from app.routers.repair import _execution_report_snapshot


def test_snapshot_do_reporte():
    class E:
        id = "abc"
        status = "success"
        stderr = ""
        output_data = {"resumo": "10 casados", "arquivo_resultado": "r.xlsx", "_oculto": 1}
        input_data = {"arquivo1": "uploads/extrato.xlsx", "arquivo2": "uploads/razao.xlsx"}
    snap = _execution_report_snapshot(E())
    assert snap["execution_id"] == "abc"
    assert snap["status"] == "success"
    assert snap["resumo"] == "10 casados"
    assert snap["input_files"] == ["extrato.xlsx", "razao.xlsx"]
    assert "_oculto" not in snap["output_keys"]
```

- [ ] **Step 3: Rodar o teste e ver falhar**

Run: `PYTHONPATH="$(pwd)" .venv/Scripts/python.exe -m pytest tests/test_repair_report.py::test_snapshot_do_reporte -v`
Expected: FAIL (`_execution_report_snapshot` não existe).

- [ ] **Step 4: Implementar snapshot + endpoint**

Em `back/app/routers/repair.py` (adicionar import `from ..models import ChatMessage` na linha de imports de models e `from ..schemas import ReportSeedIn, ReportRepairIn`):

```python
def _execution_report_snapshot(execu) -> dict:
    """Resumo da execucao para fixar no chat (card). So nomes de arquivo, sem caminhos."""
    output = (getattr(execu, "output_data", None) or {})
    stderr = (getattr(execu, "stderr", "") or "").strip()
    input_data = (getattr(execu, "input_data", None) or {})
    files = [v.split("/")[-1] for v in input_data.values() if isinstance(v, str) and "/" in v]
    return {
        "execution_id": execu.id,
        "status": execu.status,
        "resumo": output.get("resumo") if isinstance(output.get("resumo"), str) else None,
        "output_keys": [k for k in output.keys() if not str(k).startswith("_")],
        "stderr_excerpt": stderr[:600] or None,
        "input_files": files,
    }


@router.post("/projects/{project_id}/chat/report", response_model=ChatMessageOut)
def chat_report(
    project_id: int,
    body: ReportSeedIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project(db, project_id, user)
    execu = db.get(Execution, body.execution_id)
    if execu is None or execu.project_id != project_id:
        raise HTTPException(status_code=404, detail="Execução não encontrada")
    msg = ChatMessage(
        project_id=project_id,
        role="assistant",
        content="Vi o resultado desta execução. Me diga o que ficou errado que eu ajusto a automação.",
        meta={"execution_report": _execution_report_snapshot(execu)},
        tokens=0,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg
```

Adicionar `ChatMessageOut` ao import de schemas no topo do arquivo.

- [ ] **Step 5: Rodar o teste e ver passar**

Run: `PYTHONPATH="$(pwd)" .venv/Scripts/python.exe -m pytest tests/test_repair_report.py::test_snapshot_do_reporte -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add back/app/routers/repair.py back/app/schemas.py back/tests/test_repair_report.py
git commit -m "feat(repair): endpoint chat/report fixa a execucao como mensagem"
```

---

## Task 3: Endpoint de reparo a partir do reporte (`chat/report-repair`)

**Files:**
- Modify: `back/app/routers/repair.py`
- Test: `back/tests/test_repair_report.py`

**Interfaces:**
- Consumes: `run_repair` (Task 1), `PendingAction` (de `..models`), `_script_stage`.
- Produces: `POST /api/projects/{project_id}/chat/report-repair` body `{execution_id, message}` → persiste msg do usuário, roda `run_repair`, persiste msg do assistente (diagnóstico + resumo) e cria `PendingAction` kind=`edit_file` quando `has_changes`. Retorna `{message: ChatMessageOut, action: PendingActionOut | None}`.

- [ ] **Step 1: Escrever o teste (cria ação edit_file quando há correção)**

Em `back/tests/test_repair_report.py`, com monkeypatch do `run_repair` (evita chamar IA):

```python
import app.routers.repair as repair_mod
from app.schemas import RepairProposeOut


def test_report_repair_cria_acao_edit_file(monkeypatch):
    from tests.helpers import make_project_with_script, client_for  # ver Step nota
    ctx = make_project_with_script(code="from flowdesk_sdk import get_file, set_output\n")
    monkeypatch.setattr(repair_mod, "run_repair", lambda *a, **k: RepairProposeOut(
        diagnosis="Entendi o problema.", change_summary="Vou ajustar a leitura.",
        fixed_code="from flowdesk_sdk import get_file, set_output\n# corrigido\n", has_changes=True))
    r = ctx.client.post(
        f"/api/projects/{ctx.project_id}/chat/report-repair",
        json={"execution_id": ctx.execution_id, "message": "o resumo veio errado"},
        headers=ctx.auth,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["action"]["kind"] == "edit_file"
    assert data["action"]["payload"]["path"] == ctx.script_path
```

Nota: se `tests/helpers.py` com `make_project_with_script`/`client_for` não existir, criar um fixture mínimo no próprio arquivo de teste que: cria usuário+projeto+stage script+SourceFile+Execution via `SessionLocal`, e um `TestClient(app)` com header de auth. Reusar o padrão de setup já presente em outros testes de router (procurar `TestClient` em `back/tests/`).

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `PYTHONPATH="$(pwd)" .venv/Scripts/python.exe -m pytest tests/test_repair_report.py::test_report_repair_cria_acao_edit_file -v`
Expected: FAIL (rota 404, endpoint não existe).

- [ ] **Step 3: Implementar o endpoint**

Em `back/app/routers/repair.py` (import `from ..models import PendingAction`, `from ..schemas import PendingActionOut`):

```python
@router.post("/projects/{project_id}/chat/report-repair")
def chat_report_repair(
    project_id: int,
    body: ReportRepairIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project(db, project_id, user)
    if not settings.ai_enabled:
        raise HTTPException(status_code=400, detail="IA indisponível para reparo.")
    execu = db.get(Execution, body.execution_id)
    if execu is None or execu.project_id != project_id:
        raise HTTPException(status_code=404, detail="Execução não encontrada")
    stage = _script_stage(db, project_id, execu.stage_id)

    db.add(ChatMessage(project_id=project_id, role="user",
                       content=body.message, meta={"execution_id": body.execution_id}, tokens=0))
    try:
        proposal = run_repair(db, project, stage, body.execution_id, body.message)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Falha ao consultar a IA: {exc}")

    texto = proposal.diagnosis
    if proposal.change_summary:
        texto = (texto + "\n\n" + proposal.change_summary).strip()
    if not proposal.has_changes:
        texto = (texto or "Não encontrei uma correção automática.") + (
            "\n\nSe puder, detalhe melhor o que ficou errado no resultado."
        )
    assistant = ChatMessage(project_id=project_id, role="assistant", content=texto, meta={}, tokens=0)
    db.add(assistant)

    action = None
    if proposal.has_changes:
        action = PendingAction(
            project_id=project_id,
            kind="edit_file",
            title="Correção da automação",
            payload={"path": stage.entry_file, "content": proposal.fixed_code},
        )
        db.add(action)
    db.commit()
    db.refresh(assistant)
    out_action = None
    if action is not None:
        db.refresh(action)
        out_action = PendingActionOut.model_validate(action).model_dump(mode="json")
    return {
        "message": ChatMessageOut.model_validate(assistant).model_dump(mode="json"),
        "action": out_action,
    }
```

Aprovar a ação reusa `approve_action` (chat.py), que aplica o `edit_file` e re-sincroniza os campos de arquivo do Form.

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `PYTHONPATH="$(pwd)" .venv/Scripts/python.exe -m pytest tests/test_repair_report.py -v`
Expected: PASS.

- [ ] **Step 5: Suíte backend completa (menos falha ambiental conhecida)**

Run: `PYTHONPATH="$(pwd)" .venv/Scripts/python.exe -m pytest -q --deselect tests/test_seed_heal.py::test_heal_restaura_script_defasado`
Expected: PASS (0 falhas fora a deselecionada).

- [ ] **Step 6: Commit**

```bash
git add back/app/routers/repair.py back/tests/test_repair_report.py
git commit -m "feat(repair): endpoint chat/report-repair roda o reparador e cria acao de correcao"
```

---

## Task 4: Card do reporte (componente puro) no frontend

**Files:**
- Create: `front/src/pages/reportCard.tsx`
- Test: `front/src/test/reportCard.test.tsx`

**Interfaces:**
- Produces: `type ExecutionReport = { execution_id: string; status: string; resumo: string | null; output_keys: string[]; stderr_excerpt: string | null; input_files: string[] }` e `function ReportCard({ report }: { report: ExecutionReport })`.

- [ ] **Step 1: Escrever o teste do card**

Criar `front/src/test/reportCard.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReportCard } from "../pages/reportCard";

describe("ReportCard", () => {
  it("mostra status e arquivos em sucesso", () => {
    render(<ReportCard report={{ execution_id: "x", status: "success", resumo: "10 casados",
      output_keys: ["resumo"], stderr_excerpt: null, input_files: ["extrato.xlsx", "razao.xlsx"] }} />);
    expect(screen.getByText(/10 casados/)).toBeInTheDocument();
    expect(screen.getByText(/extrato\.xlsx/)).toBeInTheDocument();
  });
  it("mostra trecho do erro quando ha stderr", () => {
    render(<ReportCard report={{ execution_id: "x", status: "error", resumo: null,
      output_keys: [], stderr_excerpt: "KeyError 'Valor'", input_files: [] }} />);
    expect(screen.getByText(/KeyError 'Valor'/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run (em `front`): `npx vitest run src/test/reportCard.test.tsx`
Expected: FAIL (módulo `../pages/reportCard` não existe).

- [ ] **Step 3: Implementar `ReportCard`**

Criar `front/src/pages/reportCard.tsx`:

```tsx
export type ExecutionReport = {
  execution_id: string;
  status: string;
  resumo: string | null;
  output_keys: string[];
  stderr_excerpt: string | null;
  input_files: string[];
};

export function ReportCard({ report }: { report: ExecutionReport }) {
  return (
    <div className="rounded-xl border border-line bg-surface-2 p-3 text-sm">
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink3">
        Resultado reportado ({report.status === "error" ? "erro" : "concluído"})
      </div>
      {report.resumo && <div className="text-ink2">{report.resumo}</div>}
      {report.stderr_excerpt && (
        <pre className="mt-1 overflow-auto rounded bg-surface p-2 text-xs text-err">{report.stderr_excerpt}</pre>
      )}
      {report.input_files.length > 0 && (
        <div className="mt-1 text-xs text-ink3">Arquivos: {report.input_files.join(", ")}</div>
      )}
      <div className="mt-1 text-[11px] text-ink3">
        A correção altera o que a automação faz (o script). Problemas de exibição da plataforma não são ajustados aqui.
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Rodar o teste e ver passar**

Run (em `front`): `npx vitest run src/test/reportCard.test.tsx`
Expected: PASS (2 testes).

- [ ] **Step 5: Commit**

```bash
git add front/src/pages/reportCard.tsx front/src/test/reportCard.test.tsx
git commit -m "feat(chat): componente ReportCard do resultado reportado"
```

---

## Task 5: Modo reporte no SmartChat

**Files:**
- Modify: `front/src/components/SmartChat.tsx`

**Interfaces:**
- Consumes: `ReportCard`, `ExecutionReport` (Task 4); `GET/POST` de chat existentes; `POST /chat/report` e `/chat/report-repair` (Tasks 2, 3).
- Produces: comportamento de "modo reporte" ativado por `?report=<execution_id>` na URL.

- [ ] **Step 1: Ler o parâmetro `report` e fixar a execução ao montar**

Em `SmartChat.tsx`, importar `useSearchParams` de `react-router-dom` e `ReportCard`, `type ExecutionReport` de `../pages/reportCard`. Adicionar estado e efeito (após os estados existentes):

```tsx
const [searchParams, setSearchParams] = useSearchParams();
const [reportExecId, setReportExecId] = useState<string | null>(null);
const seededReportFor = useRef<string | null>(null);

useEffect(() => {
  const rep = searchParams.get("report");
  if (rep && seededReportFor.current !== rep) {
    seededReportFor.current = rep;
    setReportExecId(rep);
    api
      .post(`/api/projects/${projectId}/chat/report`, { execution_id: rep })
      .then(() => load())
      .catch(() => {});
    // limpa o param da URL para não refixar em reloads
    searchParams.delete("report");
    setSearchParams(searchParams, { replace: true });
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [searchParams, projectId]);
```

- [ ] **Step 2: Rotear o envio no modo reporte para o reparador**

No início de `send(...)`, antes do fluxo normal, tratar o caso reporte (usa a descrição do usuário como `message`, chama o endpoint não-streaming, recarrega e sai do modo):

```tsx
if (reportExecId) {
  const desc = (textOverride ?? input).trim();
  if (!desc || busy) return;
  setInput("");
  setBusy(true);
  try {
    setMessages((m) => [...m, { id: Date.now(), role: "user", content: desc, meta: {}, tokens: 0, created_at: "" }]);
    await api.post(`/api/projects/${projectId}/chat/report-repair`, {
      execution_id: reportExecId,
      message: desc,
    });
    setReportExecId(null);
    await load();
    onApplied();
  } catch (e: any) {
    setMessages((m) => [...m, { id: Date.now() + 1, role: "assistant", content: `Erro: ${e.message}`, meta: {}, tokens: 0, created_at: "" }]);
  } finally {
    setBusy(false);
  }
  return;
}
```

- [ ] **Step 3: Renderizar o card quando a mensagem tem `execution_report`**

No `messages.map`, envolver o `Bubble` para mostrar o card acima da bolha quando houver `meta.execution_report`:

```tsx
{messages.map((m) => (
  <div key={m.id} className="space-y-2">
    {m.meta?.execution_report && (
      <ReportCard report={m.meta.execution_report as ExecutionReport} />
    )}
    <Bubble message={m} />
  </div>
))}
```

Ajustar o placeholder do compositor quando em modo reporte:

```tsx
placeholder={reportExecId ? "Descreva o que ficou errado neste resultado..." : "Descreva o que automatizar..."}
```

- [ ] **Step 4: Verificar build de tipos**

Run (em `front`): `npx tsc --noEmit`
Expected: sem erros de tipo nos arquivos alterados.

- [ ] **Step 5: Rodar os testes de front existentes (sem regressão)**

Run (em `front`): `npx vitest run`
Expected: PASS (incluindo `reportCard.test.tsx` e os já existentes).

- [ ] **Step 6: Commit**

```bash
git add front/src/components/SmartChat.tsx
git commit -m "feat(chat): SmartChat entra em modo reporte e roteia para o reparador"
```

---

## Task 6: Botão "Reportar problema" na tela de resultado do Wizard

**Files:**
- Modify: `front/src/pages/Wizard.tsx`

**Interfaces:**
- Consumes: navegação para `/projects/:id/chat?report=<execution_id>`.
- Produces: botão visível na área de resultado do teste (sucesso e erro), usando `exec.id`.

- [ ] **Step 1: Adicionar o botão na área de resultado**

Na seção de resultado do teste (perto de "Baixar resultado", ~[Wizard.tsx:1500](../../../front/src/pages/Wizard.tsx#L1500)), com `exec?.id` disponível e o `useNavigate` (`nav`) já no componente:

```tsx
{exec?.id && (exec.status === "success" || exec.status === "error") && (
  <button
    type="button"
    onClick={() => nav(`/projects/${projectId}/chat?report=${exec.id}`)}
    className="btn-outline inline-flex items-center gap-1.5 py-1.5 text-xs"
  >
    Reportar problema
  </button>
)}
```

Se `nav` não estiver no escopo desse subcomponente, passar `projectId` já existe; usar `useNavigate` no componente que renderiza o resultado (o mesmo que tem `downloadResult`).

- [ ] **Step 2: Verificar tipos e build**

Run (em `front`): `npx tsc --noEmit`
Expected: sem erros.

- [ ] **Step 3: Verificação manual rápida (opcional, se app rodando)**

Abrir o Wizard de um projeto com teste concluído, clicar "Reportar problema", confirmar que vai para `/projects/<id>/chat` e o card aparece.

- [ ] **Step 4: Commit**

```bash
git add front/src/pages/Wizard.tsx
git commit -m "feat(wizard): botao Reportar problema na tela de resultado do teste"
```

---

## Task 7: Botão "Reportar problema" no app publicado (só dono logado) + ponte

**Files:**
- Modify: `front/src/pages/PublishedApp.tsx`

**Interfaces:**
- Consumes: `getToken` de `../lib/api` (sessão do app principal), `info.project.id`, `execution_id` do run.
- Produces: botão no resultado, visível só quando há `getToken()`; deep-link `/projects/<project_id>/chat?report=<execution_id>`.

- [ ] **Step 1: Guardar o `execution_id` em estado**

Em `PublishedApp.tsx`, adicionar estado `const [lastExecId, setLastExecId] = useState<string | null>(null);` e, em `pollExecution(execId, ...)`, no início: `setLastExecId(execId);`.

- [ ] **Step 2: Ler `project_id` do `/info`**

Confirmar que `/api/app/<sub>/info` retorna o id do projeto. Se `info.project?.id` não vier, ajustar o backend `published.py` para incluí-lo no `/info` (campo `project_id`). Ler no frontend: `const projectId = info?.project?.id ?? info?.project_id;`.

- [ ] **Step 3: Adicionar o botão gated por sessão do app principal**

Importar `getToken` de `../lib/api`. Na área de resultado (perto de "Baixar resultado", ~[PublishedApp.tsx:420](../../../front/src/pages/PublishedApp.tsx#L420)):

```tsx
{getToken() && lastExecId && projectId && (
  <a
    href={`/projects/${projectId}/chat?report=${lastExecId}`}
    className="btn-outline inline-flex items-center justify-center py-1.5 text-xs"
  >
    Reportar problema
  </a>
)}
```

Anônimo não tem `getToken()`, então não vê o botão. Não-dono que estiver logado cai no 403/404 do servidor ao usar os endpoints.

- [ ] **Step 4: Verificar tipos e build**

Run (em `front`): `npx tsc --noEmit`
Expected: sem erros.

- [ ] **Step 5: Commit**

```bash
git add front/src/pages/PublishedApp.tsx back/app/routers/published.py
git commit -m "feat(published): botao Reportar problema (dono logado) com deep-link ao chat"
```

---

## Self-Review

**Spec coverage:**
- Botão em erro e sucesso, Wizard + publicado, só dono: Tasks 6, 7. ✓
- Fixar execução no chat: Task 2 (`chat/report`) + Task 5 (render do card). ✓
- Usuário descreve, reparador responde e propõe correção aprovável: Task 3 + Task 5 (roteamento) + reuso do approve. ✓
- Reparador com o resultado (falso sucesso): Task 1 (`_execution_context` inclui output). ✓
- Ponte publicado → chat só dono: Task 7 (gate por `getToken`, enforcement no servidor). ✓
- Limitação declarada na UI: Task 4 (texto no card). ✓
- Sem alterar a FSM do orquestrador: endpoints dedicados em `repair.py`. ✓

**Placeholder scan:** Task 3 Step 1 referencia um fixture de teste que pode não existir; a nota instrui criar um setup mínimo reusando o padrão de `TestClient` já presente em `back/tests/`. Sem outros placeholders.

**Type consistency:** `ExecutionReport` (Task 4) usa os mesmos campos que `_execution_report_snapshot` (Task 2): `execution_id, status, resumo, output_keys, stderr_excerpt, input_files`. `PendingAction` edit_file com `payload.path`/`payload.content` casa com `approve_action` e `_apply_action` (chat.py). `run_repair(db, project, stage, execution_id, hint)` idêntico entre Tasks 1 e 3.

## Questões resolvidas (eram abertas na spec)
- Refixar: `?report=` é limpo da URL após fixar (Task 5), e `seededReportFor` evita duplicar; cada clique novo no resultado fixa uma vez.
- Limite de tentativas: o fluxo do chat não impõe MAX; cada reporte gera uma proposta aprovável. Se quiser limite, é incremento futuro (YAGNI agora).
