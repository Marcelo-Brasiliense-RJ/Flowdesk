# Sandbox de execução (S1 parte 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar isolamento real à execução de scripts via um backend Docker opt-in (rede off, FS read-only exceto a área do projeto, limites de recurso, usuário não-root), sem mudar o default nem quebrar o caso contábil.

**Architecture:** Uma costura mínima no `RuntimeManager._spawn` despacha entre `_spawn_local` (comportamento atual, default) e `_spawn_docker` (contêiner Linux efêmero), selecionada por `settings.execution_backend`. O contrato de I/O por arquivos em disco (`FLOWDESK_*`) permite trocar o backend sem tocar no SDK nem nos scripts.

**Tech Stack:** Python 3.11, FastAPI, pydantic-settings, Docker (Docker Desktop/WSL2 no host de dev), pytest.

## Global Constraints

- Default de execução é `local`; o backend `docker` entra desligado (`execution_backend="local"`).
- Não quebrar `test_extrato_dominio*` nem o baseline: a única falha pré-existente aceitável é `tests/test_seed_heal.py::test_heal_restaura_script_defasado`.
- Comando de teste: `/c/Users/mbrasiliense98/Documents/FlowDesk/back/.venv/Scripts/python.exe -m pytest` rodado de dentro de `back/`.
- Commitar apenas os caminhos tocados pela tarefa; nunca `git add -A`.
- Sem em dash na prosa; comentários de código em ASCII sem acento seguem o padrão do arquivo.

---

### Task 1: Costura de backend no `_spawn`

Renomeia o corpo atual de `_spawn` para `_spawn_local` e cria um `_spawn` que despacha por `settings.execution_backend`. Sem mudança de comportamento no default.

**Files:**
- Modify: `back/app/config.py` (adicionar campo `execution_backend`)
- Modify: `back/app/runtime/runner.py` (renomear `_spawn` -> `_spawn_local`, novo `_spawn` dispatcher)
- Test: `back/tests/test_spawn_dispatch.py` (criar)

**Interfaces:**
- Consumes: `settings` de `app.config`.
- Produces:
  - `RuntimeManager._spawn_local(self, *, src_dir, cwd, entry, input_path, output_path, output_dir, run_dir, env_vars, timeout) -> tuple[int, str, str]` (corpo atual, inalterado).
  - `RuntimeManager._spawn(self, **kwargs) -> tuple[int, str, str]` (dispatcher; Task 3 estende para `docker`).
  - `settings.execution_backend: str` default `"local"`.

- [ ] **Step 1: Escrever o teste de dispatch que falha**

Criar `back/tests/test_spawn_dispatch.py`:

```python
"""S1: o _spawn despacha por settings.execution_backend."""
import asyncio

import pytest

from app.config import settings
from app.runtime import runner


def test_backend_local_chama_spawn_local(monkeypatch):
    monkeypatch.setattr(settings, "execution_backend", "local", raising=False)
    mgr = runner.RuntimeManager()
    chamado = {}

    async def fake_local(**kwargs):
        chamado["local"] = kwargs
        return (0, "ok", "")

    monkeypatch.setattr(mgr, "_spawn_local", fake_local)
    rc, out, err = asyncio.run(mgr._spawn(entry="x.py", env_vars={}))
    assert rc == 0 and out == "ok"
    assert chamado["local"]["entry"] == "x.py"


def test_backend_desconhecido_levanta(monkeypatch):
    monkeypatch.setattr(settings, "execution_backend", "docker", raising=False)
    mgr = runner.RuntimeManager()
    with pytest.raises(ValueError, match="execution_backend"):
        asyncio.run(mgr._spawn(entry="x.py", env_vars={}))
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `cd back && /c/Users/mbrasiliense98/Documents/FlowDesk/back/.venv/Scripts/python.exe -m pytest tests/test_spawn_dispatch.py -v`
Expected: FAIL (o segundo teste falha porque hoje `_spawn` executa `local` para qualquer valor; não existe `ValueError`).

- [ ] **Step 3: Adicionar o campo de config**

Em `back/app/config.py`, logo após a linha `script_python: str = ""` (linha 32):

```python
    # Backend de execução de scripts: "local" (subprocesso na máquina, default)
    # ou "docker" (contêiner Linux efêmero isolado, ver S1 parte 2).
    execution_backend: str = "local"
```

- [ ] **Step 4: Renomear `_spawn` para `_spawn_local` e criar o dispatcher**

Em `back/app/runtime/runner.py`, mudar a linha `async def _spawn(` (a assinatura do método atual) para `async def _spawn_local(`. O corpo permanece idêntico. Em seguida, adicionar imediatamente ANTES de `_spawn_local` o novo dispatcher:

```python
    async def _spawn(self, **kwargs) -> tuple[int, str, str]:
        backend = settings.execution_backend
        if backend == "local":
            return await self._spawn_local(**kwargs)
        raise ValueError(f"execution_backend desconhecido: {backend!r}")
```

- [ ] **Step 5: Rodar o teste de dispatch e ver passar**

Run: `cd back && /c/Users/mbrasiliense98/Documents/FlowDesk/back/.venv/Scripts/python.exe -m pytest tests/test_spawn_dispatch.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Rodar a suíte inteira (sem regressão)**

Run: `cd back && /c/Users/mbrasiliense98/Documents/FlowDesk/back/.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, exceto a falha pré-existente `test_seed_heal.py::test_heal_restaura_script_defasado`. O teste do S1 parte 1 (`tests/test_subprocess_env_isolation.py`) continua verde (ele chama `_spawn` com backend default `local`).

- [ ] **Step 7: Commit**

```bash
git add back/app/config.py back/app/runtime/runner.py back/tests/test_spawn_dispatch.py
git commit -m "refactor(s1): costura de backend de execucao no _spawn (local default)"
```

---

### Task 2: Imagem `flowdesk-runtime` e config

Cria o `Dockerfile` da imagem de runtime (a partir do `requirements.txt` completo) e os campos de config da imagem e limites.

**Files:**
- Create: `back/runtime.Dockerfile`
- Modify: `back/app/config.py` (campos `runtime_image`, `runtime_memory`, `runtime_cpus`, `runtime_pids_limit`)
- Modify: `.claude/napkin.md` (comando de build documentado)

**Interfaces:**
- Produces:
  - `settings.runtime_image: str` default `"flowdesk-runtime:local"`.
  - `settings.runtime_memory: str` default `"512m"`.
  - `settings.runtime_cpus: str` default `"1.0"`.
  - `settings.runtime_pids_limit: int` default `256`.
  - Imagem Docker `flowdesk-runtime:local` com python 3.11 e todas as libs do `requirements.txt`.

- [ ] **Step 1: Escrever o `Dockerfile`**

Criar `back/runtime.Dockerfile`:

```dockerfile
# Imagem de runtime para o sandbox de execução (S1 parte 2).
# Build (a partir de back/):
#   docker build -f runtime.Dockerfile -t flowdesk-runtime:local .
FROM python:3.11-slim

# libs de sistema exigidas por opencv (rapidocr-onnxruntime) e afins
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# usuário não-root para rodar os scripts
RUN useradd --uid 1000 --create-home runner
WORKDIR /project
USER 1000:1000
```

- [ ] **Step 2: Adicionar os campos de config**

Em `back/app/config.py`, logo após o campo `execution_backend` criado na Task 1:

```python
    # Imagem e limites do backend "docker" (S1 parte 2). runtime_image aponta
    # para ghcr.io/<org>/flowdesk-runtime:<tag> no deploy Linux.
    runtime_image: str = "flowdesk-runtime:local"
    runtime_memory: str = "512m"
    runtime_cpus: str = "1.0"
    runtime_pids_limit: int = 256
```

- [ ] **Step 3: Buildar a imagem**

Run: `cd back && docker build -f runtime.Dockerfile -t flowdesk-runtime:local .`
Expected: build conclui sem erro (o `pip install` de onnxruntime/pymupdf pode levar minutos).

- [ ] **Step 4: Smoke test dos imports do SDK dentro da imagem**

Run: `docker run --rm flowdesk-runtime:local python -c "import pandas, xlrd, openpyxl, pdfplumber, fitz, rapidocr_onnxruntime, PIL; print('ok')"`
Expected: imprime `ok`.

- [ ] **Step 5: Registrar o build no napkin**

Em `.claude/napkin.md`, adicionar sob a categoria de comandos de runtime (criar a seção se não existir) a linha:

```markdown
- Build da imagem do sandbox (de dentro de `back/`): `docker build -f runtime.Dockerfile -t flowdesk-runtime:local .`. Rebuild quando `requirements.txt` mudar.
```

- [ ] **Step 6: Commit**

```bash
git add back/runtime.Dockerfile back/app/config.py .claude/napkin.md
git commit -m "feat(s1): imagem flowdesk-runtime e config do backend docker"
```

---

### Task 3: `_spawn_docker` e teste de contenção

Implementa o backend Docker com a contenção completa, dirigido por um teste que prova rede off, FS read-only exceto a área do projeto, e ausência de segredos.

**Files:**
- Modify: `back/app/runtime/runner.py` (novo método `_spawn_docker`; estender o dispatcher)
- Test: `back/tests/test_sandbox_docker.py` (criar)

**Interfaces:**
- Consumes: `settings.runtime_image`, `settings.runtime_memory`, `settings.runtime_cpus`, `settings.runtime_pids_limit`, `settings.execution_backend`; `RuntimeManager._spawn` (Task 1).
- Produces: `RuntimeManager._spawn_docker(self, *, src_dir, cwd, entry, input_path, output_path, output_dir, run_dir, env_vars, timeout) -> tuple[int, str, str]`.

- [ ] **Step 1: Escrever o teste de contenção que falha**

Criar `back/tests/test_sandbox_docker.py`:

```python
"""S1 parte 2: contencao do backend docker. Skip se docker/imagem ausentes."""
import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.config import settings
from app.runtime import runner


def _docker_ok() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(["docker", "info"], capture_output=True, timeout=30, check=True)
        img = subprocess.run(
            ["docker", "image", "inspect", settings.runtime_image],
            capture_output=True, timeout=30,
        )
        return img.returncode == 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _docker_ok(), reason="docker ou imagem flowdesk-runtime:local indisponivel"
)

_PROBE = (
    "import os, json, socket\n"
    "r = {}\n"
    "try:\n"
    "    s = socket.create_connection(('8.8.8.8', 53), timeout=3); s.close(); r['network']='OPEN'\n"
    "except Exception:\n"
    "    r['network']='BLOCKED'\n"
    "try:\n"
    "    open('/etc/flowdesk_probe','w').write('x'); r['write_etc']='OK'\n"
    "except Exception:\n"
    "    r['write_etc']='BLOCKED'\n"
    "try:\n"
    "    open('/src/flowdesk_probe','w').write('x'); r['write_src']='OK'\n"
    "except Exception:\n"
    "    r['write_src']='BLOCKED'\n"
    "try:\n"
    "    open(os.path.join(os.environ['FLOWDESK_RUN_DIR'],'probe.txt'),'w').write('ok'); r['write_run']='OK'\n"
    "except Exception as e:\n"
    "    r['write_run']='FAIL:'+str(e)\n"
    "r['SECRET_KEY']=os.environ.get('SECRET_KEY')\n"
    "r['OPENAI_API_KEY']=os.environ.get('OPENAI_API_KEY')\n"
    "print(json.dumps(r))\n"
)


def test_docker_contem_rede_fs_e_segredos(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "execution_backend", "docker", raising=False)
    monkeypatch.setenv("SECRET_KEY", "servidor-secreto")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-leak")

    root = tmp_path / "project"
    run_dir = root / "runs" / "exec1"
    run_dir.mkdir(parents=True)
    out_dir = root / "output"
    out_dir.mkdir()
    src = tmp_path / "src"
    src.mkdir()
    (src / "probe.py").write_text(_PROBE, encoding="utf-8")

    mgr = runner.RuntimeManager()
    rc, out, err = asyncio.run(
        mgr._spawn(
            src_dir=src,
            cwd=root,
            entry="probe.py",
            input_path=run_dir / "input.json",
            output_path=run_dir / "output.json",
            output_dir=out_dir,
            run_dir=run_dir,
            env_vars={},
            timeout=60,
        )
    )

    assert rc == 0, f"container falhou (stderr={err!r})"
    r = json.loads(out.strip().splitlines()[-1])
    assert r["network"] == "BLOCKED"
    assert r["write_etc"] == "BLOCKED"
    assert r["write_src"] == "BLOCKED"
    assert r["write_run"] == "OK"
    assert r["SECRET_KEY"] is None
    assert r["OPENAI_API_KEY"] is None
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `cd back && /c/Users/mbrasiliense98/Documents/FlowDesk/back/.venv/Scripts/python.exe -m pytest tests/test_sandbox_docker.py -v`
Expected: FAIL com `ValueError: execution_backend desconhecido: 'docker'` (o dispatcher da Task 1 ainda não conhece `docker`).

- [ ] **Step 3: Implementar `_spawn_docker`**

Em `back/app/runtime/runner.py`, adicionar o método logo após `_spawn_local`:

```python
    async def _spawn_docker(
        self,
        *,
        src_dir: Path,
        cwd: Path,
        entry: str,
        input_path: Path,
        output_path: Path,
        output_dir: Path,
        run_dir: Path,
        env_vars: dict,
        timeout: int,
    ) -> tuple[int, str, str]:
        import subprocess

        # cwd e o root de storage do projeto; run_dir e output_dir vivem sob ele.
        root = cwd

        def _to_container(p: Path) -> str:
            rel = str(p.relative_to(root)).replace("\\", "/")
            return "/project/" + rel

        name = f"flowdesk-run-{run_dir.name}"
        cmd = [
            "docker", "run", "--rm", "--name", name,
            "--network", "none",
            "--read-only",
            "--tmpfs", "/tmp",
            "-v", f"{root}:/project:rw",
            "-v", f"{src_dir}:/src:ro",
            "--user", "1000:1000",
            "--memory", settings.runtime_memory,
            "--cpus", settings.runtime_cpus,
            "--pids-limit", str(settings.runtime_pids_limit),
            "-w", "/project",
            "-e", "PYTHONPATH=/src",
            "-e", "PYTHONIOENCODING=utf-8",
            "-e", f"FLOWDESK_INPUT={_to_container(input_path)}",
            "-e", f"FLOWDESK_OUTPUT={_to_container(output_path)}",
            "-e", f"FLOWDESK_OUTPUT_DIR={_to_container(output_dir)}",
            "-e", f"FLOWDESK_RUN_DIR={_to_container(run_dir)}",
        ]
        for k, v in env_vars.items():
            cmd += ["-e", f"{k}={v}"]
        cmd += [settings.runtime_image, "python", f"/src/{entry}"]

        def _cap(b: bytes, limit: int = 100_000) -> str:
            s = b.decode("utf-8", "replace")
            return s if len(s) <= limit else s[:limit] + "\n[...saida truncada...]"

        def _blocking():
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=timeout)
                return r.returncode, _cap(r.stdout), _cap(r.stderr)
            except subprocess.TimeoutExpired as e:
                # o cliente docker morreu, mas o container pode seguir vivo
                subprocess.run(["docker", "rm", "-f", name], capture_output=True)
                err = _cap(e.stderr or b"") + f"\n[runtime] Tempo limite de {timeout}s excedido."
                return 1, _cap(e.stdout or b""), err

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _blocking)
```

- [ ] **Step 4: Estender o dispatcher para `docker`**

Em `back/app/runtime/runner.py`, no método `_spawn`, trocar o corpo por:

```python
    async def _spawn(self, **kwargs) -> tuple[int, str, str]:
        backend = settings.execution_backend
        if backend == "local":
            return await self._spawn_local(**kwargs)
        if backend == "docker":
            return await self._spawn_docker(**kwargs)
        raise ValueError(f"execution_backend desconhecido: {backend!r}")
```

- [ ] **Step 5: Ajustar o teste de dispatch da Task 1**

Em `back/tests/test_spawn_dispatch.py`, o teste `test_backend_desconhecido_levanta` usava `"docker"` como valor desconhecido. Trocar `"docker"` por `"invalido"` na chamada `monkeypatch.setattr(settings, "execution_backend", "invalido", raising=False)` (agora `docker` é válido).

- [ ] **Step 6: Rodar o teste de contenção e ver passar**

Run: `cd back && /c/Users/mbrasiliense98/Documents/FlowDesk/back/.venv/Scripts/python.exe -m pytest tests/test_sandbox_docker.py tests/test_spawn_dispatch.py -v`
Expected: PASS (o teste de contenção prova network=BLOCKED, write_etc/src=BLOCKED, write_run=OK, segredos None; dispatch verde).

- [ ] **Step 7: Rodar a suíte inteira (sem regressão)**

Run: `cd back && /c/Users/mbrasiliense98/Documents/FlowDesk/back/.venv/Scripts/python.exe -m pytest -q`
Expected: PASS exceto a falha pré-existente `test_seed_heal`.

- [ ] **Step 8: Commit**

```bash
git add back/app/runtime/runner.py back/tests/test_sandbox_docker.py back/tests/test_spawn_dispatch.py
git commit -m "feat(s1): backend docker com rede off, FS read-only e limites"
```

---

## Notas de deploy (fora do escopo desta etapa, registradas)

- Virar o default para `docker` no alvo Linux depende do I2 (conversão portável de `.xls`), senão `.xls` malformado do Domínio regride.
- Publicar a imagem via GitHub Actions -> GHCR pinada por tag/digest; o VPS só faz `pull`. Não buildar no VPS, não auto-buildar no boot.
- Resolver o acesso ao daemon Docker pelo app no EasyPanel (montar `/var/run/docker.sock` dá root no host; alternativas rootless/sysbox ou worker dedicado) antes do Docker virar default no VPS.
- Em host Linux, o root de storage do projeto precisa ser gravável pelo uid 1000 do contêiner (chown ou uid alinhado). No Docker Desktop/Windows o bind é permissivo e isso não aparece.
