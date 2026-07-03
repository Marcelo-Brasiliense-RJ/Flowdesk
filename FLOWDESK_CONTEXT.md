# FLOWDESK_CONTEXT.md — Contexto Completo da Aplicação

## Conceito
Plataforma low-code de automação de processos com IA integrada.
Inspirada no Abstra (abstra.io) mas com identidade própria.
O usuário descreve o que quer automatizar em linguagem natural,
a IA escreve o código, e o resultado vira uma aplicação web publicada.

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
  log, progress) cumpre o papel do SDK da Abstra para I/O entre stages.
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
- Campo de input com suporte a anexar arquivos
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
- Bolinhas coloridas por nó = últimas 5 execuções (🟢 sucesso, 🟡 andamento, 🔴 erro)
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
- Cada linha expansível com stdout/stderr completo do Python
- Paginação com 10 itens por página

### 6. Sistema de Arquivos
- Navegação por pastas com breadcrumb
- 3 pastas padrão: `_uploads/` (bruto por UUID), `uploads/` (organizado), `[output]/` (resultados)
- Tabela: Nome, Tamanho, Data modificação, checkbox
- Ações por arquivo: Renomear, Baixar, Excluir
- Botões: "+ Novo" e "Enviar" (upload manual)
- Paginação 20 itens/página

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
- Login integrado (SSO por domínio de e-mail)
- Renderiza os Forms criados (upload, inputs, resultados)
- Executa Scripts em background ao submeter Form
- Redireciona automaticamente entre stages do workflow
- Na tela de resultado, botão "Reportar problema" (visível só ao dono logado no app
  principal) leva ao Smart Chat com a execução fixada (ver Módulo 11)

### 10. Runtime de Execução dos Scripts
- Cada Script roda em processo Python isolado (subprocess)
- Fila FIFO com processamento em background
- Logs capturados em tempo real (stdout + stderr)
- UUID único por execução
- Arquivos salvos em `_uploads/[uuid]/`
- Variáveis de ambiente injetadas no subprocesso

### 11. Reportar problema e auto-reparo (reparador)
Fecha o ciclo quando um teste falha OU dá "falso sucesso" (roda sem erro, mas o
resultado está errado).
- Entrada: botão "Reportar problema" na tela de resultado (teste do Wizard e app
  publicado), disponível em erro e em sucesso, só para o dono logado.
- O botão leva ao Smart Chat com `?report=<execution_id>`. O chat fixa a execução num
  card (status, resumo/saída, trecho do log, arquivos de entrada) e a pessoa escreve
  só o que ficou errado.
- O reparador (`run_repair`) monta o contexto com o código atual, o `stderr` E o
  `output_data` da execução (o output é o único sinal no falso sucesso), o plano
  selado e os anexos, e chama a IA para diagnosticar e reescrever o script.
- A correção volta como uma ação aprovável `edit_file`; ao aprovar, aplica no script
  (reusa o fluxo de PendingAction, que também re-sincroniza os campos de arquivo do
  Form) e a pessoa re-testa.
- Endpoints: `POST /projects/{id}/chat/report` (fixa) e
  `POST /projects/{id}/chat/report-repair` (roda o reparador e cria a ação), em
  `back/app/routers/repair.py`.
- Escopo: o reparador só edita o script Python da automação. Bugs de plataforma/
  renderização (frontend) não são corrigidos por aqui.

## Padrão de Workflow (Pipeline Padrão)
[Form: Upload] ──(var_nome)──▶ [Script: Processar] ──▶ [Form: Download]
## Projeto de Exemplo a Criar
Nome: "Conciliador de Planilhas"
Workflow: Form(upload xlsx) → Script(pandas conciliação) → Form(download resultado)
Usuários seed: 3 usuários com papéis User e Dev

## Stack (seguir CLAUDE.md — se não estiver lá, usar):
- Backend: FastAPI + Python 3.11 + SQLAlchemy (SQLite local por padrão; Postgres/Supabase quando `SUPABASE_DB_URL`/`DATABASE_URL` estão setados)
- Frontend: React 18 + TypeScript + Tailwind CSS + Vite
- Realtime: WebSocket nativo FastAPI
- Editor: Monaco Editor
- Canvas: React Flow
- IA: OpenAI (modelo `gpt-4o-mini` por padrão, via SDK `openai`) com streaming no chat; modelo configurável por agente
- Auth: JWT + login e-mail/senha
- Filas: asyncio.Queue