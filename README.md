# FlowDesk

Plataforma low-code **genérica** de automação de processos com IA integrada
(inspirada no Abstra), com identidade IRKO. O usuário descreve a automação em
linguagem natural no **Smart Chat**, a IA conduz uma entrevista e escreve o
código Python, o fluxo é montado num canvas visual (Form → Script → Form) e
publicado como uma aplicação web independente.

> **Premissa:** o núcleo é genérico. Conhecimento de um domínio específico (ex.:
> contábil / extrato bancário → Domínio) vive num **template da galeria** e é
> carregado sob demanda, não nos prompts centrais.

## Stack

- **Backend:** FastAPI + Python 3.11 · SQLAlchemy · WebSocket nativo · JWT.
  - **Banco:** Postgres/Supabase em produção (`SUPABASE_DB_URL`); SQLite local no
    dev quando não configurado. Migrações com **Alembic**.
  - **Runtime de scripts:** fila `asyncio` (1 execução por vez) + execução isolada.
    Dois backends via `EXECUTION_BACKEND`: `subprocess` (default, on-premise, com
    allowlist de env — não vaza segredos do servidor) e `container` (opt-in,
    container efêmero por execução: rede off, FS read-only, limites, sem privilégio).
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
      models.py         modelos do domínio
      routers/          auth, projects, executions, builds, filemanager,
                        settings, chat, published, orchestrator, repair, ai,
                        templates, classify, wizard, realtime
      runtime/
        runner.py       fila FIFO + execução isolada + WebSocket + hook de colheita
        container.py    sandbox de execução em container (opt-in)
      services/
        storage.py      storage em disco + read_table portável (.xls sem Excel COM)
        reference_code.py  casa a tarefa com o template e injeta código+regras
        treinador.py    melhoria contínua (colheita, few-shot, destilação)
        ai_config.py    prompt/modelo por agente
      seed.py           org IRKO + usuários + projeto de exemplo (senha via env)
    alembic/            migrações (baseline a partir dos modelos)
    runtime-image/      Dockerfile da imagem do sandbox (flowdesk-runtime)
    tests/              suíte pytest
  front/                React + Vite (build servido por nginx)
  docker-compose.yml    stack para EasyPanel (back + front)
```

## Como rodar (dev)

### Backend
```bash
cd back
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate no Unix)
pip install -r requirements.txt
copy .env.example .env            # preencha as variáveis (abaixo)
uvicorn main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app   # ou .\run-dev.ps1
```

Variáveis do `.env` (nunca commite o `.env` real):
- `OPENAI_API_KEY` — sem ela a IA roda em modo simulado.
- `SECRET_KEY` — assina os JWT; use uma string longa e aleatória.
- `SEED_PASSWORD` — senha dos usuários do seed inicial (obrigatória no 1º seed).
- `SUPABASE_DB_URL` — Postgres/Supabase; vazio = SQLite local.

Migração de schema (produção e sempre que os modelos mudarem):
```bash
cd back
alembic upgrade head
```
No dev com SQLite, o `lifespan` também cria as tabelas no primeiro boot.

> **Use `--reload-dir app`, nunca `--reload` sozinho.** O runtime regrava o script
> `.py` de cada projeto a cada execução; o `--reload` padrão observa tudo, vê esse
> `.py` e reinicia o servidor no meio da execução. Restringir o watch a `app/`
> recarrega o backend sem enxergar o código materializado. Editou `main.py` (fora de
> `app/`)? Reinicie (ou rode `.\run-dev.ps1`).

### Frontend
```bash
cd front
npm install
npm run dev                       # http://localhost:5173 (proxy /api -> :8000)
```

## Acesso (seed)

O seed cria a organização IRKO e usuários de exemplo (um admin e demais). As
credenciais NÃO são versionadas: a senha vem de `SEED_PASSWORD` no ambiente.
- App publicado: login por SSO de domínio, só e-mail.

## Geração de automação e melhoria contínua

- **Pipeline único** (orquestrador): Planejador → (Classificador, só quando o plano
  é contábil) → Construtor → Nomeador. Chat e wizard usam o mesmo caminho.
- **Prompts genéricos + domínio sob demanda:** os prompts centrais não têm regra de
  negócio de domínio; `reference_for_task` injeta o código de referência e as regras
  do template só quando a tarefa casa com ele (galeria em `routers/templates.py`).
- **Treinador (auto-evolução):** automações publicadas e validadas viram exemplos
  (few-shot); erros→correções viram lições; ao acumular exemplos, o sistema propõe
  prompts melhores para aprovação humana na página **Agentes → Melhoria contínua**.
  Tudo best-effort, fora do caminho crítico.

## Deploy

- **EasyPanel** num VPS Linux (serviço tipo **Compose**, `docker-compose.yml`:
  `back` FastAPI + `front` nginx). Só o front tem domínio público (porta 80) e faz
  proxy de `/api` e `/ws` para o back.
- Banco no **Supabase** (Postgres). Variáveis no ambiente do EasyPanel, não em
  arquivo commitado: `OPENAI_API_KEY`, `SECRET_KEY`, `SEED_PASSWORD`,
  `SUPABASE_DB_URL`, `FRONTEND_ORIGIN`, `PUBLIC_APPS_OPEN`.
- Homologação: `https://flow-desk-hml.irkorj.com.br`.
- Sandbox de execução (`EXECUTION_BACKEND=container`) exige host Linux + a imagem
  `flowdesk-runtime` buildada (`docker build -t flowdesk-runtime:latest back/runtime-image`).

## Testes

```bash
cd back
python -m pytest -q                # suíte de unidade/integração
```
Ponta-a-ponta contra o servidor real (opcional, com o backend rodando):
```bash
python qa_suite.py                 # cria apenas projetos "QA …" e os remove ao final
```
Frontend:
```bash
cd front
npx tsc --noEmit && npm run build
```

## Notas de runtime e segurança

- Execução isolada com timeout, stdout/stderr capturados e UUID por execução.
- **Segredos do servidor não vazam** para o script: o subprocesso recebe apenas uma
  allowlist de env de SO + as `EnvVar` do projeto. O app publicado NÃO devolve
  traceback cru nem caminhos de arquivo do servidor.
- Retenção: pastas de execução antigas (`runs/`) são limpas (`run_retention_days`).
- O SDK `flowdesk_sdk` (`get_file`, `get_input`, `set_output`, `output_path`, `log`,
  `progress`, `read_table`, `get_table`, `extract_document`) é injetado em cada projeto.
