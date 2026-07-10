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
    (src / "p.py").write_text(
        "open(__import__('os').environ['FLOWDESK_OUTPUT'],'w').write('{}')\n",
        encoding="utf-8",
    )
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
    rc, so, se = asyncio.run(mgr._spawn(**_kwargs(tmp_path)))
    assert rc == 0
