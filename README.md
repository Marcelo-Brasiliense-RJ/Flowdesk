# FlowDesk

Plataforma low-code de automação de processos com IA integrada (inspirada no
Abstra), com identidade IRKO. O usuário descreve a automação em linguagem
natural no **Smart Chat**, a IA conduz uma entrevista e escreve o código Python,
o fluxo é montado num canvas visual (Form → Script → Form) e publicado como uma
aplicação web independente.

## Stack

- **Backend:** FastAPI + Python 3.11 · SQLAlchemy + SQLite · WebSocket nativo ·
  runtime de scripts em subprocesso isolado com fila asyncio · JWT.
- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS · Monaco Editor ·
  React Flow.
- **IA:** OpenAI API com streaming (override consciente do spec, que sugeria
  Anthropic). Cai em modo simulado se não houver `OPENAI_API_KEY`.

## Estrutura

```
flowdesk/
  back/                 FastAPI
    main.py             entrypoint (lifespan: cria tabelas, seed, runtime)
    app/
      models.py         modelos dos 10 módulos
      routers/          auth, projects, executions, builds, filemanager,
                        settings, chat, published, realtime
      runtime/runner.py fila FIFO + subprocesso + WebSocket
      services/         storage em disco, hub de WebSocket
      seed.py           org IRKO, 3 usuários, 2 projetos
    storage/            dados em disco por projeto (gitignored)
    qa_suite.py         suíte de testes de integração ponta-a-ponta
  front/                React + Vite
    src/pages/          Login, Console, Editor, WorkflowMonitor, Builds,
                        Logs, Files, AccessControl, ProjectSettings, PublishedApp
    src/components/     SmartChat, ProjectLayout, flowNodes, ui
```

## Como rodar

### Backend
```bash
cd back
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate no Unix)
pip install -r requirements.txt
copy .env.example .env            # e preencha OPENAI_API_KEY (opcional)
uvicorn main:app --reload         # http://127.0.0.1:8000
```
Na primeira execução o banco `flowdesk.db` é criado e populado com o seed.

### Frontend
```bash
cd front
npm install
npm run dev                       # http://localhost:5173 (proxy /api -> :8000)
```

## Acesso (seed)

- Console (admin): `admin@irko.com.br` / `flowdesk123`
- Outros usuários: `ana@irko.com.br`, `bruno@irko.com.br` (mesma senha)
- App publicado: login por SSO de domínio (`@irko.com.br`), só e-mail.

## Projeto de exemplo

**Conciliador de Planilhas** (`/app/conciliador`): workflow de 3 nós
`Form (upload) → Script (pandas) → Form (download)`, já publicado. Concilia duas
planilhas por uma chave comum e gera o relatório de divergências.

## Os 10 módulos

Console · Editor (Smart Chat + Monaco + Canvas) · Monitor em tempo real ·
Histórico de versões (builds) · Logs de execução · Sistema de arquivos ·
Controle de acesso · Configurações do projeto · Aplicação publicada ·
Runtime de execução.

## Testes

Suíte de integração que exercita todos os módulos contra o servidor real
(inclui runtime de subprocesso, WebSocket, segurança e o fluxo publicado):

```bash
# com o backend rodando em :8000
cd back
python qa_suite.py
```
Cria apenas projetos `QA …` e os remove ao final. Saída esperada:
`RESULTADO: 46/46 testes passaram`.

Verificações de tipo / build do frontend:
```bash
cd front
npx tsc --noEmit
npm run build
```

## Notas de runtime

- Cada Script roda em subprocesso Python isolado, com timeout configurável,
  stdout/stderr capturados e UUID por execução.
- As variáveis de ambiente do projeto (incluindo segredos preenchidos no Smart
  Chat via `require_env`) são injetadas no subprocesso.
- O SDK `flowdesk_sdk` (`get_input`, `set_output`, `output_path`, `log`) é
  injetado automaticamente em cada projeto.
