# Dossiê Técnico do FlowDesk

Avaliação de arquitetura, segurança, infraestrutura, escalabilidade e
manutenibilidade, com o objetivo de transformar o FlowDesk numa plataforma
robusta e eficaz. Baseado em leitura de código (não em execução da suíte).
Data: 2026-07-09.

Convenção de prioridade:
- **P0**: bloqueia produção séria (segurança grave ou perda de dados).
- **P1**: teto de escala ou dívida que já dói, resolver antes de crescer.
- **P2**: manutenibilidade e qualidade de longo prazo.

---

## 1. Sumário executivo (o veredito)

O FlowDesk tem uma base de engenharia acima da média para um MVP: camada única
de IA bem justificada, blindagem de prompt injection na fronteira dos dados,
parsing por AST onde regex não bastaria, e testes amplos. O potencial é real.

O que o impede de "encaixar" são três problemas estruturais, em ordem de impacto:

1. **Um caso de teste virou o núcleo, por acidente.** O extrato-Domínio era
   apenas UM cenário de teste de uma aplicação, não a alma da plataforma. Mas o
   conhecimento contábil desse teste vazou para dentro dos prompts centrais
   (`SYSTEM_PROMPT`, `CONSTRUTOR_PROMPT`, `_generate_build`) e hoje sufoca a
   genericidade que era o verdadeiro objetivo. A plataforma genérica está sendo
   estrangulada por um fixture de teste que colonizou o código.
2. **Execução de código arbitrário sem sandbox real.** O maior risco de
   segurança do projeto. Código gerado por IA (e editável) roda com os segredos
   e privilégios do servidor. Para dados de clientes IRKO, é inaceitável em
   produção como está.
3. **Monólito de processo único por design.** Fila de execução, rate limit,
   métricas, config de IA e store do Treinador vivem todos na memória ou no
   disco local de UM processo. Escala vertical até um teto baixo e não escala
   horizontalmente sem reescrever essas camadas.

Nenhum desses é fatal, mas os três precisam de decisão antes de qualquer
investimento em features. O item 1 é decisão de produto; 2 e 3 são engenharia.

---

## 2. Arquitetura e definição de produto

### A1 (P0 de produto) Um caso de teste colonizou o núcleo

Correção importante de premissa: o extrato-Domínio **não é a alma da
plataforma**. Foi um cenário de teste de UMA aplicação. Isso torna o diagnóstico
mais grave, não menos.

O [README](../README.md) descreve corretamente a intenção: uma plataforma
genérica de automação (Abstra). Mas o conhecimento daquele teste contábil vazou
para os prompts centrais e se espalhou: 88 ocorrências de Domínio, `Inicia
Lote`, `pdfplumber`, aging, conciliação, OCR review em 25 arquivos. Os três
prompts que deveriam ser genéricos (`SYSTEM_PROMPT` em `chat.py:48`,
`CONSTRUTOR_PROMPT` em `orchestrator.py:164`, `_generate_build` em `chat.py:550`)
hoje carregam parágrafos inteiros de regra contábil brasileira hardcoded.

Consequência prática: para qualquer automação que NÃO seja extrato bancário, a
IA recebe páginas de instruções irrelevantes sobre lote do Domínio, colunas de
crédito/débito e parsing posicional de PDF. Isso enviesa o modelo, gasta contexto
e faz a plataforma parecer que "não encaixa" em casos genéricos, porque
literalmente não foi instruída para eles. O sintoma que você sentiu tem causa
concreta e localizável.

**Recomendação (invertida em relação à versão anterior deste dossiê):** o
genérico É a fundação. O extrato-Domínio deve virar UM template da galeria, não
conteúdo do prompt do núcleo. Concretamente:

1. Reduzir os três prompts centrais a instruções genéricas de automação (ler
   entrada, transformar, gravar saída via SDK, sem placeholder). Zero menção a
   Domínio, lote, aging ou conciliação.
2. Mover todo o conhecimento contábil para um template/exemplo carregado sob
   demanda quando a tarefa for daquele tipo (o mecanismo `reference_for_task` /
   `examples_context` já existe em embrião exatamente para isso).
3. O Classificador contábil (`orchestrator.py:268`) passa a ser um agente
   opcional acionado só quando o plano marca `contabil=true`, não um cidadão de
   primeira classe do fluxo.

Isso devolve a alma genérica ao produto e mantém o caso contábil como o primeiro
de muitos templates, que é o que ele sempre foi.

### A2 (P1) Três pipelines paralelos para gerar automação

Existem três caminhos independentes que geram o código, cada um com prompt
próprio ou reimportado:

| Caminho | Local | Prompt |
|---|---|---|
| Smart Chat monolítico | `chat.py:48` `SYSTEM_PROMPT` (140 linhas) + `_generate_build` | próprio |
| Orquestrador FSM | `orchestrator.py` Planejador/Construtor/Nomeador/Classificador | 4 prompts |
| Wizard 4 etapas | `wizard.py:22` reimporta `SYSTEM_PROMPT` + `_generate_build` | reusa o do chat |

O mesmo conhecimento de domínio está copiado à mão em `SYSTEM_PROMPT`
(`chat.py:48`), `CONSTRUTOR_PROMPT` (`orchestrator.py:164`) e no `instr` de
`_generate_build` (`chat.py:550`). Uma regra de negócio que mude (ex.: colunas
do Domínio) precisa ser editada em três lugares e vai divergir. Maior fonte de
bug latente do projeto.

No front, `App.tsx:72-73` expõe `/projects/:id/assistente` (Wizard, 1750 linhas)
e `/projects/:id/chat` para o mesmo objetivo, mais um `/chat` global. O produto
não decidiu qual é O jeito de criar automação.

**Recomendação:** unificar num pipeline (o orquestrador FSM é o mais
estruturado); chat e wizard viram apenas UIs que o alimentam. Extrair o
conhecimento de domínio dos prompts para uma base única (a galeria de templates
+ `reference_code` que já existe em embrião).

### A3 (P2) Infraestrutura especulativa: o Treinador

O `services/treinador.py` é um subsistema completo de auto-evolução (colher,
anonimizar, destilar prompts melhores). Por registro do próprio projeto, as
Tasks 6-12 estão pendentes desde 2026-07-01. Otimizar automaticamente prompts
que ainda estão em três cópias divergentes (A2) é otimizar o alvo errado, e não
há métrica objetiva do que "melhora" uma automação.

**Recomendação:** congelar (não deletar) até A2 estar resolvido e existir uma
métrica de qualidade.

---

## 3. Segurança

### S1 (P0) Execução de código sem sandbox real

`runtime/runner.py:228` monta o ambiente do subprocesso com
`env = os.environ.copy()` e executa `subprocess.run([python, script])`
(`runner.py:250`). O script:

- É gerado por IA e/ou editável pelo usuário no editor.
- Herda TODAS as variáveis de ambiente do servidor: `OPENAI_API_KEY`,
  `SECRET_KEY` (assina os JWT, inclusive de admin), `SUPABASE_DB_URL`,
  `SMTP_PASSWORD`.
- Roda como o mesmo usuário do servidor, com acesso total ao filesystem e à
  rede.

O README chama isso de "subprocesso isolado", mas não há isolamento: é execução
de código arbitrário com os privilégios e segredos do servidor. Um script pode
ler o `SECRET_KEY` e forjar um token de admin, ou exfiltrar o banco inteiro.
Para dados contábeis de clientes, é o risco mais grave do projeto.

**Correções (em ordem de robustez):**
1. Passar apenas as `EnvVar` do projeto para o subprocesso, nunca
   `os.environ.copy()`. Correção barata e imediata que fecha o vazamento de
   segredos do servidor.
2. Isolamento real: container efêmero por execução (gVisor, nsjail, ou
   Firecracker), sem rede por padrão, filesystem read-only exceto `run_dir`,
   usuário sem privilégios, limites de CPU/memória/pids via cgroups. O timeout
   já existe (`runner.py:164`).

### S2 (P1) `stderr` cru devolvido ao usuário do app publicado

`published.py:233` retorna `execu.stderr` ao usuário final quando a execução
falha. Tracebacks expõem caminhos absolutos do servidor, estrutura interna e,
se o script imprimir algo sensível, segredos. Sanitizar: mostrar a mensagem
amigável (`_last_error_line` já existe em `runner.py:40`) e guardar o traceback
completo só nos logs internos.

### S3 (P1) Senha seed comprometida

Registrado no histórico do projeto: `flowdesk123` vazou no git. O código já foi
parametrizado e o histórico reescrito, mas falta **rotacionar a senha no banco**
de qualquer ambiente que tenha rodado o seed antigo.

### S4 (P1) `app_execution` vaza `input_data`

`published.py:227-234` devolve `execu.input_data` ao usuário do app publicado,
que contém os caminhos absolutos dos arquivos no disco do servidor. Remover o
`input` da resposta pública.

### S5 (P2) Modo aberto do app publicado

`public_apps_open=True` (`config.py:40`) libera o app publicado sem nenhuma
autenticação e enfileira execuções (que caem no S1). É marcado como temporário,
mas ligá-lo expõe a execução de código à internet. Documentar como perigo e
nunca usar com S1 em aberto.

### S6 (P2) JWT sem revogação

Sem refresh token nem blacklist; logout é só client-side. Token do app
principal dura 7 dias (`config.py:27`). Um token vazado é válido até expirar.
Aceitável para app interno, revisar se virar SaaS.

---

## 4. Infraestrutura e escalabilidade

**Tese central:** o backend é um singleton de processo único por design. Cinco
camadas assumem "existe só um processo":

- Fila de execução em `asyncio.Queue` na memória do processo (`runner.py:55`).
- Rate limit em dict na memória (`ratelimit.py:32`, com `ponytail:` reconhecendo).
- Métricas em memória (`metrics.py`, `runner._durations`).
- Config de IA em JSON no disco local (`ai_config.py:19`).
- Store do Treinador em JSON no disco local (`treinador.py:18`).

Rodar dois processos uvicorn (o caminho normal de escala) quebra os cinco: filas
separadas, rate limit por processo, métricas divergentes, e um admin editando um
prompt na réplica A não afeta a réplica B. Isso é aceitável para uma caixa
on-premise única da IRKO, e bloqueante para HA/SaaS/multi-tenant.

### I1 (P1) Throughput de execução = 1 por vez, global

`runner._run_worker` (`runner.py:82`) tira um item da fila e faz `await
self._execute` antes de pegar o próximo. É serial: uma execução de 120s trava
TODAS as execuções de TODOS os projetos e usuários. O `run_in_executor`
(`runner.py:262`) dá a impressão de concorrência, mas o loop é serial.

**Caminho:** fila durável fora do processo (Redis + RQ/arq/Celery) e um pool de
N workers desacoplados do web. Enquanto não, documentar o teto de 1 execução
concorrente como limite conhecido.

### I2 (P1) Acoplamento a Windows + Excel COM

`storage.py:230-245` (`read_table`) shella `powershell` + `Excel.Application`
(COM) para converter `.xls` legado do Domínio. Isso prende o runtime a um host
Windows com Office instalado; não roda em container Linux, o que inviabiliza
autoscale e deploy em cloud padrão. `main.py:21` também força
`WindowsProactorEventLoopPolicy`.

**Caminho:** trocar a conversão por algo portável (LibreOffice headless
`soffice --convert-to xlsx` num container, ou `xlrd`/`pyexcel` para `.xls`
antigo). Desacoplar do Windows abre o deploy em Linux.

### I3 (P1) Disco cresce sem limite

`_uploads/<uuid>`, `runs/<uuid>` (`runner.py:129`) e a pasta de saída nunca são
limpos, e não há cota por projeto. Cada execução deixa `input.json`,
`output.json`, `tables.json` e os arquivos gerados para sempre. DoS de disco e
custo crescente.

**Caminho:** política de retenção (ex.: apagar `runs/` com mais de N dias) e
cota por projeto. Um job agendado simples resolve o essencial.

### I4 (P1) Migrações de schema à mão

Não há Alembic. As migrações são `ALTER TABLE`/`PRAGMA` escritos à mão no
`lifespan` (`main.py:60-109`) e em `database.ensure_orchestration_columns`. Cada
mudança de schema vira um `if` manual por dialeto. Frágil e propenso a erro.
Pior: com autoscale, duas réplicas subindo ao mesmo tempo rodam `ALTER TABLE`
concorrentes no boot (o `ALTER TYPE` do auto-heal em `database.py:82-84` não é
protegido por lock).

**Caminho:** adotar Alembic e rodar migração como passo de deploy, não no boot
de cada processo.

### I5 (P2) `materialize_sources` reescreve tudo a cada execução

`storage.py:51-59` regrava todos os `SourceFile` do projeto em
`RUNTIME_SRC_DIR/<id>` (compartilhado por id) a cada execução. Com 1 worker é
serial e funciona; com >1 worker, duas execuções do mesmo projeto colidiriam nos
mesmos `.py`. I/O desnecessário e bug latente ao escalar.

### I6 (P2) Métricas efêmeras

`metrics.py` e `runner._durations` vivem em memória: somem no restart e não
agregam entre processos. Para observabilidade real, exportar para um backend
(Prometheus/StatsD) ou tabela.

---

## 5. Erros e riscos no código

### B1 (P1) Leitura de anexos ignora o próprio contrato

`chat._attachment_context` (`chat.py:266-282`) lê anexos com `pd.read_excel` /
`pd.read_csv` direto. Os três prompts proíbem isso e exigem `read_table` por
causa do `.xls` legado do Domínio ("Expected BOF record"). O contexto que
alimenta a entrevista falha exatamente nos arquivos do caso de uso principal,
caindo no ramo "não foi possível ler". A plataforma não segue o contrato que
impõe ao modelo. Usar `storage.read_table` / `extract_document`.

### B2 (P2) `get_file` heurístico frágil

`get_file` no SDK (`storage.py:154`) monta a lista de arquivos filtrando os
values do input por `Path(v).exists()`. Um campo de texto do form que por acaso
contenha um caminho existente entraria como "arquivo". E `paths[name]` depende
da ordem de inserção do dict. O fallback por nome `arquivo{i+1}` mitiga, mas a
heurística é frágil. Preferir marcar explicitamente quais campos são de arquivo
no input.

### B3 (P2) Corrida de migração/seed no boot multi-processo

`seed_if_empty` e as migrações rodam no `lifespan` de cada processo
(`main.py:110`). Em multi-processo, é corrida de boot. Ligado a I4.

### B4 (P2) Download aceita caminho absoluto do query param

`_resolve_download_target` (`published.py:249-257`) constrói o alvo a partir de
`Path(path)` que pode ser absoluto, e só depois valida `parents`. A validação
cobre o caso, mas a construção é frágil; melhor rejeitar absoluto de entrada.

### B5 (P2) Retry de import transiente re-executa o script inteiro

`runner.py:169` re-`_spawn` no cold start de numpy/pandas. A falha ocorre no
import, antes do código de negócio, então efeito colateral é improvável, mas se
um dia o heurístico `_is_transient_import_error` casar com outro erro após
efeito colateral (ex.: e-mail já enviado), reexecutaria. Baixo risco, monitorar.

---

## 6. Uso a longo prazo e manutenibilidade

- **M1 (P1)** Conhecimento de domínio triplicado em prompts (A2): dívida que
  cresce a cada regra nova.
- **M2 (P1)** Três pipelines de geração (A2): cada bug precisa ser corrigido três
  vezes.
- **M3 (P1)** Sem Alembic (I4): evolução de schema é artesanal.
- **M4 (P2)** `chat.py` com 1143 linhas mistura router HTTP, montagem de
  workflow, análise por AST e prompt. Baixa coesão, difícil de testar em
  unidades. Extrair a lógica de workflow para um serviço.
- **M5 (P2)** Config de IA e Treinador em JSON no disco (M7 do sumário):
  diverge entre réplicas, não é transacional. Mover para o banco.
- **M6 (P2)** Sem testes de carga/concorrência. `qa_suite.py` é funcional
  ponta-a-ponta, não cobre o comportamento sob fila cheia ou execuções
  concorrentes (que hoje nem existem, por I1).
- **M7 (P1)** Acoplamento Windows/Excel (I2) prende toda a evolução de deploy.

---

## 7. Roadmap priorizado

### P0 (antes de qualquer produção com dado real de cliente)
1. **S1**: parar de vazar `os.environ` para o subprocesso (correção de horas) e
   planejar sandbox real (container efêmero).
2. **S3**: rotacionar a senha seed no banco.

### P1 (antes de crescer o uso)
3. **A1**: extrair o conhecimento contábil dos prompts centrais para um template
   da galeria; restaurar prompts genéricos. Destrava A2, A3.
4. **A2 / M1 / M2**: unificar num pipeline; o domínio vira template carregado sob
   demanda, não texto fixo triplicado.
5. **I2 / M7**: desacoplar de Windows/Excel para permitir deploy em Linux.
6. **I1**: fila durável + workers desacoplados (ou documentar o teto de 1).
7. **I3**: retenção e cota de disco.
8. **I4 / M3**: adotar Alembic.
9. **S2 / S4**: parar de vazar `stderr` e `input_data` no app publicado.
10. **B1**: leitura de anexos via `read_table`.

### P2 (qualidade de longo prazo)
11. **A3**: congelar o Treinador até A2 pronto.
12. **M4**: quebrar `chat.py` em serviços.
13. **M5 / I6**: mover config de IA/Treinador e métricas para o banco.
14. **B2, B4, B5**: endurecer as heurísticas frágeis.
15. **M6**: testes de carga e de concorrência.

---

## 8. O que NÃO mexer (está bom)

Para calibrar: estas decisões são maduras e não devem ser "simplificadas".

- `services/ai_call.py`: camada única de chamada ao provedor, justificada por dor
  real (um modelo de raciocínio no dropdown quebrava todos os routers).
- `services/ai_guard.py` + `wrap_untrusted`: prompt injection tratado na
  fronteira dos dados. Segurança de fronteira feita certo.
- `chat._input_files_from_code` (`chat.py:809`): contagem de arquivos por AST,
  onde regex genuinamente não daria conta.
- Suporte a Postgres já presente (`database.py`) e índices criados no boot.
