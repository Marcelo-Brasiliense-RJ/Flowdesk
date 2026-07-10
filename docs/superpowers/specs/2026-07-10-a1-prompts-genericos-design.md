# A1: Prompts centrais genéricos, conhecimento contábil em template sob demanda

Data: 2026-07-10
Item do dossiê: A1 (P1 de produto). Premissa: o FlowDesk é uma plataforma
GENÉRICA de automação; o caso extrato-Domínio foi um caso de teste. O
conhecimento contábil nos prompts centrais é DÍVIDA a extrair, não requisito a
preservar no núcleo.

## Problema

Três prompts centrais carregam conhecimento contábil hardcoded, enviado em TODA
geração, mesmo para automações que nada têm a ver com contabilidade. Isso
enviesa o modelo, gasta contexto e faz a plataforma "não encaixar" em casos
genéricos.

- `SYSTEM_PROMPT` (chat.py:45-185): blocos "CLASSIFICAÇÃO CONTÁBIL" e "EXTRATO
  BANCÁRIO → DOMÍNIO" (83-106), Domínio/Inicia Lote (72-76), aging/conciliação
  (180-185).
- `CONSTRUTOR_PROMPT` (orchestrator.py:165-187): exemplo "extrato e razão"
  (173-175) e frase de perfil contábil (181-183), esta redundante com a injeção
  condicional já feita em `run_construtor` (209-212).
- `_generate_build` instr (chat.py:504-540): trecho de extrato PDF
  crédito/débito/saldo (524-526).

## Achados que fundamentam o desenho (mapa por subagentes, 2026-07-10)

1. O contábil é minoria bem delimitada nos três prompts; o restante é genérico e
   coerente sem ele.
2. O mecanismo de carregar domínio sob demanda JÁ EXISTE e está em uso:
   `reference_for_task` (reference_code.py:27) casa o texto da tarefa com os
   templates da galeria e injeta o código do template como few-shot (REF_LOW=2)
   ou o semeia (REF_HIGH=4). É chamado em `run_construtor` (orchestrator.py:215)
   e no wizard `_generate_script` (wizard.py:198).
3. Os dois caminhos reais de build passam por esse encanamento: o chat delega a
   `orchestrate_turn` (chat.py:403 → run_construtor), e o wizard chama
   `reference_for_task` + `_generate_build`. Logo, injetar o conhecimento no
   template cobre ambos.
4. O template `extrato-dominio` (templates.py:89-344) já carrega o conhecimento
   contábil no CÓDIGO, e os testes `test_extrato_dominio*` testam esse código,
   NÃO os prompts. Tirar o contábil dos prompts não deve quebrá-los.
5. O gate `contabil` já é condicional: `enrich_accounting` só age se
   `plan.contabil` (orchestrator.py:285). Não precisa ser generalizado agora.

## Decisão de design (galho do grill-me resolvido)

"Como o conhecimento contábil é carregado sob demanda sem virar novo
acoplamento?" Resposta: reusar `reference_for_task`, que já existe e já é o ponto
de injeção. A ÚNICA estrutura nova é um campo de DADOS (`reference`) na entrada
do template, texto injetado só quando aquele template casa. Não há novo módulo,
nem nova dependência, nem novo caminho de código: é dado + reuso do encanamento.

Não generalizar `contabil`→`domínio` agora (YAGNI): só há um domínio real. O
gate condicional atual basta.

## Arquitetura

### 1. Campo `reference` no template

Adicionar uma chave opcional `reference` (texto) à entrada de template em
`TEMPLATES` (templates.py). Para `extrato-dominio`, ela recebe as instruções
contábeis extraídas dos prompts: contrato de colunas do Domínio, Inicia Lote,
convenção débito/crédito, plano de contas com cabeçalho deslocado, convenções
`regras_classificacao`/`_CONTA_BANCO`, e o protocolo de revisão em 2 passes.
Templates sem domínio específico não têm `reference` (ou vazio).

### 2. Injeção do `reference` sob demanda

`reference_for_task` passa a devolver também o `reference` do template casado.
Os pontos de injeção que já existem (`run_construtor` no orchestrator e
`_generate_script` no wizard) passam a incluir esse texto no contexto/mensagens
enviadas ao agente, junto do few-shot de código, quando o score ≥ REF_LOW.
Assim o conhecimento contábil chega ao modelo SÓ quando a tarefa casa com
extrato-dominio. Sem match, nenhum conteúdo contábil entra no contexto.

### 3. Prompts centrais genéricos

Remover os blocos contábeis dos três prompts. Onde a técnica é genérica mas está
redigida com vocabulário contábil, REESCREVER com termos neutros (não apagar):
- Parse posicional de PDF via pdfplumber (x0/x1): manter como técnica geral para
  QUALQUER tabela em PDF, com exemplo de colunas neutras.
- Protocolo de revisão humana em 2 passes: descrever como padrão genérico de
  "devolver para revisão antes de aplicar", com chaves neutras, OU mover para o
  `reference` do template se ficar amarrado demais ao contábil (decidir na
  implementação, preferindo manter o mínimo genérico útil no núcleo).
A frase de perfil contábil do CONSTRUTOR_PROMPT (181-183) é removida sem
substituto: já é coberta pela injeção condicional do perfil em run_construtor.

## Fluxo de dados

1. Tarefa chega (chat→orchestrate_turn, ou wizard).
2. `reference_for_task(task_text)` casa contra os templates.
3. Se casa extrato-dominio (score ≥ REF_LOW): injeta código few-shot + o texto
   `reference` (instruções contábeis) no contexto do agente.
4. Se não casa: contexto 100% genérico, zero contábil.
5. Geração segue como hoje.

## Critério de sucesso (verificável)

- `grep` por Domínio / "Inicia Lote" / aging / conciliação / crédito.débito nos
  TRÊS prompts retorna vazio.
- `test_extrato_dominio*` continuam verdes (requer as fixtures do e2e dentro do
  worktree; ver Riscos).
- Uma automação genérica ("somar uma coluna de um CSV") é gerada SEM nenhuma
  instrução contábil no contexto (inspecionar o contexto montado).
- Uma tarefa que casa extrato-dominio recebe o `reference` contábil injetado.
- Suíte inteira verde (exceto a falha pré-existente test_seed_heal, I4/B3).

## Riscos e mitigações

- **Fixtures do e2e ausentes no worktree** (`testes/dominio/` não veio no
  worktree): o `test_extrato_dominio_e2e` é pulado aqui. Mitigação: copiar as
  fixtures para dentro do worktree (ou rodar o e2e no checkout principal) para
  provar de verdade que o caso contábil continua funcionando. Sem isso, a
  garantia fica só nos testes unitário e positional, que são mais fracos.
- **Perda de documentação viva**: o prompt genérico era a única explicação do
  "porquê" das colunas do Domínio. Mitigação: o `reference` do template passa a
  ser essa documentação, perto do código que a implementa.
- **Interview genérico deixa de perguntar coisas contábeis cedo**: intencional
  (A1). A profundidade contábil vem no build (template reference) e no
  Classificador (enrich_accounting quando contabil=true).

## Fora de escopo (adiado)

- A2 (unificar os três pipelines num só). A1 apenas remove a dívida de conteúdo
  dos prompts; a duplicação de PIPELINE é A2.
- Generalizar o gate `contabil` para múltiplos domínios.
- Mover TEMPLATES para o banco (hoje é dict hardcoded; item próprio).
