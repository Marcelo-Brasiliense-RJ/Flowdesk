# Auto-reparo colaborativo no Assistente (FlowDesk)

Data: 2026-06-10
Branch: flowdesk/spec-assistente-automacao

## Problema

No painel "Testar com dados de exemplo" do Assistente (`TestPanel` em
[Wizard.tsx](../../../front/src/pages/Wizard.tsx)), quando o teste falha, o usuário
só recebe uma mensagem amigável e a orientação de "ajustar a descrição" ou "abrir o
modo avançado". Um usuário não técnico (contábil/automação) não tem como corrigir o
script. Falta um caminho de reparo assistido por IA em que o próprio usuário participe.

## Objetivo

Permitir que, ao falhar um teste, o usuário acione um reparo assistido por IA,
**colaborativo e com aprovação**: a IA diagnostica o erro e propõe a correção em
linguagem simples; o usuário aprova (podendo dar uma dica) antes de aplicar; o sistema
re-roda o teste; e o ciclo se repete por até um limite de tentativas.

Não-objetivos (YAGNI): reparo automático silencioso; reparo no modo avançado (canvas);
histórico/auditoria de reparos; reparo de etapas que não sejam o Script.

## Decisões (alinhadas com o usuário)

1. Modelo de interação: **colaborativo com aprovação**.
2. Proposta: **linguagem simples + diff técnico opcional** ("ver alteração no código").
3. Loop: **até 3 tentativas** (`MAX_REPAIR_ATTEMPTS = 3`); a cada rodada o usuário pode
   adicionar uma **dica** em linguagem simples, e a IA tenta de novo vendo o novo erro + a dica.
4. Provedor de IA: mesma stack do restante do app (OpenAI, via `settings.ai_enabled`).

## Arquitetura

### Backend — `routers/repair.py` (novo)

Reusa helpers de `routers/chat.py` (`_attachment_context`) e de `routers/projects.py`
(`get_project`). Prefixo `/api`.

#### `POST /projects/{project_id}/stages/{stage_id}/repair/propose`

Body: `{ "execution_id": str, "hint": str | null }`

Comportamento:
- Valida posse do projeto (`get_project`) e que `stage_id` é um Script do projeto.
- Exige `settings.ai_enabled`; senão `400` ("IA indisponível para reparo").
- Carrega:
  - o código atual do Script (`SourceFile` cujo `path == stage.entry_file`);
  - a execução (`Execution`) e dela `stderr` (erro técnico) e `input_data`;
  - contexto do arquivo de exemplo via `_attachment_context(project_id, paths)` quando
    `input_data` referenciar arquivos existentes.
- Chama OpenAI em modo JSON pedindo:
  `{ "diagnosis": str, "change_summary": str, "fixed_code": str }`
  - `diagnosis`: causa em linguagem simples (sem jargão), ex.: "a coluna Valor não foi
    encontrada na sua planilha".
  - `change_summary`: o que será ajustado, 1-2 frases simples.
  - `fixed_code`: script corrigido completo (mantendo o uso do SDK `flowdesk_sdk`).
  - Inclui a `hint` do usuário no prompt quando presente.
- Resposta: `{ diagnosis, change_summary, fixed_code, has_changes }`, onde
  `has_changes = fixed_code.strip() != codigo_atual.strip()`.
- Falha de IA ou `has_changes == false` → resposta com `has_changes=false` e
  `diagnosis`/`change_summary` vazios ou explicativos (o frontend mostra "não consegui
  identificar uma correção automática").

#### `POST /projects/{project_id}/stages/{stage_id}/repair/apply`

Body: `{ "code": str }`

Comportamento:
- Valida posse e que `stage_id` é Script do projeto; `code` não vazio.
- Grava `code` no `SourceFile` do `stage.entry_file` (reusa o padrão de `_write_source`
  do wizard, ou query direta). Retorna `{ ok: true }`.
- Não executa nada: o re-teste é responsabilidade do frontend (reusa o endpoint de run
  já existente: `POST /projects/{id}/stages/{stage_id}/run` + polling de
  `/executions/{id}`).

#### Schemas (`schemas.py`)

```python
class RepairProposeIn(BaseModel):
    execution_id: str
    hint: str | None = None

class RepairProposeOut(BaseModel):
    diagnosis: str = ""
    change_summary: str = ""
    fixed_code: str = ""
    has_changes: bool = False

class RepairApplyIn(BaseModel):
    code: str
```

#### Registro do router

Incluir `repair.router` em `app/main.py` junto aos demais routers.

### Frontend — `RepairPanel` dentro do `TestPanel` (Wizard.tsx)

Estado do reparo (no `TestPanel` ou em sub-componente `RepairPanel`):
- `phase: "idle" | "proposing" | "proposed" | "applying" | "exhausted"`
- `proposal: { diagnosis, change_summary, fixed_code, has_changes } | null`
- `hint: string`
- `attempts: number` (limite `MAX_REPAIR_ATTEMPTS = 3`)
- `showCode: boolean` (expande o diff técnico)

Fluxo:
1. O painel só aparece quando `exec?.status === "error"` e `build.ai_enabled` é verdadeiro.
   Botão primário **"Reparar com IA"**.
2. Ao acionar → `phase=proposing`; chama `repair/propose` com `{ execution_id: exec.id, hint }`.
3. `proposed`: mostra `diagnosis` e `change_summary` (linguagem simples). Link
   "Ver alteração no código" (expande `fixed_code`, e o código atual para comparação).
   Campo opcional "Dar uma dica". Botões **"Aplicar e testar"** / **"Cancelar"**.
   - Se `has_changes == false`: mensagem "não consegui identificar uma correção
     automática; ajuste a descrição na etapa Processamento ou abra o modo avançado".
4. **"Aplicar e testar"** → `phase=applying`; chama `repair/apply` com `{ code: fixed_code }`;
   em seguida re-roda o teste reusando `runTest()`. `attempts += 1`.
5. Resultado do re-teste:
   - sucesso → estado de sucesso existente (libera "Publicar"). Reparo encerrado.
   - erro e `attempts < 3` → permite nova rodada: novo "Reparar com IA" que chama
     `propose` com o novo `execution_id` + dica atualizada.
   - erro e `attempts >= 3` → `phase=exhausted`: mensagem de limite com as saídas atuais
     (ajustar descrição / modo avançado).
6. "Cancelar" volta para `idle` sem alterar nada.

Acessibilidade/estado: botões com estado de carregamento (`proposing`/`applying`),
spinners, mensagens de erro próximas ao painel. O diff técnico é opcional e recolhido
por padrão.

## Tratamento de erros

| Situação | Comportamento |
|---|---|
| IA desabilitada | Botão "Reparar com IA" oculto; mantém orientação atual. |
| `propose` falha (rede/IA) | Mensagem no painel + permitir tentar de novo (não consome tentativa). |
| IA sem correção (`has_changes=false`) | Mensagem orientando ajustar descrição / modo avançado. |
| Re-teste ainda falha (`attempts < 3`) | Oferece nova rodada com dica. |
| Limite de tentativas atingido | `exhausted`: encerra com saídas atuais. |

Segurança: o `fixed_code` roda no mesmo subprocesso isolado dos scripts normais
(`runtime.runner`); o reparo não introduz novo vetor de execução.

## Testes

Backend (pytest, OpenAI mockado):
- `propose` retorna estrutura válida e `has_changes=true` quando o código muda.
- `propose` com `ai_enabled=false` → `400`.
- `propose`/`apply` rejeitam projeto de outra org e `stage` que não é Script.
- `apply` grava o `SourceFile` do `entry_file`.

Frontend (opcional, leve): a renderização condicional do `RepairPanel` por
`exec.status === "error"` e `ai_enabled`.

## Arquivos afetados

- `back/app/routers/repair.py` (novo)
- `back/app/schemas.py` (3 schemas novos)
- `back/app/main.py` (registro do router)
- `front/src/pages/Wizard.tsx` (`RepairPanel` + estado no `TestPanel`)
- `testes/` (testes do `propose`/`apply`, na pasta de testes existente do projeto)
