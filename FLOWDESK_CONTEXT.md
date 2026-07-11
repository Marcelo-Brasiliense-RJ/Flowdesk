# FLOWDESK_CONTEXT.md — Contexto Completo da Aplicação

> Estado **pós-refatoração** (atualizado em 2026-07-10). As mudanças de segurança
> (S1, S2, S4), identidade/escala (A1, A2, I1-I4, B1) e o loop de melhoria
> contínua (Treinador) já estão no código em `main`/`developer`. Resumo das
> mudanças no fim, seção "Estado da refatoração".

## Conceito
Plataforma low-code de automação de processos com IA integrada.
Inspirada no Abstra (abstra.io) mas com identidade própria.
O usuário descreve o que quer automatizar em linguagem natural,
a IA escreve o código, e o resultado vira uma aplicação web publicada.

**Premissa (importante):** o FlowDesk é uma plataforma GENÉRICA de automação. O
caso "extrato bancário para o Domínio" é apenas UM template da galeria, não o
núcleo. Os prompts centrais são genéricos; o conhecimento de um domínio (ex.:
contábil) vive no template e é carregado sob demanda (ver Módulo 12).

## O que é a Abstra (referência técnica)
Abstra (abstra.io) é a plataforma que inspirou o FlowDesk. Hoje ela se posiciona
como "Finance Automation Platform". Tecnicamente:
- Motor de workflow em Python: você escreve Python puro e a plataforma orquestra,
  hospeda e executa. Distribuída como pacote (`pip install abstra`); docs em
  docs.abstra.io.
- Um Workflow é uma sequência de Stages, e cada Stage é um script Python que faz
  um passo do processo. Tipos de Stage:
  - Form: script Python que gera uma página web interativa para coletar entrada do
    usuário e disparar lógica no backend.
  - Job: stage agendado (cron), roda periodicamente.
  - Hook: webhook, acionado por requisição HTTP no endpoint do stage.
  - Tasklet: script disparado por uma tarefa vinda de um stage anterior.
- Roda Python nativo com qualquer biblioteca (Pandas, Numpy, Requests, Matplotlib,
  Plotly) e oferece uploads de arquivo, agendamento cron, webhooks, formulários de UI
  para o usuário final e conectores (Slack, BigQuery, Gmail, Google Sheets, ERPs, S3).

### Como o FlowDesk se relaciona com a Abstra
- Mesmo modelo de Stages: o FlowDesk usa nós Form, Script, Job, Hook (e Agent) num
  workflow, análogo ao Form/Job/Hook/Tasklet da Abstra.
- SDK equivalente: o `flowdesk_sdk` (get_file, get_input, set_output, output_path,
  log, progress, read_table, get_table, extract_document) cumpre o papel do SDK da
  Abstra para I/O entre stages.
- Diferença central: na Abstra um desenvolvedor escreve o Python; no FlowDesk o Smart
  Chat (IA) escreve o Python a partir de linguagem natural, e a pessoa não técnica só
  aprova, testa e publica. FlowDesk = modelo de workflow no estilo Abstra somado a uma
  camada de IA que gera, ajusta e repara o código.

## Os Módulos do Sistema

### 1. Console (Painel Admin)
- Cards de projetos com nome, URL pública, badge "No ar" / "Rascunho"
- Organização por pastas/grupos com contador de projetos
- Menu: Projetos, Editores, Consumo de IA, AI Instructions, Criar pasta
- Botão "Novo projeto"

### 2. Editor de Projetos (3 painéis)
**Painel Esquerdo — Smart Chat com IA:**
- Chat conversacional para descrever a automação
- IA faz perguntas via radio buttons antes de escrever código
- Cada ação da IA tem botões "Aprovar" / "Rejeitar"
- Indicador de % do contexto da IA utilizado
- Campo de input com suporte a anexar arquivos (lidos via `read_table`/
  `extract_document`, tolerante a .xls legado — ver Módulo 12)
- "Modo reporte": ao chegar via `?report=<execution_id>`, fixa a execução como um
  card no chat e roteia a próxima mensagem para o reparador (ver Módulo 11)

**Painel Central — Editor de Código:**
- Explorador de arquivos do projeto
- Editor Monaco (VSCode) com syntax highlight Python
- Abas para navegar entre arquivos abertos

**Painel Direito — Canvas de Workflow:**
- Canvas com fundo pontilhado
- Nós arrastáveis (Form, Script, Job, Hook, Agent)
- Setas com label da variável passada entre nós
- Barra inferior com os 5 tipos de componentes

**Barra Superior:** nome, status, histórico de versões, "Salvar e Publicar"
**Rodapé:** abas Execuções | Tarefas

### 3. Workflow (Monitor em Tempo Real)
- Canvas do fluxo com nós e conexões
- Bolinhas coloridas por nó = últimas 5 execuções (sucesso, andamento, erro)
- Cada bolinha = link para o log da execução
- Barra de progresso + "X tarefas pendentes (Xm média)" no nó Script
- Atualização em tempo real via WebSocket

### 4. Histórico de Versões (Builds)
- Tabela: ID (hash 8 chars), Data, Versão do Framework, Status
- Status: "No ar" (verde), "Inativo" (cinza), "Falhou" (laranja)
- Menu por versão: Inspecionar, Ver logs, Baixar arquivos
- Cada "Salvar e Publicar" gera nova versão imutável

### 5. Logs de Execução
- Lista filtrável por: período, etapa, versão, status, ID de execução
- Cada linha expansível com stdout/stderr completo do Python (no app INTERNO)
- Paginação com 10 itens por página
- Obs.: no app PUBLICADO o stderr cru NÃO é exposto ao usuário final (ver Módulo 9)

### 6. Sistema de Arquivos
- Navegação por pastas com breadcrumb
- 3 pastas padrão: `_uploads/` (bruto por UUID), `uploads/` (organizado), `[output]/` (resultados)
- Tabela: Nome, Tamanho, Data modificação, checkbox
- Ações por arquivo: Renomear, Baixar, Excluir
- Botões: "+ Novo" e "Enviar" (upload manual)
- Paginação 20 itens/página
- Retenção: pastas `runs/<uuid>` antigas são limpas automaticamente (ver Módulo 10, I3)

### 7. Controle de Acesso
**Aba Usuários:**
- Política: "Apenas listados" OU "Todos do domínio @empresa.com"
- Tabela de usuários com e-mail e papéis atribuídos

**Aba Papéis:**
- Tabela de papéis com nome e descrição
- Papéis controlam o que o usuário vê na aplicação publicada

### 8. Configurações do Projeto (menu lateral)
- Tabelas (banco interno com CRUD visual)
- Arquivos
- Conectores (Google Sheets, APIs externas)
- Chaves de API
- Variáveis de Ambiente (valores ocultos por padrão)
- Subdomínio (URL pública da aplicação)
- Controle de Acesso

### 9. Aplicação Publicada (o que o usuário final acessa)
- URL própria por projeto
- Login integrado (SSO por domínio de e-mail). `PUBLIC_APPS_OPEN=false` por padrão
  (não abrir apps sem login em produção).
- Renderiza os Forms criados (upload, inputs, resultados)
- Executa Scripts em background ao submeter Form
- Redireciona automaticamente entre stages do workflow
- **Resposta sanitizada (S2/S4):** a tela de resultado NUNCA expõe o traceback cru
  nem o `input_data` (caminhos do servidor). Em erro, mostra só uma mensagem
  amigável (`_execution_public_view` em `published.py`); o traceback completo fica
  só nos logs internos. Download rejeita traversal na entrada (B4).
- Na tela de resultado, botão "Reportar problema" (visível só ao dono logado no app
  principal) leva ao Smart Chat com a execução fixada (ver Módulo 11)

### 10. Runtime de Execução dos Scripts
- Cada Script roda isolado. Dois backends, escolhidos por `EXECUTION_BACKEND`:
  - **`subprocess`** (default, on-premise): processo Python separado. **S1:** o
    subprocesso recebe apenas uma allowlist de variáveis de SO + as `EnvVar` do
    projeto, NUNCA o `os.environ` do servidor (não vaza `SECRET_KEY`,
    `OPENAI_API_KEY`, `SUPABASE_DB_URL`, `SMTP_*`). `PYTHONPATH` isolado ao src.
  - **`container`** (opt-in, alvo Linux): container efêmero por execução
    (`back/app/runtime/container.py`), imagem `flowdesk-runtime`. Isolamento:
    `--network=none`, FS read-only exceto os dirs montados, limites de CPU/mem/pids,
    usuário sem privilégio, `--cap-drop=ALL`, staging dos uploads. Precisa de host
    Linux + a imagem buildada (e validação de permissões de uid).
- Fila FIFO (`asyncio.Queue`) com 1 execução por vez (I1: teto conhecido; escala
  real = fila durável + workers, documentado em `runner._run_worker`).
- Logs capturados em tempo real (stdout + stderr); UUID por execução; retenção de
  `runs/` (I3, `run_retention_days`, default 30 dias).
- Variáveis de ambiente do projeto injetadas na execução (nunca as do servidor).

### 11. Reportar problema e auto-reparo (reparador)
Fecha o ciclo quando um teste falha OU dá "falso sucesso" (roda sem erro, mas o
resultado está errado).
- Entrada: botão "Reportar problema" na tela de resultado, disponível em erro e em
  sucesso, só para o dono logado.
- O botão leva ao Smart Chat com `?report=<execution_id>`. O chat fixa a execução num
  card (status, resumo/saída, trecho do log, arquivos de entrada) e a pessoa escreve
  só o que ficou errado.
- O reparador (`run_repair`) monta o contexto com o código atual, o `stderr` E o
  `output_data` da execução, o plano selado e os anexos, e chama a IA para
  diagnosticar e reescrever o script.
- A correção volta como ação aprovável `edit_file`; ao aprovar, aplica no script.
- **Alimenta a melhoria contínua:** ao propor a correção, o evento erro→correção é
  gravado (`treinador.record_repair`, best-effort) como sinal de treino (Módulo 13).
- Endpoints em `back/app/routers/repair.py`.

### 12. Pipeline de geração (unificado — A1/A2)
Como uma automação nasce a partir da linguagem natural:
- **Um único pipeline** (o orquestrador FSM): Planejador → (Classificador, só se o
  plano for `contabil`) → Construtor → Nomeador. O chat (`orchestrate_turn`) e o
  wizard (`_generate_script` → `_build_turn`) usam o MESMO caminho. O antigo
  monólito `_generate_build` foi removido (A2).
- **Prompts centrais GENÉRICOS (A1):** `SYSTEM_PROMPT`, `CONSTRUTOR_PROMPT` e o
  build turn não contêm mais conhecimento contábil (Domínio, Inicia Lote, aging,
  conciliação). Instrução genérica de automação: ler entrada, transformar, gravar
  saída via SDK.
- **Conhecimento de domínio sob demanda:** a galeria de templates
  (`back/app/routers/templates.py`) tem um campo `reference` por template com as
  regras daquele domínio. `reference_for_task` (`services/reference_code.py`) casa a
  tarefa com o template mais próximo e injeta código de referência (few-shot) +
  `reference` só quando casa (score >= limiar). Sem match, contexto 100% genérico.
- **Templates atuais:** `totais-planilha`, `conciliacao-planilhas`,
  `pdf-para-planilha`, `extrato-dominio` (extrato bancário → importação do Domínio,
  com todo o contábil no `reference`), `aging` (dias de atraso por faixa),
  `conciliacao-contabil` (débito×crédito).
- **SDK read_table portável (I2/B1):** lê xlsx/csv e .xls legado; no Windows usa
  Excel COM, no Linux usa LibreOffice headless (a imagem `flowdesk-runtime` já traz
  o LibreOffice). O contexto de anexos do chat usa `storage.read_table` (não
  `pd.read_excel` direto).

### 13. Treinador — melhoria contínua (auto-evolução dos agentes)
7º agente que faz o sistema melhorar sozinho, com aprovação humana. Tudo
best-effort, fora do caminho crítico (nunca quebra execução). Store em JSON em
`STORAGE_DIR/treinador/`.
- **Colheita:** ao uma automação publicada rodar com sucesso, um hook em
  `runner._schedule_harvest` (thread destacada) chama `treinador.harvest_project`:
  se validada (status live + sucesso recente), anonimiza o plano e guarda
  plano+código como exemplo.
- **Few-shot:** `examples_context` injeta os exemplos validados mais parecidos no
  contexto do Construtor.
- **Reparo:** eventos erro→correção gravados via `record_repair` (Módulo 11).
- **Destilação:** ao acumular ~10 exemplos novos, `maybe_distill` propõe um
  system prompt melhor por agente (status "pending").
- **Aprovação humana:** endpoints admin `GET/POST /api/ai/treinador/proposals`,
  `.../approve`, `.../reject`, `.../distill`; UI na página **Agentes** ("Melhoria
  contínua"), onde o admin aprova/rejeita a proposta. Aprovar aplica o prompt via
  `ai_config.apply_prompt`.

## Padrão de Workflow (Pipeline Padrão)
[Form: Upload] ──(var_nome)──▶ [Script: Processar] ──▶ [Form: Download]

## Projeto de Exemplo
Nome: "Conciliador de Planilhas"
Workflow: Form(upload xlsx) → Script(pandas conciliação) → Form(download resultado)

## Stack
- Backend: FastAPI + Python 3.11 + SQLAlchemy. **Banco:** Postgres/Supabase em
  produção (`SUPABASE_DB_URL`); SQLite local no dev quando vazio.
- **Migrações:** Alembic (`back/alembic/`, baseline a partir dos modelos). Deploy
  roda `alembic upgrade head`; o boot também faz `create_all` como rede de segurança.
- Frontend: React 18 + TypeScript + Tailwind CSS + Vite (servido por nginx).
- Realtime: WebSocket nativo FastAPI
- Editor: Monaco Editor · Canvas: React Flow
- IA: OpenAI (via SDK `openai`), streaming no chat; modelo configurável por agente
  (catálogo em `ai.py:MODEL_CATALOG`).
- Auth: JWT + login e-mail/senha. `SECRET_KEY` e `SEED_PASSWORD` vêm do ambiente
  (não há credencial hardcoded no código).
- Filas: `asyncio.Queue` (1 execução por vez — ver Módulo 10).

## Deploy / Infra
- **Easypanel** (num VPS Linux na Hostinger). Serviço tipo **Compose**
  (`docker-compose.yml`: `back` FastAPI + `front` nginx). Só o front tem domínio
  público (porta 80); ele faz proxy de `/api` e `/ws` para o back pela rede interna.
- Volume `flowdesk_storage` guarda uploads/outputs (sobrevive a redeploys).
- CI: push na branch de deploy dispara um webhook do Easypanel
  (`.github/workflows/deploy-homologacao.yml`).
- **Homologação:** `https://flow-desk-hml.irkorj.com.br` (banco no Supabase).
- Variáveis no ambiente do Easypanel (não em arquivo commitado): `OPENAI_API_KEY`,
  `SECRET_KEY`, `SEED_PASSWORD`, `SUPABASE_DB_URL`, `FRONTEND_ORIGIN`,
  `PUBLIC_APPS_OPEN`.

## Estado da refatoração (o que mudou, resumo)
- **P0 segurança:** S1 (env allowlist no subprocesso + sandbox de container opt-in),
  S2/S4 (app publicado sanitizado), S3 (senha seed não-hardcoded, vem do ambiente).
- **P1 identidade/escala:** A1 (prompts genéricos + conhecimento de domínio em
  template), A2 (pipeline único), I1 (teto de concorrência documentado), I2 (.xls
  portável via LibreOffice), I3 (retenção de disco), I4 (Alembic), B1 (anexos via
  read_table).
- **Melhoria contínua:** Treinador ligado (colheita, few-shot, reparo, destilação,
  aprovação na UI).
- **P2:** B4 (traversal no download), B5 (retry de import). Pendentes: B2 (marcar
  campos de arquivo no input), M4 (quebrar `chat.py` em serviço), M5/M6 (config e
  métricas no banco, testes de carga).
