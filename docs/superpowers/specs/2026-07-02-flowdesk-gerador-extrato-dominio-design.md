# Conserto do gerador: extrato bancário PDF para planilha do Domínio

Data: 2026-07-02
Status: aprovado (design)
Escopo: caminho do gerador do Wizard + runner compartilhado. Backend apenas.

## Problema

A partir de um pedido em linguagem natural mais três arquivos (extrato PDF, plano
de contas, modelo de importação), o Wizard entende a tarefa mas gera uma automação
incompleta. O objetivo é corrigir o GERADOR, não escrever um script avulso.

## Causa-raiz

Existem dois geradores no FlowDesk e eles divergiram:

1. Caminho do Chat: `chat_stream` -> `orchestrate_turn` -> `run_construtor`
   (orchestrator.py). Já injeta o código de referência da galeria via
   `reference_code.reference_for_task` e semeia o oráculo verbatim quando o
   casamento é claro (`score >= REF_HIGH`, via `_seed_primary_script`).

2. Caminho do Wizard: `build_from_wizard` -> `_generate_script` -> `_generate_build`
   (wizard.py, chat.py). NÃO injeta referência. Monta um intent magro
   (`"Tarefa: ... Entrada: file. Saída: download"`) mais o SYSTEM_PROMPT mais as
   colunas de um único `sample_file`.

O teste E2E que falhou (projeto 105) usa o Wizard. Além disso, o Form de entrada é
dimensionado contando `get_file()` no código já gerado (`_input_fields` ->
`_count_input_files`), o que é circular: o código usa 1 arquivo porque nunca foi
avisado que havia 3, então o Form nasce com 1 campo.

## Sintomas mapeados à causa

1. Três arquivos viram um. `analyze` deduz os arquivos só em prosa (`summary`,
   `process`), nunca em campo estruturado. `input` carrega só `kind` e `fields`.
   O intent passa só `inp.kind`. Form dimensionado circularmente pelo código.
2. Classificação vazia (`get_table('regras_classificacao')` em vez de ler o
   Contas.xlsx). O Wizard não injeta o oráculo (que tem `carregar_plano`). Sem ele,
   o modelo cai no hint genérico do SYSTEM_PROMPT sobre `get_table`. E só vê um
   anexo, sem papel identificado.
3. Só a fase 1 (review) é construída. O intent diz "download -> arquivo_resultado",
   não descreve o contrato de 2 passes. Sem o oráculo, o modelo escreve só o pass 1.
4. `error=null`. Em falha dura, `output.json` não existe, então `output_data={}`;
   o runner grava `status=error` e `stderr` mas nenhuma mensagem legível.
   `ExecutionOut` nem tem campo `error`; o app publicado devolve só `stderr` cru.
5. `get_file()` pega o arquivo errado. O SDK `get_file()` sem argumento retorna
   `paths[0]` (ordem do dict). O oráculo já usa `get_file(0/1)` posicional; o
   gerador precisa ser instruído a fazer igual e o Form precisa gravar os campos na
   ordem dos papéis.

Observação chave: como a semente do oráculo substitui o script verbatim, e o Form
conta `get_file` do código final, injetar a referência no Wizard já corrige 2, 3, 5
e boa parte de 1 de uma vez. A propagação estruturada dos papéis generaliza para
além desse template e fecha o 1 por completo.

## Decisões (aprovadas)

1. Tamanho do Form quando `analyze` deduz N arquivos mas o código lê M (M < N):
   `max(plano, código)`. O usuário anexa os N que foi instruído a anexar; o
   arquivo não lido (ex.: modelo) fica como upload ignorado.
2. Canal de erro: reusar `output_data['erro']`. Sem novo campo, sem migração, sem
   mudança de front. Mesma convenção do oráculo (`set_output({'erro': ...})`), já
   exibida pelo app publicado e pelo ReportCard.
3. Escopo: Wizard mais runner compartilhado. O chat já injeta referência e semeia;
   só herda a instrução compartilhada de `get_file(0..n)` posicional.

## Mudanças

Todas backend, cirúrgicas. Sem migração de banco, sem dependência nova, sem
reescrever o chat.

### A. `analyze` emite o plano de arquivos estruturado
Arquivo: wizard.py, `_ANALYZE_INSTR` mais os fallbacks (com IA e sem IA).
Quando `input.kind == "file"`, o plano ganha
`input.files = [{role, label, hint}]`, na ordem em que o código deve ler
(`get_file(0)`, `get_file(1)`, ...). Fallback sem IA: um arquivo genérico
(compatibilidade). Round-trip: o setter genérico `PUT wizard_state = body.state`
(projects.py) grava verbatim, então `files` sobrevive de analyze a build. O build
não depende só disso (ver fallback em B).

### B. `build`/`_generate_script` herda referência mais plano de arquivos
Arquivo: wizard.py, `_generate_script`.
- Injeta a referência igual ao chat: `reference_for_task(process mais contexto dos
  anexos)`; `>= REF_LOW` vira bloco few-shot "adapte, não reescreva"; `>= REF_HIGH`
  semeia o script verbatim (reusa `_seed_primary_script`).
- Monta a seção de arquivos do intent a partir de `ws["input"]["files"]`
  (preferido), com fallback para o número de anexos presentes: enumerar os N
  arquivos na ordem, instruir `get_file(0..n)` posicional, e mandar LER cada
  arquivo anexado (o plano de contas é lido do arquivo, não de `get_table`).
- Contexto de anexos para todos os arquivos (rotulados por papel), não só um
  `sample_file`.

### C. Form dimensionado por `max(plano, código)`
Arquivo: wizard.py, `_input_fields` (e o helper em chat.py se necessário).
`n = max(len(plan.files), _count_input_files(code))`. Rótulos: papéis do plano na
ordem, senão os derivados do código (`_file_labels_from_code`), senão "Arquivo N".
Nomes `arquivo1..N` na ordem do plano, então `get_file(i)` mapeia ao papel i.

### D. Coerência output.kind com o código
Arquivo: wizard.py.
Com `out_kind == "download"`, o código gerado tem que conter um caminho que grava
`arquivo_resultado`. O oráculo de 2 passes satisfaz (pass 2 grava). Guarda leve: se
faltar, registrar com comentário `ponytail:` de teto conhecido, sem regeneração
automática (fora do mínimo). O fix real do sintoma 3 é a injeção da referência
(ambos os passes passam a existir).

### E. Runner: erro legível (reusa `output_data['erro']`)
Arquivo: runner.py, no ponto de montagem do `output_data` e em `_fail_silently`.
Em `status == "error"` sem `erro` nem `arquivo_resultado` no output, definir
`output_data["erro"] = <última linha útil do stderr>` (a exceção real). Flui pelo
canal `erro` que o app publicado e o ReportCard já exibem.

## Testes (TDD, determinístico, sem OpenAI ao vivo)

Fixtures em `testes/dominio/`: extrato PDF (JBB GIG BRADESCO 04.2026), Contas.xlsx,
modelo .xlsm, resultado esperado, e o oráculo `extrato_bradesco_para_dominio.CORRIGIDO.py`.

- Plumbing (unit):
  - `analyze` emite `input.files` (testar ao menos o fallback sem IA e a forma).
  - `_generate_script` injeta ou semeia a referência no caso extrato-domínio
    (asserção sobre as mensagens montadas ou o código semeado).
  - `_input_fields` devolve `max(plano, código)` com rótulos e ordem do plano.
- Runtime E2E contra as fixtures reais (portão de aceite): forçar a semente, então
  o script gerado é o oráculo; materializar e rodar pelo runtime com os três
  arquivos:
  - Pass 1 devolve `_classificacao_review` com `contas` não vazio (leu Contas.xlsx)
    e `grupos`.
  - Pass 2 (`_classificacao_confirmada`) gera `arquivo_resultado`, e o xlsx tem
    linhas.
  - PDF inválido devolve `output_data["erro"]` legível (fix do runner).
- Rodar `back/tests/` inteiro, sem regressão (Conciliador e demais seeds).
- Fim: `/verify` no app real (fluxo do projeto 105) com IA ao vivo.

Os testes e o E2E rodam contra o banco local de teste (SQLite fallback), nunca
contra o Postgres/Supabase de produção.

## Critério de aceite

A partir SOMENTE do prompt em linguagem natural mais os três arquivos anexados, a
automação gerada deve, de ponta a ponta: extrair os lançamentos do PDF, classificar
usando o Contas.xlsx, e produzir um `arquivo_resultado` no layout de importação do
Domínio, disponível para download. Um erro de insumo (ex.: PDF inválido) deve
retornar mensagem legível, não `error=null`.

## Fora de escopo

Migração ou mudança de schema de banco; reescrita do caminho do chat; dependência
nova. O chat só herda a instrução compartilhada de `get_file(0..n)` posicional. Não
quebrar os projetos seed existentes.
