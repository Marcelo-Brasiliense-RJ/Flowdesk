"""S1: o subprocesso que roda o script gerado NAO pode herdar os segredos do
servidor (SECRET_KEY, OPENAI_API_KEY, SMTP_PASSWORD, SUPABASE_DB_URL). Deve
receber apenas as EnvVar do projeto, os caminhos FLOWDESK_* e o minimo de
ambiente do SO para o interpretador subir."""
import asyncio
import json
from pathlib import Path

from app.runtime import runner

_PROBE = (
    "import os, json\n"
    "print(json.dumps({\n"
    "  'SECRET_KEY': os.environ.get('SECRET_KEY'),\n"
    "  'OPENAI_API_KEY': os.environ.get('OPENAI_API_KEY'),\n"
    "  'SMTP_PASSWORD': os.environ.get('SMTP_PASSWORD'),\n"
    "  'SUPABASE_DB_URL': os.environ.get('SUPABASE_DB_URL'),\n"
    "  'PROJ_VAR': os.environ.get('PROJ_VAR'),\n"
    "  'RUN_DIR': os.environ.get('FLOWDESK_RUN_DIR'),\n"
    "}))\n"
)


def _run_probe(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (src / "probe.py").write_text(_PROBE, encoding="utf-8")

    mgr = runner.RuntimeManager()
    rc, out, err = asyncio.run(
        mgr._spawn(
            src_dir=src,
            cwd=run_dir,
            entry="probe.py",
            input_path=run_dir / "input.json",
            output_path=run_dir / "output.json",
            output_dir=out_dir,
            run_dir=run_dir,
            env_vars={"PROJ_VAR": "valor-do-projeto"},
            timeout=30,
        )
    )
    return rc, out, err


def test_subprocesso_nao_ve_segredos_do_servidor(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "servidor-super-secreto")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-servidor-leak")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-leak")
    monkeypatch.setenv("SUPABASE_DB_URL", "postgres://leak")

    rc, out, err = _run_probe(tmp_path)

    assert rc == 0, f"o interpretador nao subiu (stderr={err!r})"
    seen = json.loads(out)
    assert seen["SECRET_KEY"] is None
    assert seen["OPENAI_API_KEY"] is None
    assert seen["SMTP_PASSWORD"] is None
    assert seen["SUPABASE_DB_URL"] is None


def test_subprocesso_ve_envvar_do_projeto_e_flowdesk(tmp_path):
    rc, out, err = _run_probe(tmp_path)

    assert rc == 0, f"o interpretador nao subiu (stderr={err!r})"
    seen = json.loads(out)
    assert seen["PROJ_VAR"] == "valor-do-projeto"
    assert seen["RUN_DIR"] == str(tmp_path / "run")
