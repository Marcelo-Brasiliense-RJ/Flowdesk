# Design: Sandbox de execução (S1 parte 2)

Data: 2026-07-09
Item do dossiê: S1 (P0) parte 2, isolamento real da execução de código.
Depende de: S1 parte 1 (allowlist de env, commit 7321589) já concluída.

## Contexto e premissa

Scripts gerados por IA (e editáveis pelo usuário) rodam hoje num subprocesso
local (`RuntimeManager._spawn`, `back/app/runtime/runner.py`) com os privilégios
do processo servidor, rede plena e filesystem plena. A parte 1 do S1 já cortou o
vazamento de segredos do servidor (o subprocesso recebe apenas uma allowlist de
variáveis de SO mais as `EnvVar` do projeto). Falta o isolamento real: rede off
por padrão, filesystem read-only exceto a área de storage do projeto, limites de
CPU/memória/pids e usuário não privilegiado.

Restrições de realidade levantadas na análise:

- A plataforma tem dois alvos de deploy. On-premise Windows (produção atual, com
  Docker Desktop/WSL2 disponível) e, no roteiro, um VPS Linux na Hostinger
  orquestrado pelo EasyPanel (Docker nativo).
- `read_table` do SDK (`flowdesk_sdk.py`, materializado em `src_dir`) lê `.xls`
  legado do Domínio. A cadeia é: `pd.read_excel` (usa `xlrd`, pip puro, roda em
  Linux) e, só se o pandas falhar E a extensão for `.xls`, cai numa conversão via
  Excel COM (PowerShell, Windows-only). Ou seja, apenas `.xls` fora do padrão do
  Domínio dependem do Excel COM, e a falha já é controlada (RuntimeError com
  orientação "exporte como .xlsx/.csv").
- Não pode quebrar o caso extrato-Domínio (cuidado #3) nem deixar a caixa Windows
  sem conversão de `.xls` durante a transição (cuidado #6).

## Decisão

Introduzir uma costura mínima de backend de execução no `runner`, com dois
backends selecionados por flag de configuração:

- `local` (default): comportamento atual, subprocesso na máquina (já com a
  allowlist do S1 parte 1). Preserva o Excel COM e o caso contábil no Windows.
- `docker` (opt-in): roda o mesmo script num contêiner Linux efêmero, isolado.

O backend Docker é a fundação do isolamento real e o caminho natural de default
no alvo Linux (Hostinger/EasyPanel), mas entra desligado por padrão para não
mudar produção nem quebrar o `.xls` malformado enquanto o I2 (conversão portável)
não existir.

## Arquitetura (a costura)

Hoje `_spawn` fixa "subprocesso local". A mudança extrai a operação "rode este
script com estes caminhos/env/timeout e devolva `(returncode, stdout, stderr)`"
para uma função selecionável, sem hierarquia de classes especulativa:

- `_spawn_local(...)`: o corpo atual de `_spawn`.
- `_spawn_docker(...)`: nova função com a mesma assinatura e o mesmo contrato de
  retorno.
- `_spawn(...)` passa a despachar para uma das duas conforme
  `settings.execution_backend`.

O restante do fluxo (`_run_once`, materialização de fontes, escrita de
`input.json`/`tables.json`, `_chain_next`, broadcast por WebSocket) não muda. O
contrato de I/O por arquivos em disco (`FLOWDESK_INPUT`, `FLOWDESK_OUTPUT`,
`FLOWDESK_OUTPUT_DIR`, `FLOWDESK_RUN_DIR`) é o que permite trocar o backend sem
tocar no SDK nem nos scripts.

## Contenção do backend Docker

`docker run --rm` com:

- `--network none`: rede off por padrão.
- `--read-only` no rootfs e `--tmpfs /tmp`: nada gravável fora do previsto.
- Um único bind gravável para a área de storage do projeto:
  `-v <root_do_projeto>:/project:rw`, onde `root = storage.ensure_project_dirs(project)`
  contém `runs/<id>` e a pasta de saída. `cwd` do contêiner é `/project`.
  Contido: só o diretório deste projeto é gravável, nunca o servidor ou outros
  projetos.
- Código read-only: `-v <src_dir>:/src:ro`, `PYTHONPATH=/src`. O `src_dir`
  (materializado em `RUNTIME_SRC_DIR/<id>`, fora do storage) inclui o script e o
  `flowdesk_sdk.py`.
- `--user 1000:1000`: processo não-root.
- `--memory`, `--cpus`, `--pids-limit`: limites de recurso (valores na config).
- `EnvVar` do projeto via `-e`; os `FLOWDESK_*` reescritos para os caminhos do
  contêiner (`/project/runs/<id>`, etc.). Segredos do servidor nunca entram (o
  contêiner sobe limpo, reforçando o S1 parte 1).
- Timeout: reusa o `subprocess.run(..., timeout=...)` sobre o cliente `docker`.
  Como `docker run` pode deixar o contêiner vivo se o cliente for morto, usar
  `--name flowdesk-run-<execution_id>` e, no `TimeoutExpired`, forçar
  `docker rm -f <name>` antes de propagar o timeout.

Correção em relação ao texto do dossiê: o gravável não é só `run_dir`, e sim o
root de storage do projeto (o script grava a saída em `output_dir`, irmão de
`run_dir` sob o mesmo root). Isso mantém a contenção (um projeto por vez) sem
quebrar a gravação de saída.

## Imagem e dependências

Imagem `flowdesk-runtime` construída a partir do `requirements.txt` completo do
projeto (decisão: uma fonte, zero drift, garante "roda no local, roda no
Docker"). Base `python:3.11-slim`. As libs pesadas do runtime
(`rapidocr-onnxruntime`, `pymupdf`, `pdfplumber`, `pillow`, `pandas`, `openpyxl`,
`xlrd`, `psutil`) têm wheels Linux e são pip-only. O nome/tag da imagem é
configurável em `settings` (`runtime_image`), preparado para virar
`ghcr.io/<org>/flowdesk-runtime:<tag>` no deploy.

## Limites (defaults)

- `--memory=512m`
- `--cpus=1.0`
- `--pids-limit=256`

Todos configuráveis via `settings`/env. Aviso operacional: OCR de PDF grande
(`rapidocr-onnxruntime` + `pymupdf`) pode estourar 512m. Como o backend Docker é
opt-in, começa conservador; subir o teto é só ajustar a env.

## Interação com o `.xls` (por que o default fica `local`)

Dentro do contêiner Linux, `read_table` lê `.csv`, `.xlsx` e `.xls` padrão via
pandas/xlrd normalmente. Só o `.xls` fora do padrão do Domínio (que hoje depende
do Excel COM) falha, e falha de forma controlada (o RuntimeError já existente).
Como o backend Docker é opt-in e o default é `local`, o caso extrato-Domínio
continua rodando no caminho Windows com Excel COM. Os testes `test_extrato_dominio*`
exercitam o backend `local` e permanecem verdes.

## Config

- `execution_backend: str = "local"` (aceita `"local"` ou `"docker"`).
- `runtime_image: str = "flowdesk-runtime:local"`.
- `runtime_memory: str = "512m"`, `runtime_cpus: str = "1.0"`,
  `runtime_pids_limit: int = 256`.

## Testes

Teste de contenção novo (`tests/test_sandbox_docker.py`), com skip automático se
o Docker não estiver disponível no ambiente (`docker info` falha) ou se a imagem
não existir, para não quebrar CI sem Docker:

- Script sonda rodando com `execution_backend="docker"` prova, num único run:
  1. tentativa de abrir socket de rede externo falha (rede off);
  2. tentativa de escrever fora de `/project` (ex.: `/etc/x`, `/src/x`) falha
     (FS read-only);
  3. escrita em `/project/runs/<id>` funciona;
  4. nenhum segredo do servidor (`SECRET_KEY`, `OPENAI_API_KEY`) visível.

O teste do backend `local` (S1 parte 1) já existe e continua valendo.

## Escopo

Nesta etapa (P0):

- Costura `_spawn` -> `_spawn_local`/`_spawn_docker`.
- `_spawn_docker` com a contenção acima.
- `back/runtime.Dockerfile`.
- Flags de config.
- Teste de contenção com skip.
- Build manual documentado no napkin.

Fora desta etapa (dependências explícitas, fases posteriores):

- Virar o default para `docker` no alvo Linux: bloqueado por I2 (conversão
  portável de `.xls`, ex.: LibreOffice headless) para não regredir `.xls`
  malformado.
- Workflow GitHub Actions -> GHCR publicando a imagem pinada por tag/digest
  (fase de deploy Linux, I2-era). Não buildar no VPS, não auto-buildar no boot.
- Decisão arquitetural do acesso ao daemon Docker pelo app no EasyPanel (montar
  `/var/run/docker.sock` dá root no host; alternativas: rootless/sysbox ou worker
  dedicado). Resolver antes do Docker virar default no VPS.
- Fila durável e workers desacoplados (I1). Independente desta etapa; o backend
  Docker herda o teto de 1 execução concorrente atual.

## Critério de sucesso (mapeado ao prompt)

- Plano escrito (este documento) e primeira etapa implementada (rede off por
  padrão, FS read-only exceto a área do projeto, limites CPU/mem).
- Verificação: um script que tenta abrir conexão de rede ou escrever fora da área
  do projeto falha de forma controlada (teste de contenção acima).
- Suíte existente continua verde; caso extrato-Domínio intacto no backend `local`.
- security-review da parte sem achados abertos de severidade alta.
