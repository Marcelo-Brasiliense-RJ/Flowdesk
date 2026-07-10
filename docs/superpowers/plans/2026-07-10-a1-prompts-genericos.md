# A1: Prompts genéricos + contábil sob demanda — Plano

> Executado inline com TDD (superpowers:test-driven-development). Spec:
> docs/superpowers/specs/2026-07-10-a1-prompts-genericos-design.md

**Goal:** os três prompts centrais ficam genéricos; o conhecimento contábil vai
para um campo `reference` do template extrato-dominio, injetado sob demanda pelo
`reference_for_task` que já existe.

**Ordem (o lar do contábil nasce ANTES de sair dos prompts, sem janela de perda):**

## Global Constraints
- `test_extrato_dominio*` verde ao final (trazer fixtures do e2e para o worktree).
- grep por Domínio/Inicia Lote/aging/conciliação/crédito.débito nos 3 prompts = vazio.
- Mover, não reescrever (o texto contábil migra ~verbatim para o reference).
- Sem novo módulo/dependência: só dado (campo reference) + reuso da injeção.
- Commits pequenos, só caminhos tocados, padrão do repo.

## Task 1 — reference_for_task devolve o `reference`
- Files: back/app/services/reference_code.py; test: back/tests/test_reference_code.py (estender).
- TDD: teste que um template com campo `reference` faz `reference_for_task` retornar esse texto (e string vazia quando ausente).
- Impl: `best` passa a incluir `"reference": tpl.get("reference", "")`.

## Task 2 — injetar o `reference` no contexto (run_construtor + wizard)
- Files: back/app/routers/orchestrator.py (run_construtor ~215-222); back/app/routers/wizard.py (_generate_script ~198-204).
- Test: back/tests/test_construtor_reference.py (estender) — quando o ref casa e tem reference, o bloco de instruções entra nas messages/blocks.
- Impl: após o bloco de código de referência, se `ref.get("reference")`, anexar bloco "REGRAS DO DOMÍNIO (quando aplicável):\n{reference}". Nos dois sites (duplicação é dívida de A2, não mexer além disso).

## Task 3 — popular extrato-dominio.reference com o contábil (movido dos prompts)
- Files: back/app/routers/templates.py (entrada extrato-dominio).
- Conteúdo movido ~verbatim: contrato de colunas do Domínio, Inicia Lote, convenção débito/crédito, plano de contas com cabeçalho deslocado, convenções regras_classificacao/_CONTA_BANCO, protocolo de revisão em 2 passes (chaves _classificacao_review/_classificacao_confirmada/_conta_banco/_periodo).
- Test: back/tests/test_templates.py (ou novo) — extrato-dominio tem `reference` não vazio contendo "Inicia Lote" e "regras_classificacao".

## Task 4 — SYSTEM_PROMPT genérico (chat.py)
- Files: back/app/routers/chat.py (SYSTEM_PROMPT ~45-185).
- Remover blocos contábeis: L72-76, L83-106, L180-185. Reescrever neutro: pdfplumber posicional (colunas neutras), revisão em 2 passes (chaves neutras) — manter a técnica genérica.
- Test: grep no SYSTEM_PROMPT sem Domínio/Inicia Lote/aging/conciliação.

## Task 5 — CONSTRUTOR_PROMPT genérico (orchestrator.py)
- Files: back/app/routers/orchestrator.py (CONSTRUTOR_PROMPT ~165-187).
- Remover L173-175 (exemplo extrato/razão) e L181-183 (frase perfil contábil, redundante com injeção condicional).

## Task 6 — _generate_build instr genérico (chat.py)
- Files: back/app/routers/chat.py (_generate_build instr ~524-526).
- Reescrever o trecho de extrato PDF com colunas neutras (técnica pdfplumber genérica).

## Task 7 — Verificação
- Trazer fixtures testes/dominio/ para o worktree (NÃO commitar — dado confidencial de cliente).
- grep dos 3 prompts limpo (evidência).
- Suíte inteira verde; test_extrato_dominio* verde (incl. e2e com fixtures).
- Automação genérica ("somar coluna de CSV") gerada sem contábil no contexto (inspecionar contexto).
- security-review não se aplica (sem superfície de segurança nova); /code-review ao final.
