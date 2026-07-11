# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

## FlowDesk — contexto do projeto e acordo de trabalho

**O que é:** plataforma low-code GENÉRICA de automação com IA (estilo Abstra). O
usuário descreve em linguagem natural, a IA gera o Python e publica como app web.
O caso contábil (extrato bancário → Domínio) é só UM template da galeria, não o
núcleo. Conhecimento de domínio vive no `reference` do template, carregado sob
demanda; os prompts centrais são genéricos. Contexto completo: `FLOWDESK_CONTEXT.md`.

**Stack / infra:**
- Backend FastAPI + SQLAlchemy. Banco: Postgres/Supabase em produção, SQLite no dev.
- Migrações: Alembic (`back/alembic/`); no deploy roda `alembic upgrade head`.
- Frontend React + Vite (servido por nginx). IA: OpenAI.
- Deploy: **EasyPanel** num VPS Linux (Hostinger), serviço tipo Compose
  (`docker-compose.yml`: back + front). Homologação:
  `https://flow-desk-hml.irkorj.com.br`. Banco no Supabase.

**Git — modelo de 2 branches:** só `developer` (integração) e `main` (estável).
Dois remotes espelho: `irko` (oficial, IRKO-Rio-de-janeiro/Flow-Desk) e `origin`
(pessoal). Tudo converge nas duas. Trabalhar em worktree isolado; commitar só os
caminhos que você tocou (nunca `git add -A`, nunca tocar WIP alheio sem mandar).
Ao terminar: merge → `main` nas duas → apagar a branch/worktree.

**Como o usuário quer que eu trabalhe:**
- Rápido e enxuto. Respostas curtas, linguagem simples, sem paredes de texto.
- Decidir sozinho o razoável e seguir; perguntar só quando muda o rumo. Consolidar
  várias decisões de uma vez.
- Executar e mostrar resultado (código, commits, deploy quando pedido), não narrar.
- Qualidade não se corta: TDD no que tem lógica, verificação real antes de dizer
  "pronto", honestidade analítica (apontar risco/falha, não concordar por padrão).
- Autorização permanente de commit/push nas duas developers ao fim de cada item;
  parar só em bloqueio técnico real ou ação irreversível de PRODUÇÃO (deploy,
  migração de banco, delete em prod ainda pedem confirmação).

**Pegadinhas / lições:**
- NUNCA coloque `SUPABASE_DB_URL` (nem qualquer banco de PRODUÇÃO) no `.env` LOCAL:
  os testes usam o engine do app e passam a rodar contra a produção — testes
  destrutivos (ex.: bulk_delete) apagam dados reais. A URL de produção vive só no
  ambiente do EasyPanel. Dev/testes usam SQLite.
- Rodar a suíte a partir de `back/`: `& ..\back\.venv\Scripts\python.exe -m pytest -q`.
  Os testes de container (`test_container_run`) e o e2e do extrato dependem de
  Docker/fixtures; `--ignore` deles quando o Docker estiver indisponível.
- `git` não está no PATH do bash aqui; use PowerShell para git.
- uvicorn: `--reload-dir app`, nunca `--reload` sozinho (o runtime regrava `.py` e
  reiniciaria o servidor no meio da execução).
- Seed exige `SEED_PASSWORD` no ambiente; senha seed não é hardcoded.
- Sandbox de execução (`EXECUTION_BACKEND=container`) é opt-in, só roda em Linux com
  a imagem `flowdesk-runtime` buildada; default é `subprocess`.
- Segurança: a execução nunca recebe os segredos do servidor; o app publicado não
  devolve stderr cru nem caminhos de arquivo.
