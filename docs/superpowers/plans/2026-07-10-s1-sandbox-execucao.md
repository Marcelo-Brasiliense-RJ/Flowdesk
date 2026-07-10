# S1 Sandbox de Execução (primeira etapa) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Executar o script de cada automação num container Linux efêmero e isolado (rede off, FS read-only exceto os dirs de trabalho, limites de CPU/mem/pids, usuário sem privilégio), mantendo o subprocess atual como default até validar.

**Architecture:** Um novo módulo `container.py` monta e roda o comando `docker run` isolado. `RuntimeManager._spawn` passa a despachar entre o subprocess atual e o container conforme `settings.execution_backend`. O contrato de I/O (input.json / output.json em `run_dir`, saída em `output_dir`) é preservado montando esses diretórios no container e reescrevendo os caminhos passados ao script.

**Tech Stack:** Python 3.11, FastAPI, pydantic-settings, Docker/Podman CLI, pytest.

## Global Constraints

- Alvo do runtime é Linux em container; motor Docker/Podman, gVisor-ready via flag `--runtime`.
- `execution_backend` default `"subprocess"`: o caminho atual NÃO pode quebrar (on-premise Windows continua rodando por subprocess).
- Segredos do servidor nunca chegam ao script: reusar a allowlist `_ENV_PASSTHROUGH` já existente em `runner.py` (commit `a99cd4d`), nunca `os.environ` inteiro.
- Rede default-deny (`--network=none`) nesta etapa; egresso por projeto é item futuro.
- Sem `pip install` em runtime: dependências pré-assadas na imagem `flowdesk-runtime`.
- Testes que exigem daemon Docker fazem `skip` controlado quando o daemon está ausente; a verificação real roda com o Docker Desktop ligado.
- Commits pequenos, só os caminhos tocados, mensagem no padrão do repo, sufixo `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

### Task 1: Campos de configuração do sandbox

**Files:**
- Modify: `back/app/config.py:32` (dentro da classe `Settings`, junto de `script_python`)
- Test: `back/tests/test_sandbox_config.py`

**Interfaces:**
- Produces: `settings.execution_backend: str`, `settings.container_image: str`, `settings.container_memory: str`, `settings.container_cpus: str`, `settings.container_pids: int`, `settings.container_runtime: str`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# back/tests/test_sandbox_config.py
import sys
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

from app.config import Settings


def test_defaults_do_sandbox_preservam_subprocess():
    s = Settings()
    assert s.execution_backend == "subprocess"  # on-premise não quebra
    assert s.container_image == "flowdesk-runtime:latest"
    assert s.container_memory == "512m"
    assert s.container_cpus == "1"
    assert s.container_pids == 128
    assert s.container_runtime == ""
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_sandbox_config.py -v` (a partir de `back/`)
Expected: FAIL com `AttributeError: 'Settings' object has no attribute 'execution_backend'`

- [ ] **Step 3: Implementar os campos**

Em `back/app/config.py`, logo após `script_python: str = ""` (linha 32), adicionar:

```python
    # Sandbox de execução (S1). "subprocess" = comportamento atual (default,
    # on-premise). "container" = container efêmero isolado por execução.
    execution_backend: str = "subprocess"
    container_image: str = "flowdesk-runtime:latest"
    container_memory: str = "512m"
    container_cpus: str = "1"
    container_pids: int = 128
    container_runtime: str = ""  # vazio = runtime padrão; "runsc" = gVisor
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_sandbox_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add back/app/config.py back/tests/test_sandbox_config.py
git commit -m "feat(security): config do sandbox de execução (S1)"
```

---

### Task 2: Construção do comando de container (pura, testável sem daemon)

Separar a MONTAGEM do comando `docker run` (lógica pura, testável sem Docker) da execução (Task 3). Assim as garantias de isolamento são verificáveis por unidade, sem daemon.

**Files:**
- Create: `back/app/runtime/container.py`
- Test: `back/tests/test_container_cmd.py`

**Interfaces:**
- Consumes: `settings` (Task 1), `_ENV_PASSTHROUGH` de `app.runtime.runner`.
- Produces:
  - `build_docker_cmd(*, image, run_dir, output_dir, src_dir, entry, env, memory, cpus, pids, runtime) -> list[str]`
  - `container_env(env_vars: dict) -> dict[str, str]` (env allowlist + EnvVar do projeto, SEM os caminhos host; os `FLOWDESK_*` internos são setados aqui apontando para `/run` e `/out`).

- [ ] **Step 1: Escrever o teste que falha**

```python
# back/tests/test_container_cmd.py
import sys
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

from app.runtime.container import build_docker_cmd, container_env


def test_cmd_isola_rede_fs_usuario_e_recursos(tmp_path):
    cmd = build_docker_cmd(
        image="flowdesk-runtime:latest",
        run_dir=tmp_path / "run",
        output_dir=tmp_path / "out",
        src_dir=tmp_path / "src",
        entry="proc.py",
        env={"FLOWDESK_INPUT": "/run/input.json", "PROJ_TOKEN": "x"},
        memory="512m",
        cpus="1",
        pids=128,
        runtime="",
    )
    s = " ".join(cmd)
    assert cmd[0] == "docker"
    assert "run" in cmd and "--rm" in cmd
    assert "--network=none" in cmd
    assert "--read-only" in cmd
    assert "--user=65534:65534" in cmd
    assert "--memory=512m" in cmd
    assert "--cpus=1" in cmd
    assert "--pids-limit=128" in cmd
    # run_dir montado rw, src_dir montado ro
    assert f"{tmp_path / 'run'}:/run:rw" in s
    assert f"{tmp_path / 'src'}:/src:ro" in s
    assert f"{tmp_path / 'out'}:/out:rw" in s
    # env do projeto passa por -e; runtime vazio não vira flag
    assert "PROJ_TOKEN=x" in s
    assert "--runtime" not in s
    # entrypoint
    assert cmd[-3:] == ["flowdesk-runtime:latest", "python", "/src/proc.py"]


def test_runtime_gvisor_vira_flag(tmp_path):
    cmd = build_docker_cmd(
        image="img", run_dir=tmp_path, output_dir=tmp_path, src_dir=tmp_path,
        entry="p.py", env={}, memory="256m", cpus="1", pids=64, runtime="runsc",
    )
    assert "--runtime=runsc" in cmd


def test_container_env_nao_vaza_segredos_do_servidor(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "vaza")
    monkeypatch.setenv("OPENAI_API_KEY", "vaza")
    monkeypatch.setenv("PATH", "/usr/bin")
    env = container_env({"PROJ_TOKEN": "visivel"})
    assert env["PROJ_TOKEN"] == "visivel"
    assert "SECRET_KEY" not in env
    assert "OPENAI_API_KEY" not in env
    assert env["PYTHONPATH"] == "/src"
    assert env["FLOWDESK_INPUT"] == "/run/input.json"
    assert env["FLOWDESK_OUTPUT"] == "/run/output.json"
    assert env["FLOWDESK_OUTPUT_DIR"] == "/out"
    assert env["FLOWDESK_RUN_DIR"] == "/run"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_container_cmd.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.runtime.container'`

- [ ] **Step 3: Implementar `container.py`**

```python
# back/app/runtime/container.py
"""S1: monta o comando de container efêmero e isolado para rodar o script.

A montagem do comando é pura (sem chamar Docker) para as garantias de
isolamento serem testáveis por unidade. A execução fica em run_in_container().
"""
from __future__ import annotations

import os
from pathlib import Path

from .runner import _ENV_PASSTHROUGH


def container_env(env_vars: dict) -> dict[str, str]:
    """Ambiente do processo DENTRO do container: allowlist de SO + EnvVar do
    projeto + os FLOWDESK_* já apontando para os caminhos internos (/run, /out).
    Nunca inclui segredos do servidor."""
    env = {k: v for k, v in os.environ.items() if k.upper() in _ENV_PASSTHROUGH}
    env.update({k: str(v) for k, v in env_vars.items()})
    env["FLOWDESK_INPUT"] = "/run/input.json"
    env["FLOWDESK_OUTPUT"] = "/run/output.json"
    env["FLOWDESK_OUTPUT_DIR"] = "/out"
    env["FLOWDESK_RUN_DIR"] = "/run"
    env["PYTHONPATH"] = "/src"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def build_docker_cmd(
    *,
    image: str,
    run_dir: Path,
    output_dir: Path,
    src_dir: Path,
    entry: str,
    env: dict[str, str],
    memory: str,
    cpus: str,
    pids: int,
    runtime: str,
) -> list[str]:
    cmd = [
        "docker", "run", "--rm",
        "--network=none",
        "--read-only",
        "--tmpfs", "/tmp:rw,size=64m",
        f"--memory={memory}",
        f"--cpus={cpus}",
        f"--pids-limit={pids}",
        "--user=65534:65534",
        "-v", f"{run_dir}:/run:rw",
        "-v", f"{output_dir}:/out:rw",
        "-v", f"{src_dir}:/src:ro",
        "-w", "/run",
    ]
    if runtime:
        cmd.append(f"--runtime={runtime}")
    for k, v in env.items():
        cmd.extend(["-e", f"{k}={v}"])
    cmd.extend([image, "python", f"/src/{entry}"])
    return cmd
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_container_cmd.py -v`
Expected: PASS (3 testes)

- [ ] **Step 5: Commit**

```bash
git add back/app/runtime/container.py back/tests/test_container_cmd.py
git commit -m "feat(security): montagem do comando de container isolado (S1)"
```

---

### Task 3: Execução no container + staging de arquivos de entrada

**Files:**
- Modify: `back/app/runtime/container.py` (adicionar `run_in_container` e `_stage_inputs`)
- Test: `back/tests/test_container_run.py`

**Interfaces:**
- Consumes: `build_docker_cmd`, `container_env` (Task 2); `settings` (Task 1).
- Produces:
  - `docker_available() -> bool`
  - `run_in_container(*, src_dir, output_dir, run_dir, entry, env_vars, timeout) -> tuple[int, str, str]`

**Nota de staging:** o `input.json` pode referenciar arquivos por caminho absoluto do host (uploads). Esses arquivos são copiados para `run_dir/in/` e os caminhos no input reescritos para `/run/in/<nome>` antes de disparar, para `get_file`/`get_input` do SDK enxergarem-nos dentro do container sem montar `_uploads` inteiro.

- [ ] **Step 1: Escrever o teste que falha (gated por Docker)**

```python
# back/tests/test_container_run.py
import json
import sys
from pathlib import Path

import pytest

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

from app.runtime.container import docker_available, run_in_container

pytestmark = pytest.mark.skipif(
    not docker_available(), reason="daemon Docker indisponível"
)


def _prep(tmp_path, script: str, input_data: dict | None = None):
    src = tmp_path / "src"; src.mkdir()
    run = tmp_path / "run"; run.mkdir()
    out = tmp_path / "out"; out.mkdir()
    (run / "input.json").write_text(
        json.dumps(input_data or {}, ensure_ascii=False), encoding="utf-8"
    )
    (src / "proc.py").write_text(script, encoding="utf-8")
    return src, run, out


def test_script_legitimo_le_input_e_grava_output(tmp_path):
    src, run, out = _prep(
        tmp_path,
        "import os, json, pandas as pd\n"
        "df = pd.DataFrame({'a':[1,2,3]})\n"
        "open(os.environ['FLOWDESK_OUTPUT'],'w').write(json.dumps({'soma':int(df['a'].sum())}))\n",
    )
    rc, so, se = run_in_container(
        src_dir=src, output_dir=out, run_dir=run, entry="proc.py",
        env_vars={}, timeout=60,
    )
    assert rc == 0, se
    saida = json.loads((run / "output.json").read_text(encoding="utf-8"))
    assert saida["soma"] == 6


def test_rede_desligada_falha_controlada(tmp_path):
    src, run, out = _prep(
        tmp_path,
        "import socket, os\n"
        "socket.create_connection(('8.8.8.8', 53), timeout=5)\n"
        "open(os.environ['FLOWDESK_OUTPUT'],'w').write('{}')\n",
    )
    rc, so, se = run_in_container(
        src_dir=src, output_dir=out, run_dir=run, entry="proc.py",
        env_vars={}, timeout=60,
    )
    assert rc != 0
    assert not (run / "output.json").exists()


def test_escrita_fora_do_run_dir_falha(tmp_path):
    src, run, out = _prep(
        tmp_path,
        "open('/etc/flowdesk_pwn','w').write('x')\n",
    )
    rc, so, se = run_in_container(
        src_dir=src, output_dir=out, run_dir=run, entry="proc.py",
        env_vars={}, timeout=60,
    )
    assert rc != 0  # root FS read-only
```

- [ ] **Step 2: Rodar e ver falhar**

Run (com Docker ligado): `python -m pytest tests/test_container_run.py -v`
Expected: FAIL com `ImportError: cannot import name 'run_in_container'` (ou `docker_available`)

- [ ] **Step 3: Implementar `run_in_container` + `_stage_inputs` + `docker_available`**

Adicionar em `back/app/runtime/container.py`:

```python
import shutil
import subprocess


def docker_available() -> bool:
    exe = shutil.which("docker")
    if not exe:
        return False
    try:
        r = subprocess.run([exe, "info"], capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def _cap(b: bytes, limit: int = 100_000) -> str:
    s = b.decode("utf-8", "replace")
    return s if len(s) <= limit else s[:limit] + "\n[...saída truncada...]"


def _stage_inputs(run_dir: Path) -> None:
    """Copia para run_dir/in/ os arquivos referenciados por caminho absoluto no
    input.json e reescreve os caminhos para /run/in/<nome> (visão do container).
    Sem arquivos referenciados, é no-op."""
    import json as _json

    input_path = run_dir / "input.json"
    if not input_path.exists():
        return
    data = _json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return
    in_dir = run_dir / "in"
    changed = False
    for key, value in list(data.items()):
        if isinstance(value, str):
            p = Path(value)
            if p.is_absolute() and p.is_file():
                in_dir.mkdir(exist_ok=True)
                dest = in_dir / p.name
                shutil.copy2(p, dest)
                data[key] = f"/run/in/{p.name}"
                changed = True
    if changed:
        input_path.write_text(_json.dumps(data, ensure_ascii=False), encoding="utf-8")


def run_in_container(
    *,
    src_dir: Path,
    output_dir: Path,
    run_dir: Path,
    entry: str,
    env_vars: dict,
    timeout: int,
) -> tuple[int, str, str]:
    from ..config import settings

    _stage_inputs(run_dir)
    cmd = build_docker_cmd(
        image=settings.container_image,
        run_dir=run_dir,
        output_dir=output_dir,
        src_dir=src_dir,
        entry=entry,
        env=container_env(env_vars),
        memory=settings.container_memory,
        cpus=settings.container_cpus,
        pids=settings.container_pids,
        runtime=settings.container_runtime,
    )
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return r.returncode, _cap(r.stdout), _cap(r.stderr)
    except subprocess.TimeoutExpired as e:
        err = _cap(e.stderr or b"") + f"\n[runtime] Tempo limite de {timeout}s excedido."
        return 1, _cap(e.stdout or b""), err
```

- [ ] **Step 4: Rodar e ver passar (Docker ligado)**

Run: `python -m pytest tests/test_container_run.py -v`
Expected: PASS (3 testes). Sem daemon: 3 SKIPPED.

- [ ] **Step 5: Commit**

```bash
git add back/app/runtime/container.py back/tests/test_container_run.py
git commit -m "feat(security): execução isolada em container + staging de inputs (S1)"
```

---

### Task 4: Imagem `flowdesk-runtime`

**Files:**
- Create: `back/runtime-image/Dockerfile`
- Create: `back/runtime-image/requirements.txt`
- Create: `back/runtime-image/README.md`

**Interfaces:**
- Produces: imagem `flowdesk-runtime:latest` com o stack de dados curado + `flowdesk_sdk`.

- [ ] **Step 1: Escrever `requirements.txt` da imagem**

```
# back/runtime-image/requirements.txt
pandas==2.2.2
numpy==2.0.1
openpyxl==3.1.5
xlrd==2.0.1
pdfplumber==0.11.4
```

- [ ] **Step 2: Escrever o Dockerfile**

```dockerfile
# back/runtime-image/Dockerfile
FROM python:3.11-slim

RUN useradd -u 65534 -r -s /usr/sbin/nologin nobodyrun || true

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# flowdesk_sdk é montado em /src junto do script do projeto em runtime.
WORKDIR /run
USER 65534:65534
```

- [ ] **Step 3: Escrever o README de build**

```markdown
# back/runtime-image/README.md
Imagem de sandbox para execução de scripts (S1).

Build:

    docker build -t flowdesk-runtime:latest back/runtime-image

O stack de libs é fixo (rede desligada no runtime, sem pip install). Para
adicionar uma dependência que os scripts possam usar, edite requirements.txt e
reconstrua a imagem.
```

- [ ] **Step 4: Construir a imagem (Docker ligado)**

Run: `docker build -t flowdesk-runtime:latest back/runtime-image`
Expected: build conclui; `docker images` lista `flowdesk-runtime`.

- [ ] **Step 5: Commit**

```bash
git add back/runtime-image/Dockerfile back/runtime-image/requirements.txt back/runtime-image/README.md
git commit -m "feat(security): imagem flowdesk-runtime do sandbox (S1)"
```

---

### Task 5: Despachar `_spawn` entre subprocess e container

**Files:**
- Modify: `back/app/runtime/runner.py` (dentro de `_spawn`, ~linha 226)
- Test: `back/tests/test_spawn_backend.py`

**Interfaces:**
- Consumes: `run_in_container` (Task 3); `settings.execution_backend` (Task 1).
- Produces: `_spawn` roteia por `settings.execution_backend`; default `"subprocess"` mantém o comportamento atual byte-a-byte.

- [ ] **Step 1: Escrever o teste que falha**

```python
# back/tests/test_spawn_backend.py
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

from app.runtime.runner import RuntimeManager


def _kwargs(tmp_path):
    src = tmp_path / "src"; src.mkdir()
    run = tmp_path / "run"; run.mkdir()
    (run / "input.json").write_text("{}", encoding="utf-8")
    (src / "p.py").write_text("open(__import__('os').environ['FLOWDESK_OUTPUT'],'w').write('{}')\n", encoding="utf-8")
    return dict(
        src_dir=src, cwd=run, entry="p.py",
        input_path=run / "input.json", output_path=run / "output.json",
        output_dir=run, run_dir=run, env_vars={}, timeout=30,
    )


def test_backend_container_delega_para_run_in_container(tmp_path):
    mgr = RuntimeManager()
    with patch("app.config.settings.execution_backend", "container"), \
         patch("app.runtime.container.run_in_container", return_value=(0, "", "")) as m:
        rc, so, se = asyncio.run(mgr._spawn(**_kwargs(tmp_path)))
    assert rc == 0
    assert m.called


def test_backend_subprocess_e_o_default(tmp_path):
    mgr = RuntimeManager()
    # default subprocess: roda de verdade e grava output
    rc, so, se = asyncio.run(mgr._spawn(**_kwargs(tmp_path)))
    assert rc == 0
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_spawn_backend.py -v`
Expected: `test_backend_container_delega_para_run_in_container` FAIL (o subprocess roda em vez de delegar; `m.called` é False).

- [ ] **Step 3: Implementar o dispatch**

No começo de `_spawn` (`back/app/runtime/runner.py`, logo após `import os` na linha ~226), antes de montar `env`:

```python
        from ..config import settings

        if settings.execution_backend == "container":
            from .container import run_in_container

            return await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: run_in_container(
                    src_dir=src_dir,
                    output_dir=output_dir,
                    run_dir=run_dir,
                    entry=entry,
                    env_vars=env_vars,
                    timeout=timeout,
                ),
            )
```

O restante do `_spawn` (o caminho subprocess com a allowlist) fica intacto abaixo desse `if`.

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_spawn_backend.py -v`
Expected: PASS (2 testes)

- [ ] **Step 5: Rodar a suíte inteira (garantir que o default não quebrou)**

Run: `python -m pytest -q`
Expected: os mesmos 131 passed + os novos; a única falha aceitável é a pré-existente `test_seed_heal::test_heal_restaura_script_defasado` (I4/B3, não relacionada).

- [ ] **Step 6: Commit**

```bash
git add back/app/runtime/runner.py back/tests/test_spawn_backend.py
git commit -m "feat(security): _spawn despacha entre subprocess e container (S1)"
```

---

### Task 6: Verificação end-to-end e nota no napkin

**Files:**
- Modify: `.claude/napkin.md` (aprendizados: como buildar a imagem, rodar os testes gated por Docker, pegadinha do daemon parado no Windows)

- [ ] **Step 1: Verificação real com o backend container**

Com Docker ligado e a imagem buildada, apontar `execution_backend=container` (via env `EXECUTION_BACKEND=container`) e exercer uma automação real ponta a ponta pelo app (upload de planilha → script pandas → download), confirmando que roda isolada e a saída sai correta. Colar a evidência.

- [ ] **Step 2: security-review da mudança completa (S1 parte 2)**

Rodar a revisão de segurança sobre a diff das Tasks 1-5. Sem achados de severidade alta.

- [ ] **Step 3: Registrar aprendizados no napkin e commitar**

```bash
git add .claude/napkin.md
git commit -m "docs: aprendizados do sandbox de execução no napkin (S1)"
```

---

## Self-Review

**Spec coverage:**
- Seam de executor → Task 5. ContainerExecutor (net=none, read-only, run_dir rw, tmpfs, limites, non-root, env allowlist) → Tasks 2 e 3. Imagem flowdesk-runtime → Task 4. Config → Task 1. Staging de uploads → Task 3. Rede default-deny documentada → Global Constraints + Task 4 README. Critérios de sucesso (rede/fs bloqueados, script legítimo roda, subprocess default intacto, security-review) → Tasks 3, 5, 6. Coberto.
- Fora do escopo (I1, egresso por projeto, gVisor efetivo, remoção do subprocess) permanece fora, como no spec.

**Placeholder scan:** sem TBD/TODO; todo passo de código tem o código.

**Type consistency:** `build_docker_cmd`/`container_env`/`run_in_container`/`docker_available` usados em Tasks 3 e 5 batem com as assinaturas definidas na Task 2/3. Campos de `settings` (Task 1) usados iguais em `run_in_container`. `_ENV_PASSTHROUGH` reusado de `runner.py` (já existe). Consistente.
