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
    assert f"{tmp_path / 'run'}:/run:rw" in s
    assert f"{tmp_path / 'src'}:/src:ro" in s
    assert f"{tmp_path / 'out'}:/out:rw" in s
    assert "PROJ_TOKEN=x" in s
    assert "--runtime" not in s
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
