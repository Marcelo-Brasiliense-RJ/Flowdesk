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
