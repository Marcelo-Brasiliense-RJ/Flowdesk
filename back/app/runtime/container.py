"""S1: monta o comando de container efêmero e isolado para rodar o script.

A montagem do comando é pura (sem chamar Docker) para as garantias de
isolamento serem testáveis por unidade. A execução fica em run_in_container().
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def container_env(env_vars: dict) -> dict[str, str]:
    """Ambiente do processo DENTRO do container. NÃO herda nada do host: a
    imagem Linux traz seu próprio PATH e ambiente; injetar o env do host
    (Windows) quebraria o container e vazaria detalhes do servidor. Só as
    EnvVar do projeto + os FLOWDESK_* apontando para os caminhos internos."""
    env = {k: str(v) for k, v in env_vars.items()}
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


def docker_available() -> bool:
    exe = shutil.which("docker")
    if not exe:
        return False
    try:
        r = subprocess.run([exe, "info"], capture_output=True, timeout=15)
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
    input_path = run_dir / "input.json"
    if not input_path.exists():
        return
    data = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return
    # Só faz staging de arquivos DENTRO da raiz do projeto (run_dir = <root>/runs/
    # <id>). Sem isso, um input malicioso citando um caminho absoluto do servidor
    # (ex.: .env, flowdesk.db) faria o arquivo ser copiado para dentro do sandbox
    # e devolvido na saída. Ver B2 do dossiê (get_file heurístico).
    project_root = run_dir.parent.parent.resolve()
    in_dir = run_dir / "in"
    changed = False
    for key, value in list(data.items()):
        if isinstance(value, str):
            p = Path(value)
            if not (p.is_absolute() and p.is_file()):
                continue
            resolved = p.resolve()
            if project_root not in resolved.parents:
                continue  # fora da raiz do projeto: não expõe ao sandbox
            in_dir.mkdir(exist_ok=True)
            shutil.copy2(resolved, in_dir / p.name)
            data[key] = f"/run/in/{p.name}"
            changed = True
    if changed:
        input_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


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
