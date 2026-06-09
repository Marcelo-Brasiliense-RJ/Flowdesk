# Design: Assistente de automação para usuário não-técnico (FlowDesk)

- **Data:** 2026-06-09
- **Status:** aprovado (brainstorming), aguardando plano de implementação
- **Projeto:** FlowDesk (`flowdesk/`)

## Problema e objetivo

O FlowDesk nasceu como uma IDE de desenvolvedor: editor de código Python (Monaco),
explorador de arquivos e canvas técnico (React Flow), pensado para o desenvolvedor
montar automações *para* o usuário. A meta agora é inverter isso: permitir que o
**próprio usuário não-técnico** (profissionais de contabilidade, fiscal, auditoria
da IRKO) crie suas automações, sem nunca ver código.

A tela do Editor atual continua poderosa, porém intimidante e inadequada para esse
público. Precisamos de uma porta de entrada guiada.

## Decisões de produto (fechadas no brainstorming)

1. **Público:** não-técnico, *zero código*. O código continua existindo, mas fica
   escondido por padrão.
2. **Interação:** assistente passo a passo (wizard) de **4 etapas** fixas:
   **Gatilho → Entrada → Processamento → Resultado**. Escolhido em vez de chat puro
   por previsibilidade.
3. **IDE atual:** preservada como **modo avançado** (admin/dev/suporte), servindo de
   válvula de escape quando a IA gera código errado. O wizard é a porta de entrada.
4. **Rede de segurança:** **teste obrigatório com dados de exemplo** + explicação em
   português do que foi montado, antes de publicar.

## Risco central que o design ataca

Como toda automação roda em Python gerado pela IA, quando a geração erra o usuário
não-técnico não tem como corrigir pela interface, só re-descrever. Portanto a
**qualidade da geração e o tratamento de erro são o coração do produto**, não a
estética. O design prioriza o caminho de falha: descrever → ver explicação → testar
com dados reais → ver resultado ou erro traduzido → ajustar → só então publicar.

## Abordagem escolhida: A — camada fina sobre o modelo atual

O wizard é majoritariamente **orquestração de frontend** que dirige a API já
existente (`Stage`/`Edge`/arquivo/execução). Reaproveita o backend validado, não
introduz modelo de dados novo (exceto um campo de metadado), e o modo avançado é
literalmente o `Editor.tsx` de hoje.

Abordagens descartadas:
- **B (abstração de "receita" + compilador):** cria duas fontes de verdade (receita
  vs. código gerado) que divergem assim que um dev edita o código no modo avançado —
  exatamente o cenário que decidimos manter. Backend pesado, risco de YAGNI.
- **C (wizard conversacional):** flexível, mas menos previsível — o oposto da
  estrutura escolhida.

### Reaproveitamento já disponível (validado no código atual)

`SmartChat.tsx` e o backend já fornecem blocos prontos:
- `InterviewPanel`: uma pergunta por vez, com opções, "Outro", voltar/pular, `X/N`.
- Subir arquivo base (`POST /fs/upload`) e gerar exemplo (`POST /sample-spreadsheet`).
- Aprovação de pendências (`/pending-actions` + approve/reject).
- Geração via `/chat/stream`; execução por stage (`/stages/:id/run`); `publish`.
- Conceito de papéis (`Role`/`Member`) para gatear o modo avançado.

## Arquitetura

### Rotas e papéis
- **`/projects/:id/assistente`** — o wizard. Landing padrão do usuário não-técnico.
- **`/projects/:id/editor`** — o `Editor.tsx` atual = **modo avançado**, acessível só
  a admin/dev/suporte (gate por `Role`). Não-técnico não vê o botão de modo avançado.

### Dono da estrutura
O **frontend é dono das 4 etapas fixas**. A IA é chamada em momentos específicos
(geração no passo Processamento; interpretação do arquivo de entrada), nunca para
decidir o roteiro. É isso que garante a previsibilidade.

### Mapeamento etapa → modelo FlowDesk
Tudo via API existente, sem modelo de dados novo:

| Etapa do wizard | Vira no modelo FlowDesk |
|---|---|
| Gatilho | `Job` (agendado) ou `Hook` (ao receber) ou nada (manual via Form) |
| Entrada | `Form` com campos / upload de arquivo |
| Processamento | `Script` + arquivo `.py` gerado pela IA |
| Resultado | `Form` em modo `result` (resumo + download) |

As **edges** entre os nós e o `entry_file` são criados automaticamente pelo wizard; o
usuário nunca vê "aresta" nem nome de arquivo.

### Único toque no backend: `wizard_state`
Salvar as respostas do wizard em `project.wizard_state` (JSON), só para re-hidratar as
etapas na edição. **Não é fonte de verdade**: stages/código continuam canônicos. Se um
dev editar no modo avançado, o `wizard_state` é marcado como possivelmente defasado e a
edição pelo wizard avisa antes de regenerar (ver "Ponte com o modo avançado").

## As 4 etapas

Topo do wizard: trilha horizontal com as 4 etapas e `X/4`, botão "Voltar", e rascunho
salvo automaticamente (`wizard_state`) a cada avanço.

### Etapa 1 — Gatilho: "Como essa automação começa?"
Três cartões, escolha única:
- **Eu mesmo executo** (manual) → nenhum nó de gatilho; o Form de entrada é o início.
- **Em um horário** (agendado) → cria um `Job`; reusa o seletor amigável do
  `JobPreview` (a cada X / diariamente às HH:MM).
- **Quando chega algo de fora** (webhook) → cria um `Hook`; reusa `HookPreview`
  (URL pronta + "testar webhook").

### Etapa 2 — Entrada: "O que essa automação recebe?"
- **Um arquivo** (planilha/CSV/PDF): `Form` com campo `file`. Permite subir um
  arquivo base (`/fs/upload`) ou gerar um exemplo (`/sample-spreadsheet`). Esse
  arquivo base alimenta o teste obrigatório.
- **Alguns campos digitados**: construtor simples (rótulo + tipo: texto/número/data/
  lista), sem JSON. Vira `cfg.fields` do Form.
- **Nada**: pula direto.

### Etapa 3 — Processamento: "O que fazer com isso?" (o coração)
Caixa de texto guiada com placeholders do contexto IRKO ("remover linhas duplicadas
pela coluna Valor"; "somar por CNPJ e gerar um resumo"). Ao confirmar:
1. Chama a geração (backend do `/chat/stream`) passando a descrição + o
   cabeçalho/preview do arquivo base da Etapa 2, para a IA enxergar os dados reais.
2. Em vez de despejar código, mostra a **explicação em português** (lista de passos) e
   cria o `Script` + `.py` como **pendência** (reusa `pending-actions`).
3. O código fica oculto; só o modo avançado o expõe.

### Etapa 4 — Resultado: "O que você recebe de volta?"
- **Arquivo para baixar** (padrão): `Form` em modo `result` com download
  (`result_file_key`, já suportado em `StagePreview`).
- **Resumo na tela**: usa `summary_key`.
- *(Fora de escopo agora: e-mail.)*

Ao fim, o wizard montou: gatilho? → Form(entrada) → Script → Form(result), com edges
automáticas.

## Rede de segurança: teste obrigatório antes de publicar

Após a Etapa 4, tela de **Revisão e teste** (não um "Publicar" direto):

1. **Resumo em português** etapa por etapa: "Recebe uma planilha → remove duplicados
   pela coluna Valor → gera um Excel para baixar". Sem jargão, sem código.
2. **Rodar com dados de exemplo (obrigatório):** "Testar agora" usa o arquivo
   base/exemplo da Etapa 2 e dispara `/stages/:id/run`. O botão **"Publicar" fica
   desabilitado até existir um teste com status `success`**.
3. **Mostrar o resultado real:** preview do arquivo gerado (primeiras linhas) + link de
   download (`/fs/download`). É o que substitui a leitura de código.
4. **Quando o teste falha:** em vez de stack trace, mostrar:
   - mensagem traduzida ("A coluna 'Valor' não foi encontrada na planilha"),
   - botão **"Ajustar"** que volta à Etapa 3 com a descrição preenchida para refinar e
     regenerar,
   - e, só para admin/dev, link discreto "ver detalhes técnicos / abrir no modo
     avançado".

**Limite assumido:** a tradução de erro cobre casos comuns (coluna faltando, arquivo
vazio, formato errado). Erros raros caem num texto genérico + saída do modo avançado.
Não há promessa de tradução perfeita de todo erro de Python.

## Editar automação existente

Abrir uma automação recarrega as 4 etapas a partir do `wizard_state`. Cada etapa fica
como cartão-resumo editável ("Entrada: uma planilha · editar"). Mudou a Etapa 3?
Regenera só o `Script` daquele trecho e **re-exige o teste** antes de republicar.

### Ponte com o modo avançado
Se um dev mexeu no código/canvas pelo `Editor.tsx`, o `wizard_state` pode estar
defasado. Ao abrir o wizard nesse caso: aviso "Esta automação foi ajustada manualmente.
Editar pelo assistente pode sobrescrever esses ajustes." com **Continuar mesmo assim**
ou **Abrir no modo avançado**. Sem merge automático — decisão explícita do usuário.
Evita a divergência silenciosa condenada na Abordagem B.

## Escopo

**Neste trabalho:**
- Rota do wizard e as 4 etapas.
- Teste obrigatório com resultado/erro traduzido.
- Gate de papel para o modo avançado.
- `wizard_state` + aviso de defasagem.
- Edição re-hidratada.

**Fora de escopo (deliberado):**
- Saída por e-mail.
- Catálogo de modelos prontos (a abordagem híbrida não escolhida).
- Redesenho do Console/Dashboard.
- Multi-ramificação no canvas pelo wizard (cobre o fluxo linear
  gatilho→entrada→processo→saída, que é o caso comum).
- i18n além de pt-BR.

## Testes

- **Backend:** estender `qa_suite.py` (hoje 52/52) com casos de `wizard_state`
  (salvar/recarregar, marcação de defasagem) e do gate de papel.
- **Frontend:** `npm run build` limpo + teste de fluxo do wizard montando os 4 nós e
  bloqueando "Publicar" sem teste `success`.
- **Manual:** rodar um caso real de `flowdesk/testes/` (ex.: planilha de duplicados)
  ponta a ponta pelo wizard.

## Critérios de sucesso

- Um usuário não-técnico cria, testa e publica uma automação linear sem ver código.
- O teste obrigatório bloqueia publicação de automação que não roda com sucesso.
- Erros comuns aparecem traduzidos com caminho de ajuste.
- O modo avançado continua abrindo o mesmo projeto sem regressão.
