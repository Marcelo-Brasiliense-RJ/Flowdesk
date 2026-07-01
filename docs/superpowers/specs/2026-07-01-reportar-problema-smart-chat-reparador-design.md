# Reportar problema no Smart Chat com o reparador

Data: 2026-07-01
Status: aprovado (aguardando plano de implementação)

## Contexto

Depois de rodar uma automação (no teste do Wizard ou no app publicado), o resultado
pode estar errado de duas formas: execução com erro (stderr) ou "falso sucesso"
(rodou sem erro, mas o resultado está incorreto, ex.: conciliação casando lançamentos
errados, colunas trocadas). Hoje só existe o `RepairPanel` no Wizard, que aparece
apenas na caixa de erro do teste. Não há caminho para relatar um problema a partir do
resultado, nem quando a execução "deu sucesso".

Já existe infraestrutura reaproveitável:

- Reparador: [back/app/routers/repair.py](../../../back/app/routers/repair.py) com
  `POST /projects/{id}/stages/{stage_id}/repair/propose` (recebe `execution_id` +
  `hint`, junta código + `stderr` + anexos + plano, devolve
  `{diagnosis, change_summary, fixed_code, has_changes}`) e `.../repair/apply`.
- `Execution` guarda `stdout`, `stderr`, `input_data`, `output_data`, `status`
  (`queued|running|success|error`).
- Ações aprováveis do chat: `PendingAction` + `POST .../pending-actions/{id}/approve`,
  que ao aplicar um `edit_file .py` já re-sincroniza os campos de arquivo do Form
  (comportamento recém-adicionado em `chat._sync_input_file_fields`).
- Chat/Smart Chat vive na página do Wizard ([front/src/pages/Wizard.tsx](../../../front/src/pages/Wizard.tsx)).

## Objetivo

Botão "Reportar problema" na tela de resultado (Wizard e app publicado), visível
apenas ao dono logado, disponível em erro E em sucesso. Ao acionar, o Smart Chat do
projeto recebe a execução "fixada" (card), o usuário escreve o que está errado, e o
reparador responde no chat com diagnóstico e uma correção aprovável do script.

## Não-objetivos

- Corrigir bugs de plataforma/renderização (ex.: o "mega lista" era frontend). O
  reparador só edita o **script Python** da automação. A UI deve deixar isso claro.
- Reporte por usuário anônimo do app publicado (sem sessão do dono). Fora de escopo.
- Auto-aplicar a correção sem aprovação humana. Mantém-se o gate de aprovação.
- Alterar a FSM do orquestrador. O fluxo de reporte usa endpoints dedicados.

## Fluxo do usuário

1. Na tela de resultado (Wizard e publicado), o dono logado vê "Reportar problema",
   em erro ou sucesso.
2. Ao clicar, vai ao Smart Chat do projeto com a execução fixada: card com status,
   resumo/saída (`output_data`), trecho do `stderr` (se houver) e nomes dos arquivos
   enviados (`input_data`).
3. O chat pede: "Me diga o que ficou errado neste resultado." O usuário escreve só o
   problema.
4. Ao enviar, o reparador responde no chat: diagnóstico + o que vai mudar, e propõe a
   correção como `PendingAction` (edit_file do script).
5. Usuário aprova → aplica no script → re-sincroniza o Form → re-testa.

## Backend

### Enriquecer o reparador com o resultado
`repair_propose` (e a lógica reusada pelo endpoint de reporte) passa a incluir, além do
`stderr`, um resumo do `output_data` da execução, para dar sinal em falso sucesso.
Contrato de saída inalterado (`diagnosis, change_summary, fixed_code, has_changes`).
Truncar o output para um teto de caracteres, como já é feito com código/stderr.

### `POST /projects/{id}/chat/report`
Corpo: `{ "execution_id": "<uuid>" }`. Autenticado; valida posse (`get_project`) e que
a execução pertence ao projeto. Monta o snapshot e persiste uma `ChatMessage`
(role=assistant) com:
- `content`: mensagem amigável pedindo o que ficou errado.
- `meta.execution_report`: `{ execution_id, status, resumo (str|null), output_keys,
  stderr_excerpt (str|null), input_files: [nome...] }`.
Retorna a mensagem criada. Idempotência não é requisito (cada clique fixa de novo é
aceitável; ver questões em aberto).

### `POST /projects/{id}/chat/report-repair`
Corpo: `{ "execution_id": "<uuid>", "message": "<texto do usuário>" }`. Autenticado;
valida posse + execução. Passos:
1. Persiste `ChatMessage` role=user com o texto (opcional: `meta.execution_id`).
2. Resolve o stage de script do projeto e o código atual.
3. Chama a lógica do reparador com `hint = message` (código + stderr + output).
4. Persiste `ChatMessage` role=assistant com `diagnosis` + `change_summary`.
5. Se `has_changes`, cria `PendingAction` kind=`edit_file`, `payload.path` = entry_file
   do script, `payload.content` = `fixed_code`, título "Correção da automação".
Retorna `{ message, action|null }`. A aprovação reusa o fluxo existente
(`approve_action` → aplica código → re-sincroniza Form).

## Frontend

### Estado da execução
Wizard e PublishedApp guardam o `execution_id` da última execução em estado (o
PublishedApp já o recebe em `res.execution_id`, mas não persiste em estado).

### Botão na tela de resultado
- Wizard: botão na área de resultado do teste (sucesso e erro).
- PublishedApp: botão no bloco de resultado, visível só quando há sessão do app
  principal no navegador (`getToken()` presente). Anônimo não vê.

### Ponte publicado → chat
No publicado, o botão faz deep-link para `/projects/<id>?report=<execution_id>`. O
`project_id` vem do `/info` do app publicado (expor se ainda não vier). A posse é
validada no servidor ao chamar os endpoints; não-dono recebe 403/404 e cai no login.

### Modo reporte no Wizard
O Wizard lê `?report=<execution_id>` (ou recebe o clique local no teste), chama
`/chat/report` (fixa a execução), abre o chat e entra em "modo reporte": o próximo
envio do compositor vai para `/chat/report-repair` com o `execution_id` em vez do
`/chat` normal. O modo encerra ao aprovar a correção ou ao dispensar o card.
Renderiza o card a partir de `meta.execution_report` e a proposta com botão aprovar
(reusa o componente de ação/aprovação do chat).

## Tratamento de erros

- IA indisponível: mesma resposta do reparador atual (400 "IA indisponível").
- Execução inexistente ou de outro projeto: 404.
- `has_changes` falso (reparador não achou o que mudar): posta o diagnóstico sem ação;
  UI mostra o texto e sugere detalhar melhor o problema.
- Deep-link para não-dono: 403/404 do servidor; o Wizard mostra acesso negado.

## Testes

- Unit (pytest): `repair_propose` inclui `output_data` no contexto (montagem da
  mensagem contém o resumo). Snapshot de `/chat/report` com uma execução de sucesso e
  uma de erro. `/chat/report-repair` cria `PendingAction` edit_file quando há correção
  e não cria quando não há.
- Frontend (vitest): visibilidade do botão (com/sem `getToken`), leitura do
  `?report=` e transição para "modo reporte".

## Limitação declarada na UI

Deixar visível (texto curto no card ou perto do botão) que a correção altera o que a
automação **faz** (o script), e que problemas de exibição da plataforma não são
resolvidos por aqui.

## Questões em aberto (resolver no plano)

- Refixar: permitir múltiplos cards de reporte na conversa, ou substituir o pin ativo?
  Proposta: um pin ativo por vez; novo clique substitui.
- Limite de tentativas de reparo pelo chat (o `RepairPanel` usa MAX=3). Decidir se o
  fluxo do chat também limita.
