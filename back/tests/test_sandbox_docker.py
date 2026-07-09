"""S1 parte 2: contencao do backend docker. Skip se docker/imagem ausentes."""
import asyncio
import json
import shutil
import subprocess

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
