# S1 (parte 2): Sandbox real de execução de scripts

Data: 2026-07-10
Item do dossiê: S1 (P0), segunda parte. A primeira parte (parar de herdar
`os.environ` no subprocesso) já foi entregue no commit `a99cd4d`.

## Problema

O runtime executa scripts gerados por IA (e editáveis pelo usuário) com
`subprocess.run([python, script])` no mesmo host e usuário do servidor web
(`runner.py:_spawn`). Mesmo após a allowlist de ambiente, o script ainda tem:

- acesso total ao filesystem do servidor (ler/escrever qualquer caminho);
- rede aberta (exfiltração, SSRF, chamadas a serviços internos);
- os privilégios do usuário do servidor;
- sem teto de CPU/memória/processos além do timeout já existente.

Para dados contábeis de clientes IRKO, isso é inaceitável em produção.

## Premissas fechadas (brainstorming)

- **Alvo do runtime:** Linux, em container. Acopla-se a I2 (desacoplar do Excel
  COM) e habilita deploy em cloud.
- **Motor:** Docker/Podman, container efêmero por execução. gVisor-ready
  (`--runtime=runsc` plugável depois sem mudar o design).
- **Transição:** o caminho atual (subprocess in-process) permanece vivo como
  fallback e default até o caminho container ser validado (cuidado #6 do prompt:
  não deixar a máquina on-premise sem execução no meio da transição).

## Arquitetura

### Seam de executor

`_spawn` passa a delegar a um executor escolhido por configuração, sem
hierarquia especulativa (só as duas implementações que existem de fato):

- `SubprocessExecutor`: o comportamento atual, incluindo a allowlist de ambiente
  de `a99cd4d`. **Default.**
- `ContainerExecutor`: roda o script num container efêmero.

Config `execution_backend: "subprocess" | "container"` decide qual. O dict de
ambiente já montado hoje (allowlist `_ENV_PASSTHROUGH` + `env_vars` do projeto +
`FLOWDESK_*`) é reaproveitado e injetado no container via `-e`.

### ContainerExecutor

Comando por execução:

```
docker run --rm --network=none --read-only
  --tmpfs /tmp:rw,size=64m
  --memory=<container_memory> --cpus=<container_cpus> --pids-limit=<container_pids>
  --user 65534:65534
  -v <run_dir>:/run:rw
  -v <src_dir>:/src:ro
  -e FLOWDESK_INPUT=/run/input.json -e FLOWDESK_OUTPUT=/run/output.json
  -e FLOWDESK_OUTPUT_DIR=/run -e FLOWDESK_RUN_DIR=/run
  -e PYTHONPATH=/src -e PYTHONIOENCODING=utf-8
  <-e cada var da allowlist/EnvVar do projeto>
  [--runtime=<container_runtime se definido>]
  -w /run
  <container_image>
  python /src/<entry>
```

Propriedades de isolamento:

- **Rede:** `--network=none` (default-deny).
- **Filesystem:** root read-only; escrita só em `/run` (o `run_dir` montado) e
  num `tmpfs` `/tmp` limitado. `src_dir` montado read-only.
- **Usuário:** `65534:65534` (nobody), sem privilégio.
- **Recursos:** `--memory`, `--cpus`, `--pids-limit` por flag; o timeout já
  existente (`runner.py`) continua envolvendo a chamada.
- **gVisor:** `--runtime=runsc` só se `container_runtime` estiver definido;
  vazio = runtime padrão.

Os caminhos de `input_path`/`output_path`/`output_dir` que hoje são absolutos do
host passam a ser reescritos para os caminhos internos do container (`/run/...`).
A leitura do `output.json` continua sendo feita pelo host no `run_dir` real
(montado), então o contrato de I/O com o resto do runner não muda.

**Arquivos de entrada (uploads):** hoje o `input_data` referencia arquivos por
caminho absoluto do host (ex.: `_uploads/<uuid>/planilha.xls`), que não resolvem
dentro do container. O `ContainerExecutor` deve, antes de disparar, copiar os
arquivos referenciados no input para dentro de `run_dir` (ex.: `run_dir/in/`) e
reescrever os caminhos do `input.json` para os equivalentes internos
(`/run/in/...`). Assim `get_file`/`get_input` do SDK enxergam os arquivos sem
montar `_uploads` inteiro nem vazar a árvore do host. Este staging é parte
obrigatória da primeira etapa para que uma automação real (com upload) rode no
container, não só os scripts sintéticos dos testes de isolamento.

### Imagem `flowdesk-runtime`

Dockerfile versionado no repo. Base Python fixada + o stack de dados curado que
os scripts podem usar (pandas, numpy, openpyxl, leitor `.xls` portável pensando
no I2, pdfplumber) + `flowdesk_sdk`. Como a rede está desligada, não há
`pip install` em runtime: as dependências são pré-assadas na imagem. Tag da
imagem fica em config.

### Configuração (novos campos)

| Campo | Default | Papel |
|---|---|---|
| `execution_backend` | `"subprocess"` | qual executor usar |
| `container_image` | `"flowdesk-runtime:latest"` | imagem do sandbox |
| `container_memory` | `"512m"` | teto de memória |
| `container_cpus` | `"1"` | teto de CPU |
| `container_pids` | `128` | teto de processos |
| `container_runtime` | `""` | vazio = padrão; `"runsc"` = gVisor |

## Fluxo de dados

1. Runner prepara `run_dir` (input.json, dirs de saída) como hoje.
2. Executor escolhido por `execution_backend`.
3. `ContainerExecutor` monta `run_dir` (rw) e `src_dir` (ro), injeta env,
   dispara `docker run`, captura stdout/stderr (com o mesmo truncamento
   `_cap` atual), respeita o timeout.
4. Host lê `output.json` do `run_dir` real. Nada muda para `_execute`/
   `_chain_next` a jusante.

## Tratamento de erro

- Docker indisponível ou imagem ausente com `execution_backend=container`: falha
  controlada com mensagem clara nos logs internos; não vaza detalhe de infra ao
  usuário (alinhado a S2).
- Estouro de memória/pids/CPU: o container morre; returncode != 0 e a mensagem
  amigável (`_last_error_line`) já cobre a exibição ao usuário.
- Timeout: mesmo caminho atual (`subprocess.TimeoutExpired`), mais `docker run`
  encerrado.

## Escopo da primeira etapa (implementável agora)

1. Novos campos de config.
2. `ContainerExecutor` com net=none + root read-only + `run_dir` rw + tmpfs +
   limites + non-root + env allowlist reaproveitada.
3. Dockerfile da imagem `flowdesk-runtime`.
4. Testes TDD (rodam onde o daemon Docker está disponível; `skip` controlado
   quando ausente):
   - script que tenta abrir socket de rede falha de forma controlada;
   - script que tenta escrever fora de `run_dir` falha;
   - script que lê `input` e escreve em `run_dir` tem sucesso e o host lê a saída.
5. `subprocess` permanece como default; on-prem não quebra.

## Fora do escopo (adiado, itens próprios)

- Fila durável + pool de workers (I1).
- Egresso de rede por projeto (allowlist via proxy) para conectores/hooks. A
  primeira etapa é default-deny e **documenta** que conectores que dependem de
  rede não funcionam sob o sandbox até essa etapa existir.
- Runtime gVisor efetivo (design pronto, é só a flag `container_runtime`).
- Remoção do caminho `subprocess`.

## Critério de sucesso (verificável)

- Com `execution_backend=container`: um script que tenta abrir conexão de rede
  OU escrever fora de `run_dir` falha de forma controlada (evidência: saída do
  teste).
- Um script legítimo (lê input, usa pandas, grava output) roda com sucesso no
  container.
- Com `execution_backend=subprocess` (default): comportamento atual intacto,
  suíte existente verde.
- security-review da mudança sem achados de severidade alta.
