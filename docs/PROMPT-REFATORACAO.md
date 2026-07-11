# Prompt de refatoração e ajuste do FlowDesk

Cole o bloco abaixo numa nova sessão do Claude Code, na raiz do repositório. Ele
foi escrito a partir do dossiê em `docs/DOSSIE-TECNICO.md`; leia o dossiê antes.

---

## PROMPT

Você vai conduzir a refatoração do FlowDesk descrita em
`docs/DOSSIE-TECNICO.md`. Leia esse dossiê inteiro antes de qualquer ação; ele é
a fonte da verdade sobre os problemas, a numeração (S1, I1, A1...) e as
prioridades (P0/P1/P2). Não confie na sua leitura do README para entender a
intenção do produto: a premissa correta está em A1.

### Premissa crítica (não negociável)

O FlowDesk é uma plataforma GENÉRICA de automação. O caso "extrato bancário para
o Domínio" foi apenas um caso de teste, NÃO o núcleo do produto. Todo o
conhecimento contábil que hoje vive nos prompts centrais é DÍVIDA a ser extraída
para um template, não requisito a preservar no núcleo. Nunca trate contabilidade
como a alma da plataforma.

### Skills que você deve usar (e quando)

- **superpowers:brainstorming**: ANTES de desenhar a unificação dos pipelines
  (A2) e a extração do domínio para template (A1). São decisões de design;
  levante intenção e alternativas antes de codar.
- **grill-me**: logo após o brainstorming, use para estressar as decisões de
  maior consequência antes de selar o plano: em A2, qual pipeline fica (o
  orquestrador FSM) e o que morre; em A1, como o template contábil é carregado
  sob demanda sem virar novo acoplamento; em I1, se a fila durável entra agora
  ou fica como teto documentado. Resolva cada galho antes de escrever o plano.
- **superpowers:writing-plans**: depois do brainstorming e do grill, escreva o
  plano por fases com checkpoints. Uma fase por vez.
- **superpowers:executing-plans** (ou **superpowers:subagent-driven-development**
  quando as tarefas forem independentes): é o motor de execução do plano, com
  checkpoints de revisão entre etapas. Não execute o plano "à mão"; conduza por
  ele.
- **karpathy-guidelines**: em todo o trabalho. Mudanças cirúrgicas, sem
  refatorar o que não foi pedido, sem abstração especulativa, cada linha
  rastreável ao objetivo.
- **ponytail** (modo full): em todo o trabalho. A solução mais simples que
  funciona. Especialmente relevante em A3 (não expandir o Treinador) e ao
  extrair domínio (mover, não reescrever).
- **superpowers:test-driven-development**: em cada correção com lógica não
  trivial. Teste que reproduz o problema primeiro, depois a correção.
- **superpowers:systematic-debugging**: nos bugs B1 a B5, antes de propor
  correção. Ache a causa-raiz, não o sintoma.
- **security-review**: obrigatória ao fechar cada item de segurança (S1 a S6) e
  ao final da fase P0.
- **superpowers:using-git-worktrees**: use um worktree isolado para este
  trabalho. Há outras sessões mexendo na árvore (ver Cuidados).
- **superpowers:verification-before-completion**: antes de declarar QUALQUER
  item pronto. Rode a verificação e mostre a saída; nunca afirme sucesso sem
  evidência.
- **verify** e **run**: para exercer o app de verdade (criar uma automação
  genérica ponta a ponta, publicar, executar), não só rodar testes.
- **superpowers:requesting-code-review** (ou o comando `/code-review`): ao final
  de cada fase.
- **napkin**: registre no runbook do repo os aprendizados recorrentes desta
  refatoração (comandos de teste, pegadinhas do runtime Windows, etc.).

### Cuidados inegociáveis

1. **Sessões concorrentes / WIP.** Há trabalho em andamento de outras sessões na
   árvore de trabalho. Trabalhe num git worktree próprio. Ao commitar, adicione
   SÓ os caminhos que você mesmo tocou, explicitamente. Nunca faça `git add -A`
   nem toque em WIP alheio.
2. **S1 é P0 e vem primeiro.** A correção barata (parar de passar
   `os.environ.copy()` ao subprocesso, mandar só as `EnvVar` do projeto) fecha o
   vazamento de segredos e deve ser o primeiro commit. O sandbox real
   (container efêmero) é maior e pode vir depois, mas planeje-o.
3. **Não quebre o caso contábil ao extrair o domínio.** A capacidade de fazer o
   extrato-Domínio deve continuar funcionando, agora via template/reference, não
   via prompt central. Os testes `test_extrato_dominio*` são o critério: eles
   têm que continuar verdes depois de A1.
4. **Não delete o Treinador (A3), congele.** É trabalho real. Pare de expandir
   (Tasks 6-12), não o remova.
5. **Preserve o que está bom.** Não "simplifique" `services/ai_call.py`,
   `services/ai_guard.py`, nem a contagem de arquivos por AST em `chat.py`. Ver
   seção 8 do dossiê.
6. **Windows on-premise vs Linux (I2).** Ao desacoplar do Excel COM, mantenha o
   caminho antigo funcionando enquanto o novo não estiver validado. Não deixe a
   máquina on-premise sem conversão de `.xls` no meio da transição.
7. **Migrações (I4).** Ao adotar Alembic, gere a baseline a partir do schema
   atual (não recrie o banco). Bancos existentes (SQLite e o Postgres/Supabase)
   não podem perder dados.
8. **Compatibilidade de dados.** `plan`, `accounting_profile`, `wizard_state` e
   os JSON em `storage/` já existem em bancos reais. Nenhuma mudança pode exigir
   apagar dados de projeto para o app subir.
9. **Rotação da senha seed (S3)** é operação de banco, não de código. Sinalize
   ao responsável; não invente credencial nova no código.

### Objetivos por fase, com critério de sucesso verificável

Execute em ordem. Não comece uma fase sem a anterior verificada e revisada.

**Fase P0, segurança que bloqueia produção**
- S1 (parte barata): o subprocesso recebe apenas as `EnvVar` do projeto, nunca o
  ambiente do servidor.
  - Verificar: teste que executa um script tentando ler `SECRET_KEY`/
    `OPENAI_API_KEY` do ambiente e confirma que NÃO estão visíveis; a suíte
    existente continua verde.
- S1 (sandbox real): plano escrito e primeira etapa implementada (rede off por
  padrão, FS read-only exceto `run_dir`, limites de CPU/mem).
  - Verificar: um script que tenta abrir conexão de rede ou escrever fora de
    `run_dir` falha de forma controlada.
- security-review da fase sem achados abertos de severidade alta.

**Fase P1, identidade e escala**
- A1: os três prompts centrais não contêm mais conhecimento contábil; ele vive
  num template carregado sob demanda.
  - Verificar: `grep` por Domínio/`Inicia Lote`/aging/conciliação nos três
    prompts retorna vazio; `test_extrato_dominio*` continua verde; uma automação
    genérica (ex.: "somar coluna de um CSV") é gerada sem instrução contábil no
    contexto.
- A2: um único pipeline de geração; chat e wizard passam a alimentá-lo.
  - Verificar: `_generate_build`/`SYSTEM_PROMPT` monolítico removido ou reduzido
    a fino adaptador; toda a suíte verde; app exercido ponta a ponta com `verify`.
- S2, S4: app publicado não devolve `stderr` cru nem `input_data`.
  - Verificar: teste do endpoint publicado confirma resposta sanitizada.
- I2: conversão de `.xls` portável (sem Excel COM) disponível, com o caminho
  Windows preservado como fallback.
  - Verificar: leitura de um `.xls` legado num ambiente sem Excel.
- I1: fila de execução com teto documentado ou movida para backend durável
  (decida no brainstorming qual escopo cabe agora).
- I3: retenção/limpeza de `runs/` e `_uploads/` e cota por projeto.
- I4: Alembic adotado, baseline a partir do schema atual, migração roda como
  passo de deploy.
- B1: leitura de anexos via `read_table`/`extract_document`.

**Fase P2, qualidade de longo prazo**
- A3: Treinador congelado e documentado como tal.
- M4: lógica de workflow extraída de `chat.py` para um serviço testável.
- M5, I6: config de IA/Treinador e métricas migradas para o banco.
- B2, B4, B5: heurísticas frágeis endurecidas.
- M6: testes de carga/concorrência mínimos.

### Regras de execução

- Um objetivo por vez. Não abra frente nova sem a anterior verde e revisada.
- Todo item com lógica não trivial nasce de um teste (TDD).
- Antes de dizer "pronto", rode a verificação e cole a saída
  (verification-before-completion). Sem evidência, não está pronto.
- Ao final de cada fase: `/code-review` e, para as fases P0/P1, `security-review`.
- Commits pequenos, mensagem no padrão do repo, apenas os caminhos que você
  tocou. Só commite/push quando pedido.
- Se algum ponto do dossiê estiver desatualizado em relação ao código real que
  você encontrar, PARE e reporte a divergência antes de agir; não presuma.

### Definição de pronto (global)

- Fase P0: segredos do servidor inacessíveis ao script; security-review limpa.
- Fase P1: prompts centrais genéricos, pipeline único, app genérico funcionando
  ponta a ponta, caso contábil ainda funcionando via template, suíte verde.
- Fase P2: itens de manutenibilidade fechados ou explicitamente adiados com
  justificativa registrada no napkin.
