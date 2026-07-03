# Correções de QA do FlowDesk (5 testes contábeis) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corrigir os defeitos de plataforma e de comportamento do Smart Chat revelados pelos 5 testes de QA (soma, conciliação por chave, razão D x C, aging, conciliação por valor+data), de forma validável e incremental.

**Architecture:** Três frentes. Fase A corrige bugs determinísticos de plataforma (download, serialização, render, seed defasado), testáveis em pytest/vitest puro. Fase B ajusta o gatilho de entrevista do Smart Chat. Fase C endurece o system prompt para o código gerado pela IA e revalida ponta a ponta reusando os 5 agentes de QA. Cada tarefa entrega algo testável de forma independente.

**Tech Stack:** Backend FastAPI + Python 3.11 + pandas (pytest, venv em `back/.venv`). Frontend React 18 + TypeScript + Vite (vitest). IA via OpenAI (gpt-4o-mini), modo streaming.

## Global Constraints

- Backend roda a partir de `back/`; pytest via `back/.venv/Scripts/python.exe -m pytest`.
- Não introduzir dependência nova. pandas, openpyxl, httpx, pytest já existem.
- Comunicação em PT-BR, registro profissional, sem travessão (use vírgula).
- `storage/` é gitignored e regenerado pelo runtime; correções de conteúdo de projeto seed vão em `back/app/seed.py`, nunca direto em `back/storage/`.
- Data-base de referência dos testes: 2026-06-08. Gabaritos em `testes/README.md` são a fonte da verdade.
- Não commitar `back/flowdesk.db` nem `back/storage/`.

---

## Resumo dos achados que cada tarefa endereça

| Origem (teste) | Sintoma | Tarefa |
|---|---|---|
| T1, T2-chat | Download da saída devolve 404 quando o script grava nome de arquivo nu | A1 |
| T1 | `total_geral` serializado como string `"1700"` (numpy via `default=str`) | A2 |
| T1 | Resumo com lista de dict renderiza `[object Object]` na tela publicada | A3 |
| T2 (/app/conciliador) | App publicado lê `planilha_x` e ignora o 2º arquivo; seed em disco defasado | A4 |
| T1, T3, T4 (0 perguntas), T2 (1 só) | Entrevista pulada: `build_intent` casa verbos do enunciado ("gere", "concilie") | B1 |
| T3 (D x C), T4 (sinal do aging), T5 (1:1, dif. de dias) | Código gerado pela IA contábilmente incorreto | C1 |
| T2, T3, T4 | "success" silencioso com resultado errado | C1 (gate de invariantes) + revalidação C2 |

---

## FASE A, Bugs determinísticos de plataforma

### Task A1: Download tolera nome de arquivo nu (cai na pasta output)

**Files:**
- Modify: `back/app/routers/published.py:241-256`
- Test: `back/tests/test_download_resolve.py` (criar)

**Interfaces:**
- Produces: `_resolve_download_target(root: Path, output_folder_name: str, path: str) -> Path` em `published.py`.

- [ ] **Step 1: Escrever o teste que falha**

Criar `back/tests/test_download_resolve.py`:

```python
"""O download deve achar o arquivo mesmo quando o script grava só o nome nu."""
import sys
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

from app.routers.published import _resolve_download_target


def test_resolve_acha_na_raiz(tmp_path):
    (tmp_path / "r.xlsx").write_text("x")
    assert _resolve_download_target(tmp_path, "output", "r.xlsx") == (tmp_path / "r.xlsx").resolve()


def test_resolve_cai_na_pasta_output(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    (out / "r.xlsx").write_text("x")
    # script gravou só "r.xlsx"; o arquivo real está em output/
    assert _resolve_download_target(tmp_path, "output", "r.xlsx") == (out / "r.xlsx").resolve()


def test_resolve_respeita_caminho_explicito(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    (out / "r.xlsx").write_text("x")
    assert _resolve_download_target(tmp_path, "output", "output/r.xlsx") == (out / "r.xlsx").resolve()
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `back/.venv/Scripts/python.exe -m pytest tests/test_download_resolve.py -v` (a partir de `back/`)
Expected: FAIL com `ImportError: cannot import name '_resolve_download_target'`.

- [ ] **Step 3: Implementar o helper e usá-lo no endpoint**

Em `back/app/routers/published.py`, adicionar o helper antes de `app_download` e refatorar o corpo:

```python
def _resolve_download_target(root: Path, output_folder_name: str, path: str) -> Path:
    candidate = Path(path)
    target = (candidate if candidate.is_absolute() else (root / path)).resolve()
    # scripts às vezes gravam só o nome do arquivo; o real vive na pasta de saída
    if not target.exists() and not candidate.is_absolute():
        alt = (root / output_folder_name / path).resolve()
        if alt.exists():
            return alt
    return target
```

Substituir o miolo de `app_download` (linhas 247-255) por:

```python
    from pathlib import Path

    target = _resolve_download_target(root, project.output_folder_name, path)
    root_r = root.resolve()
    if root_r not in target.parents and target != root_r:
        raise HTTPException(status_code=400, detail="Caminho inválido")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
```

Garantir `from pathlib import Path` no topo do módulo (mover para o topo se hoje está dentro da função).

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `back/.venv/Scripts/python.exe -m pytest tests/test_download_resolve.py -v`
Expected: PASS, 3 testes.

- [ ] **Step 5: Commit**

```bash
git add back/app/routers/published.py back/tests/test_download_resolve.py
git commit -m "fix(download): resolver arquivo de saída na pasta output quando script grava nome nu"
```

---

### Task A2: `set_output` serializa números como número, não string

**Files:**
- Modify: `back/app/services/storage.py` (string `_SDK_SOURCE`, função `set_output`, linhas ~155-161)
- Test: `back/tests/test_sdk_helpers.py` (acrescentar caso)

**Interfaces:**
- Consumes: `_load_sdk(tmp_path, monkeypatch)` já existente em `test_sdk_helpers.py`.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar em `back/tests/test_sdk_helpers.py`:

```python
def test_set_output_preserva_numpy_como_numero(tmp_path, monkeypatch):
    import numpy as np
    import json
    sdk = _load_sdk(tmp_path, monkeypatch)
    sdk.set_output({"total": np.int64(1700), "frac": np.float64(2.5)})
    saved = json.loads((tmp_path / "output.json").read_text(encoding="utf-8"))
    assert saved["total"] == 1700 and isinstance(saved["total"], int)
    assert saved["frac"] == 2.5 and isinstance(saved["frac"], float)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `back/.venv/Scripts/python.exe -m pytest tests/test_sdk_helpers.py::test_set_output_preserva_numpy_como_numero -v`
Expected: FAIL, `saved["total"]` vem como string `"1700"` (assert de tipo quebra).

- [ ] **Step 3: Implementar a coerção no SDK**

Em `back/app/services/storage.py`, dentro de `_SDK_SOURCE`, substituir a função `set_output` por:

```python
def _json_default(o):
    # numpy/pandas escalares expõem .item() -> int/float nativo (não string)
    if hasattr(o, "item"):
        try:
            return o.item()
        except Exception:
            pass
    return str(o)


def set_output(data) -> None:
    if not isinstance(data, dict):
        data = {"resultado": data}
    Path(_OUTPUT).write_text(
        json.dumps(data, ensure_ascii=False, default=_json_default), encoding="utf-8"
    )
```

- [ ] **Step 4: Rodar e ver passar**

Run: `back/.venv/Scripts/python.exe -m pytest tests/test_sdk_helpers.py -v`
Expected: PASS (incluindo os testes pré-existentes).

- [ ] **Step 5: Commit**

```bash
git add back/app/services/storage.py back/tests/test_sdk_helpers.py
git commit -m "fix(sdk): set_output preserva numpy como número via _json_default"
```

---

### Task A3: Resumo estruturado na tela publicada (sem `[object Object]`)

**Files:**
- Modify: `front/src/pages/PublishedApp.tsx:395-398`
- Test: `front/src/test/formatSummaryValue.test.ts` (criar)

**Interfaces:**
- Produces: `formatSummaryValue(v: unknown): string` exportada de `PublishedApp.tsx`.

- [ ] **Step 1: Escrever o teste que falha**

Criar `front/src/test/formatSummaryValue.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { formatSummaryValue } from "../pages/PublishedApp";

describe("formatSummaryValue", () => {
  it("formata escalar", () => {
    expect(formatSummaryValue(1700)).toBe("1700");
  });
  it("formata lista de objetos legível", () => {
    const v = [{ produto: "Plano A", valor: 400 }, { produto: "Plano B", valor: 300 }];
    expect(formatSummaryValue(v)).toBe("Plano A: 400; Plano B: 300");
  });
  it("formata objeto chave-valor", () => {
    expect(formatSummaryValue({ a: 1, b: 2 })).toBe("a: 1; b: 2");
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run (a partir de `front/`): `npm run test -- formatSummaryValue`
Expected: FAIL, `formatSummaryValue` não existe. (Se o script de teste tiver outro nome, ajustar; o repo tem vitest configurado em `vite.config.ts`.)

- [ ] **Step 3: Implementar o helper e usá-lo no render**

Em `front/src/pages/PublishedApp.tsx`, adicionar perto do topo do arquivo (após os imports), exportando:

```ts
export function formatSummaryValue(v: unknown): string {
  if (Array.isArray(v)) {
    return v
      .map((item) =>
        item && typeof item === "object"
          ? Object.values(item as Record<string, unknown>).join(": ")
          : String(item)
      )
      .join("; ");
  }
  if (v && typeof v === "object") {
    return Object.entries(v as Record<string, unknown>)
      .map(([k, val]) => `${k}: ${String(val)}`)
      .join("; ");
  }
  return String(v);
}
```

Trocar a célula de valor (linha 398) de `{String(v)}` para `{formatSummaryValue(v)}`.

- [ ] **Step 4: Rodar e ver passar**

Run (a partir de `front/`): `npm run test -- formatSummaryValue`
Expected: PASS, 3 testes.

- [ ] **Step 5: Commit**

```bash
git add front/src/pages/PublishedApp.tsx front/src/test/formatSummaryValue.test.ts
git commit -m "fix(published): resumo renderiza listas/objetos legíveis em vez de [object Object]"
```

---

### Task A4: Seed auto-corrige o script do conciliador em bases já existentes

**Files:**
- Modify: `back/app/seed.py` (acrescentar `heal_seed_scripts`)
- Modify: `back/main.py:101` (chamar após `seed_if_empty`)
- Test: `back/tests/test_seed_heal.py` (criar)

**Contexto:** `RECONCILE_SCRIPT` em `seed.py` JÁ está correto (lê `planilha_a`/`planilha_b`, tem aba `Divergencias`, grava `str(out)`). O bug do T2 publicado é que `back/storage/1` foi semeado de uma versão antiga e `seed_if_empty()` só roda em DB vazio. Esta tarefa cura instalações existentes.

**Interfaces:**
- Consumes: `RECONCILE_SCRIPT`, `storage.materialize_sources` (de `seed.py`/`storage.py`).
- Produces: `heal_seed_scripts() -> int` (retorna nº de projetos curados).

- [ ] **Step 1: Escrever o teste que falha**

Criar `back/tests/test_seed_heal.py`:

```python
"""heal_seed_scripts restaura o script canônico do conciliador em bases antigas."""
import sys
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

from app.database import SessionLocal
from app.models import Project, SourceFile
from app.seed import RECONCILE_SCRIPT, heal_seed_scripts, seed_if_empty


def test_heal_restaura_script_defasado():
    seed_if_empty()
    db = SessionLocal()
    proj = db.query(Project).filter(Project.subdomain == "conciliador").first()
    assert proj is not None
    sf = db.query(SourceFile).filter(
        SourceFile.project_id == proj.id, SourceFile.path == "processar.py"
    ).first()
    sf.content = "# versao antiga quebrada\nplanilha_x = None\n"
    db.commit()
    db.close()

    curados = heal_seed_scripts()
    assert curados >= 1

    db = SessionLocal()
    sf = db.query(SourceFile).filter(
        SourceFile.project_id == proj.id, SourceFile.path == "processar.py"
    ).first()
    assert sf.content == RECONCILE_SCRIPT
    db.close()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `back/.venv/Scripts/python.exe -m pytest tests/test_seed_heal.py -v`
Expected: FAIL, `ImportError: cannot import name 'heal_seed_scripts'`.

- [ ] **Step 3: Implementar `heal_seed_scripts`**

Em `back/app/seed.py`, ao final do módulo:

```python
def heal_seed_scripts() -> int:
    """Mantém os scripts dos projetos seed sincronizados com a versão canônica,
    mesmo em bases já existentes (seed_if_empty só roda em DB vazio)."""
    from app.database import SessionLocal
    db = SessionLocal()
    curados = 0
    try:
        canon = {("conciliador", "processar.py"): RECONCILE_SCRIPT}
        for (subdomain, path), content in canon.items():
            proj = db.query(Project).filter(Project.subdomain == subdomain).first()
            if not proj:
                continue
            sf = db.query(SourceFile).filter(
                SourceFile.project_id == proj.id, SourceFile.path == path
            ).first()
            if sf and sf.content != content:
                sf.content = content
                db.commit()
                storage.materialize_sources(db, proj)
                curados += 1
        return curados
    finally:
        db.close()
```

Conferir que `storage`, `Project`, `SourceFile` já estão importados no topo de `seed.py` (estão; ver linhas 22 e imports de `storage`).

- [ ] **Step 4: Chamar no lifespan**

Em `back/main.py`, logo após a linha `seed_if_empty()` (linha 101):

```python
    from app.seed import heal_seed_scripts
    heal_seed_scripts()
```

- [ ] **Step 5: Rodar e ver passar**

Run: `back/.venv/Scripts/python.exe -m pytest tests/test_seed_heal.py -v`
Expected: PASS.

- [ ] **Step 6: Validação manual ponta a ponta do conciliador**

Reiniciar o backend (sem `--reload`), depois:

```bash
curl -s -X POST http://127.0.0.1:8000/api/auth/login -H "Content-Type: application/json" \
  -d '{"email":"admin@irko.com.br","password":"REMOVED-SEED-PASSWORD"}'
```

Subir `testes/teste2_sistema.xlsx` e `testes/teste2_banco.xlsx` no app `/app/conciliador` e conferir o resumo: `conciliados=3, somente_a=3, somente_b=3, divergencias=1`. A planilha de saída deve ter a aba `Divergencias` com `id=5, valor_A=500, valor_B=550`.

- [ ] **Step 7: Commit**

```bash
git add back/app/seed.py back/main.py back/tests/test_seed_heal.py
git commit -m "fix(seed): auto-curar script do conciliador em bases existentes"
```

---

## FASE B, Comportamento do Smart Chat

### Task B1: `build_intent` não pula a entrevista por causa de verbos do enunciado

**Files:**
- Modify: `back/app/routers/chat.py:311-317`
- Test: `back/tests/test_build_intent.py` (criar)

**Contexto:** Hoje a regex casa `gera|gere|cria|crie|monta|...` em qualquer posição, então "Concilie estas planilhas e gere uma saída" dispara construção e pula o discovery. A entrevista real é acionada pelo prefixo "Respostas da entrevista" (que a UI envia após responder). O ajuste: só tratar como "construir agora" quando for comando explícito (verbo no início da frase, ou verbo + "agora"), preservando o prefixo de respostas.

**Interfaces:**
- Produces: `_is_build_intent(content: str) -> bool` em `chat.py`.

- [ ] **Step 1: Escrever o teste que falha**

Criar `back/tests/test_build_intent.py`:

```python
import sys
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

from app.routers.chat import _is_build_intent


def test_prompt_descritivo_nao_constroi():
    # T1/T3/T4: verbo no meio da frase descreve a tarefa, deve ABRIR entrevista
    assert _is_build_intent("Tenho uma planilha de vendas. Quero o total por produto, gerando uma planilha de saída.") is False
    assert _is_build_intent("Concilie este razão contábil e gere um resumo com os totais.") is False
    assert _is_build_intent("Classifique cada título por faixa de atraso e some o valor por faixa.") is False


def test_prefixo_respostas_constroi():
    assert _is_build_intent("Respostas da entrevista: fonte=xlsx; saida=planilha") is True


def test_comando_explicito_constroi():
    assert _is_build_intent("pode montar agora") is True
    assert _is_build_intent("Monte o app") is True
    assert _is_build_intent("finaliza isso") is True
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `back/.venv/Scripts/python.exe -m pytest tests/test_build_intent.py -v`
Expected: FAIL, `_is_build_intent` não existe.

- [ ] **Step 3: Extrair e endurecer o predicado**

Em `back/app/routers/chat.py`, adicionar acima do handler:

```python
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
```

Substituir as linhas 311-317 por:

```python
    build_intent = _is_build_intent(body.content)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `back/.venv/Scripts/python.exe -m pytest tests/test_build_intent.py -v`
Expected: PASS, 3 testes.

- [ ] **Step 5: Commit**

```bash
git add back/app/routers/chat.py back/tests/test_build_intent.py
git commit -m "fix(chat): entrevista não é pulada por verbos do enunciado; build só em comando explícito"
```

---

## FASE C, Qualidade do código gerado e revalidação E2E

### Task C1: Endurecer o SYSTEM_PROMPT com receitas contábeis canônicas

**Files:**
- Modify: `back/app/routers/chat.py` (constante `SYSTEM_PROMPT`)
- Test: revisão manual do prompt + validação na Task C2 (saída da IA não é unit-testável de forma determinística)

**Contexto:** Os erros de T3 (groupby em vez de parear D x C, sinal do crédito), T4 (sinal invertido do aging) e T5 (sem casamento 1:1, sem coluna de diferença de dias) são erros de raciocínio do modelo. Acrescentar regras explícitas e trechos canônicos reduz a recorrência.

- [ ] **Step 1: Acrescentar a seção de regras ao SYSTEM_PROMPT**

Em `back/app/routers/chat.py`, dentro de `SYSTEM_PROMPT`, acrescentar um bloco:

```
REGRAS DE CÓDIGO PARA TAREFAS CONTÁBEIS/FISCAIS (siga à risca):
- Saída de arquivo: SEMPRE set_output({"arquivo_resultado": str(output_path("nome.xlsx")), ...}). Nunca passe o nome nu.
- Aging / dias de atraso: dias = (data_base - vencimento).days. dias <= 0 é "A vencer"; 1-30, 31-60, 61-90, 90+ usam o limite superior inclusivo. Pergunte a data-base se não vier. Para "por cliente E faixa", use pivot_table(index=cliente, columns=faixa, values=valor, aggfunc="sum").
- Conciliação débito x crédito que zera: pareie por VALOR ABSOLUTO (abs(valor)), tratando crédito negativo. Pareamento 1:1, marcando cada lançamento já usado; com valores repetidos, ordene de forma estável. Mantenha TODOS os registros (Conciliados + Não Conciliados = carregados) e gere resumo com as contagens que fecham.
- Conciliação por valor + data com tolerância: case mesmo valor com diferença de datas <= tolerância (em dias); > tolerância NÃO casa. Casamento 1:1 (não reutilize a mesma linha). Inclua na saída a coluna "dif_dias". Remova não casados por ÍNDICE da linha, nunca por valor de data.
- Antes de declarar sucesso, valide invariantes: somas por categoria fecham com o total carregado; não há divisão por zero; colunas esperadas existem (erro claro em PT-BR se faltar).
```

- [ ] **Step 2: Validar que o backend sobe com o prompt novo**

Run: `back/.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'.'); from app.routers.chat import SYSTEM_PROMPT; print('ok', len(SYSTEM_PROMPT))"` (a partir de `back/`)
Expected: imprime `ok` e o tamanho (sem erro de sintaxe).

- [ ] **Step 3: Commit**

```bash
git add back/app/routers/chat.py
git commit -m "feat(chat): regras canônicas contábeis no system prompt (aging, D x C, tolerância, output_path)"
```

---

### Task C2: Revalidação ponta a ponta dos 5 testes

**Files:** nenhum (validação). Pré-requisito: backend reiniciado SEM `--reload` com todas as Fases A, B, C aplicadas.

- [ ] **Step 1: Subir o backend limpo**

Run (a partir de `back/`): `.venv/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000`
Confirmar: `curl -s http://127.0.0.1:8000/api/health` retorna `{"status":"ok","ai_enabled":true}`.

- [ ] **Step 2: Rodar a suíte de pytest completa**

Run (a partir de `back/`): `.venv/Scripts/python.exe -m pytest tests/ -v`
Expected: todos os testes das Fases A e B passam; nenhum regrediu.

- [ ] **Step 3: Re-disparar os 5 agentes de QA**

Re-executar os 5 subagentes de QA com os mesmos prompts da rodada anterior (um por teste, persona usuário comum + técnico contábil/fiscal), contra o backend corrigido. Comparar cada veredito ao gabarito de `testes/README.md`.

Critério de aceite por teste:
- T1: total 1700 e quebra correta; download 200; resumo legível na tela.
- T2: Chat e /app/conciliador batem 3/3/3 e divergência id 5; download 200.
- T3: carregados 7, conciliados 4, não conciliados 3, soma fecha; sem crash.
- T4: faixas {A vencer 1400, 1-30 2500, 31-60 2500, 90+ 6000} (confirmar convenção de fronteira do vencimento na data-base com o usuário); matriz cliente x faixa presente.
- T5: 2 casados, par de 2500 fora por exceder 3 dias, coluna dif_dias presente, casamento 1:1.

- [ ] **Step 4: Registrar o placar**

Consolidar os 5 vereditos numa tabela antes/depois. Onde ainda houver falha de raciocínio do modelo (não determinística), abrir tarefa de template validado na galeria como follow-up.

---

## Self-Review (executado pelo autor do plano)

**Cobertura do spec:** os 7 grupos de achados da tabela inicial têm tarefa (A1, A2, A3, A4, B1, C1, C2). OK.

**Placeholders:** nenhum "TODO/TBD/etc." nos passos de código. As tarefas determinísticas (A1, A2, A4, B1) têm código e comandos exatos; A3 idem com vitest; C1 é edição de prompt (não unit-testável) validada por C2.

**Consistência de tipos/nomes:** `_resolve_download_target`, `_json_default`, `formatSummaryValue`, `heal_seed_scripts`, `_is_build_intent`, `RECONCILE_SCRIPT` usados com a mesma assinatura onde referenciados. `output_folder_name` confere com `models.py:87` (default "output").

**Risco aberto:** o gate de invariantes de C1 depende de o modelo segui-lo; T3/T4/T5 podem ainda falhar de forma não determinística. Mitigação registrada em C2 step 4 (template validado como follow-up).
