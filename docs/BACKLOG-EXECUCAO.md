# Backlog: camada de execução (sandbox, modo degradado, fila)

Três itens de backlog derivados da revisão de 2026-07-30 sobre "Python é a stack
certa?". Conclusão daquela revisão: sim, Python fica. Nenhuma dor real da
plataforma se resolve trocando a linguagem do backend, porque o artefato gerado
(pandas, openpyxl, xlrd, pdfplumber, rapidocr) é Python por necessidade e o
gargalo medido não está na API. As dores estão na **camada de execução**, e são
estas três.

Complementa `DOSSIE-TECNICO.md` (itens S1, I1, I2, I5) com o plano de execução e,
principalmente, com as armadilhas: o que **não** pode entrar em commit.

Prioridade segue a convenção do dossiê: **P0** bloqueia produção com dado real,
**P1** é teto de escala que já dói, **P2** é qualidade de longo prazo.

---

## Estado atual (verificado em código, não presumido)

| Fato | Evidência |
| --- | --- |
| Default de execução é `subprocess` | [config.py:35](../back/app/config.py#L35) |
| `EXECUTION_BACKEND` não é definido no deploy | [docker-compose.yml](../docker-compose.yml) não menciona a variável |
| Sem `SCRIPT_PYTHON`, o script roda no interpretador da API | [config.py:78-80](../back/app/config.py#L78-L80) cai em `sys.executable` |
| A allowlist de env protege segredos, não disco nem rede | [runner.py:48-60](../back/app/runtime/runner.py#L48-L60) e [runner.py:307](../back/app/runtime/runner.py#L307) |
| Sandbox de container existe, pronto e desligado | [container.py](../back/app/runtime/container.py), imagem em `back/runtime-image/` |
| Deps do script já divergem das da API | `pandas==2.2.2` no runtime-image, `2.2.3` em `back/requirements.txt` |
| Fila serial, uma execução por vez, global | [runner.py:106-113](../back/app/runtime/runner.py#L106-L113) |
| `docker_available()` nunca é chamado pelo app | só aparece em `tests/test_container_run.py` |

**Consequência hoje, em homologação:** o script gerado por IA e editável pelo
usuário roda no mesmo container, mesmo interpretador e mesmo filesystem da API,
com acesso a `/app/storage` inteiro (todos os projetos, todos os clientes) e à
rede interna do compose. Os segredos do processo estão protegidos pela allowlist;
o resto não está.

---

## Item 1 (P0) Ligar o sandbox de container no deploy Linux

**Objetivo:** em qualquer ambiente Linux (hml e prod), toda execução de script
gerado acontece em container efêmero, sem rede, filesystem read-only, sem
capabilities, como uid 65534, com teto de memória, CPU e PIDs.

**Por que agora:** é o único item da lista que muda o perfil de risco. O código
já existe; falta ligar e resolver dois blocantes reais de caminho.

### Blocante A: os caminhos do `-v` não são os mesmos dentro e fora do container

[container.py:61-63](../back/app/runtime/container.py#L61-L63) monta
`run_dir`, `output_dir` e `src_dir` com os caminhos vistos pelo processo que
chama o Docker. Se a API roda dentro de um container e fala com o daemon do host,
o daemon resolve esses caminhos no **filesystem do host**, não no do container.
Resultado: monta diretório vazio ou falha, e nenhuma execução funciona. Isso não
aparece em teste local no Windows com Docker Desktop, que mascara o problema.

Agrava: `STORAGE_DIR` é `back/storage` relativo ao código
([config.py:10-11](../back/app/config.py#L10-L11)), e `RUNTIME_SRC_DIR` vive em
`tempfile.gettempdir()` ([config.py:18](../back/app/config.py#L18)), que é
`/tmp` **interno ao container** e não é volume nenhum. São dois caminhos a
reconciliar, não um.

Opções, com trade-off honesto:

1. **Caminhos idênticos nos dois lados (recomendada).** Bind mount do host em
   `/app/storage:/app/storage` e `/tmp/flowdesk-runtime-src:/tmp/flowdesk-runtime-src`.
   Zero mudança de código. Custo: troca o volume nomeado `flowdesk_storage` por
   bind mount de caminho absoluto do host, e **é preciso confirmar se o EasyPanel
   permite bind mount fora da árvore dele**. Não presuma: verifique antes de
   escrever o compose.
2. **Worker de execução fora do compose, no host.** Resolve o caminho por
   construção. Custo: um processo a mais para operar e supervisionar, e depende do
   Item 3 (fila fora do processo) para fazer sentido.
3. **Docker-in-Docker.** Isola o daemon, custa privilégio elevado e mais peças.
   Não vale para uma caixa single-tenant.

### Blocante B: `--network=none` muda o comportamento das automações

O sandbox corta a rede por completo. Qualquer automação publicada que consulte
API, envie e-mail ou baixe arquivo passa a falhar, e falha com erro de rede que o
usuário final não entende. Antes de virar o default, é preciso saber se existe
automação assim em uso. Se existir, a decisão é de produto (proxy com allowlist
por projeto, ou flag por projeto), não de infraestrutura, e vira item separado.

### Passos, cada um com sua verificação

1. Levantar se há automação em uso que precisa de rede. Verificar: consulta nos
   scripts publicados por `requests`, `httpx`, `urllib`, `smtplib`.
2. Decidir e registrar a opção de caminho (1, 2 ou 3), confirmando o suporte do
   EasyPanel a bind mount. Verificar: um `docker run -v` de teste no host, a
   partir do container `back`, montando o dir real e listando o conteúdo.
3. Buildar `flowdesk-runtime` no host de hml. Verificar: `docker images` lista a
   tag e `docker run --rm flowdesk-runtime python -c "import pandas, pdfplumber"`
   sai com 0.
4. Expor o acesso ao daemon para o serviço `back`, com a decisão do passo 2.
   Verificar: `docker info` de dentro do container `back` retorna 0.
5. Definir `EXECUTION_BACKEND=container` **só no ambiente Linux**, via variável do
   EasyPanel, e adicionar a variável ao compose com default vazio.
6. Rodar de ponta a ponta uma automação que leia planilha e grave arquivo.
   Verificar: `output.json` gravado, `status=success`, arquivo de saída presente
   em `outputs/`, e `docker ps -a` sem container órfão.
7. Rodar a suíte de container no host Linux: `pytest back/tests/test_container_run.py`.

### Critério de aceite

- Execução em hml roda em container, comprovado por `docker events` ou por log com
  o nome `flowdesk-<run_id>`.
- Um script de teste que tente ler `/app/storage/../.env` ou abrir socket falha.
- Uma execução de outro projeto não é visível de dentro do sandbox.
- Windows on-premise continua em `subprocess` e continua passando os testes.

### Armadilhas: o que NÃO commitar

- **`EXECUTION_BACKEND=container` como default no `config.py`.** Quebra o
  on-premise Windows inteiro, onde o backend de container não funciona por design
  ([container.py:5-9](../back/app/runtime/container.py#L5-L9)). O valor vive no
  ambiente, não no código.
- **`EXECUTION_BACKEND: container` fixo no `docker-compose.yml`.** Mesmo problema
  para quem sobe o compose local no Windows. Se entrar no compose, entra como
  `${EXECUTION_BACKEND:-}`, com default vazio.
- **Montagem do socket do Docker sem registrar o risco.** `-v
  /var/run/docker.sock:/var/run/docker.sock` no serviço `back` dá ao processo da
  API poder equivalente a root no host. Se for a opção escolhida, o commit precisa
  dizer isso em comentário no compose, e a decisão precisa ser consciente, não
  herdada de um tutorial.
- **Bind mount com caminho de máquina de alguém.** Nada de
  `/home/marcelo/...` ou `C:\Users\...` no compose. Caminho de host vem de
  variável de ambiente ou é um caminho neutro e documentado.
- **Deixar de sincronizar `back/runtime-image/requirements.txt`.** Se o script
  passa a rodar na imagem de runtime, é essa lista que define o que ele pode
  importar. Commit que adiciona dep ao SDK e esquece a imagem entrega
  `ModuleNotFoundError` em produção com o teste local passando.
- **`.env`, `SUPABASE_DB_URL`, `SECRET_KEY`, `OPENAI_API_KEY` em qualquer arquivo
  versionado.** O `.gitignore` cobre `.env` e `.env.*`, mas não cobre um segredo
  colado dentro do `docker-compose.yml` ou de um `README`. Compose recebe
  `${VAR}`, sempre.
- **Imagem, `flowdesk.db`, `storage/`, planilhas de teste.** Já cobertos pelo
  `.gitignore`; não force com `git add -f`.
- **Remover o retry de import transiente "porque no container não acontece".**
  ([runner.py:224-226](../back/app/runtime/runner.py#L224-L226)) O caminho
  `subprocess` continua vivo no Windows e depende dele. Mudança de sandbox não
  autoriza limpeza no caminho que não está sendo trocado.
- **Commit misturando o compose, o default do config e refatoração do runner.**
  Este item precisa ser revertível em um `git revert` só. Se a virada do sandbox
  quebrar hml, você quer desfazer a virada, não o resto.

---

## Item 2 (P1) Tornar o `subprocess` um modo degradado explícito, não o silêncio atual

**Objetivo:** parar de tratar `subprocess` como equivalente ao container. Ele
existe porque o on-premise Windows precisa dele, e é aceitável ali. Em Linux, é
uma escolha que precisa ser visível a quem opera.

**Por que é item separado do 1:** o Item 1 muda infraestrutura de um ambiente.
Este muda o que o sistema diz sobre si mesmo, e vale mesmo que o Item 1 atrase.

### Escopo

1. **Preflight no boot.** Com `EXECUTION_BACKEND=container`, chamar
   `docker_available()` no startup e falhar alto, ou logar aviso severo e recusar
   enfileirar. Hoje a função existe e nunca é chamada fora dos testes: se o daemon
   não estiver acessível, cada execução falha isolada com erro obscuro de
   subprocess, e ninguém liga uma coisa à outra.
2. **Registrar o backend efetivo por execução.** Persistir em `Execution` qual
   backend rodou. Sem isso, ao investigar um incidente você não sabe se aquela
   execução foi sandboxed ou não.
3. **Aviso no painel de admin quando rodando `subprocess` em Linux.** Uma linha,
   junto das métricas de máquina que já existem em `routers/admin.py`.
4. **Documentar em `SECURITY.md`** que `subprocess` é modo degradado, com o que
   ele protege (segredos do processo, via allowlist) e o que não protege
   (filesystem de storage, rede interna, deps compartilhadas com a API).

### Critério de aceite

- Subir com `EXECUTION_BACKEND=container` e daemon indisponível produz erro claro
  no boot ou no log, nomeando a causa.
- Uma execução consultada na API informa o backend usado.
- `SECURITY.md` descreve os dois modos sem eufemismo.

### Armadilhas: o que NÃO commitar

- **Fallback silencioso de `container` para `subprocess`.** Tentador e péssimo:
  transforma falha de configuração em degradação invisível de segurança. Pediu
  container e não tem container, então falha. Nunca "cai pro subprocess" sozinho.
- **`docker info` no caminho de cada execução.** São até 15s de timeout por
  chamada ([container.py:81](../back/app/runtime/container.py#L81)) numa fila que
  já é serial. Preflight é no boot, e no máximo com cache.
- **Migration só para o campo de backend, sem rodar `alembic upgrade head` em
  hml.** Coluna nova em modelo sem migration correspondente quebra o deploy.
- **Texto tranquilizador no `SECURITY.md`.** "Execução isolada por processo" é
  falso para o modo `subprocess`. Documento de segurança que ameniza é pior que
  documento ausente, porque induz decisão errada.
- **Aproveitar a passagem para "melhorar" o `admin.py`.** Uma linha de aviso é o
  escopo.

---

## Item 3 (P2, condicionado) Fila durável e pool de workers

**Não fazer agora.** Está aqui para não ser esquecido e para não ser antecipado.

**Gatilho de entrada:** dado real de fila, não intuição. Concretamente: fila com
mais de N itens pendentes de forma recorrente, ou reclamação de espera atribuída
à serialização, ou necessidade de mais de uma instância do backend por
disponibilidade. Enquanto o gargalo for uma execução pesada por vez numa caixa
única, paralelizar só troca o gargalo pelo disco.

**Pré-requisito obrigatório, e é uma pegadinha:** I5 do dossiê.
`materialize_sources` reescreve o mesmo `src_dir` por projeto a cada execução.
Com duas execuções concorrentes do mesmo projeto, uma sobrescreve o `.py` da
outra no meio da execução. Ou seja: **habilitar concorrência antes de
materializar por execução introduz corrupção silenciosa de resultado**, não
lentidão. O ceiling está anotado em [runner.py:106-113](../back/app/runtime/runner.py#L106-L113)
e a ordem ali é a correta.

### Escopo, na ordem

1. Materializar o código em `RUNTIME_SRC_DIR/<projeto>/<exec_id>` por execução, com
   limpeza. Verificar: teste que roda duas execuções do mesmo projeto com códigos
   diferentes e confirma que cada uma viu o seu.
2. Fila durável fora do processo (Redis + `arq` ou RQ; Celery só se precisar do
   ecossistema). Verificar: matar o processo web no meio e confirmar que o item
   pendente sobrevive e é processado.
3. Worker desacoplado do web, com N configurável.
4. Só então trocar o `await` serial por concorrência limitada.

Outras camadas de estado em memória do mesmo processo (rate limit, métricas,
config de IA, store do Treinador) precisam sair da memória antes de haver mais de
uma instância. Isso é I6/A3 do dossiê, não deste item, mas bloqueia o mesmo
objetivo de HA.

### Armadilhas: o que NÃO commitar

- **Aumentar a concorrência antes do passo 1.** É o erro que corrompe dado do
  cliente sem quebrar nada visivelmente. Nenhuma exceção, nem "só em dev".
- **Redis como dependência obrigatória do boot.** O on-premise é uma caixa só.
  Sem Redis configurado, o caminho atual precisa continuar funcionando.
- **`asyncio.gather` nas execuções como "solução rápida".** Some com o teto de
  memória e CPU da máquina, e o passo 1 continua faltando.
- **Redis com URL, senha ou host de produção em arquivo versionado.** Mesma regra
  do Item 1: ambiente, nunca código.
- **Reescrita do `runner.py` num commit só.** Cada passo do escopo é um commit com
  a sua verificação. Um commit grande aqui é irrevertível na prática, e este é o
  caminho crítico da plataforma.

---

## Regras de commit válidas para os três itens

1. **Nada de segredo em arquivo versionado.** Nem em compose, nem em README, nem
   em comentário, nem em teste. O `.gitignore` cobre `.env*`, `back/flowdesk.db*`,
   `back/storage/`, `testes/dominio/` e as planilhas de QA na raiz. Ele não cobre
   você colando uma string.
2. **Nunca `SUPABASE_DB_URL` no `.env` local.** Os testes usam o engine do app;
   com a URL de produção presente, um teste destrutivo apaga dado real. Dev e
   testes usam SQLite.
3. **Commitar só os caminhos que você tocou.** Sem `git add -A`. Há sessões
   concorrentes e WIP de terceiros na árvore.
4. **Um item, um commit revertível.** Mudança de infraestrutura separada de
   mudança de comportamento, separada de refatoração.
5. **Verificação antes de "pronto".** Cada passo acima tem um comando ou uma
   observação concreta. "Deve funcionar" não conta.
6. **Nada de mudança de produção sem confirmação explícita.** Deploy, migração de
   banco e virada de `EXECUTION_BACKEND` em prod pedem aprovação, mesmo com
   autorização permanente de commit e push.
