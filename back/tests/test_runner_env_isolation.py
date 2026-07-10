"""S1: o subprocesso de execução não pode herdar os segredos do servidor.

O script rodado é gerado por IA e editável; se ele enxergar SECRET_KEY ou
OPENAI_API_KEY do ambiente do servidor, pode forjar tokens de admin ou
exfiltrar credenciais. Só as EnvVar do projeto (mais o mínimo de SO para o
Python iniciar) podem chegar ao subprocesso.
"""
import asyncio
import json
import sys
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

from app.runtime.runner import RuntimeManager


def test_subprocess_nao_enxerga_segredos_do_servidor(tmp_path, monkeypatch):
    # Segredos do servidor presentes no ambiente do processo web.
    monkeypatch.setenv("SECRET_KEY", "assina-jwt-de-admin")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-vazou")
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://vazou")

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    inp = run_dir / "input.json"
    inp.write_text("{}", encoding="utf-8")
    out = run_dir / "output.json"

    # Script hostil: tenta ler os segredos do ambiente e grava o que enxergou.
    (src_dir / "leak.py").write_text(
        "import os, json\n"
        "chaves = ['SECRET_KEY', 'OPENAI_API_KEY', 'SUPABASE_DB_URL', 'PROJ_TOKEN']\n"
        "visto = {k: os.environ.get(k) for k in chaves}\n"
        "open(os.environ['FLOWDESK_OUTPUT'], 'w', encoding='utf-8').write(json.dumps(visto))\n",
        encoding="utf-8",
    )

    mgr = RuntimeManager()
    rc, stdout, stderr = asyncio.run(
        mgr._spawn(
            src_dir=src_dir,
            cwd=run_dir,
            entry="leak.py",
            input_path=inp,
            output_path=out,
            output_dir=run_dir,
            run_dir=run_dir,
            env_vars={"PROJ_TOKEN": "visivel"},
            timeout=30,
        )
    )

    # Prova que o Python iniciou com o ambiente mínimo (allowlist de SO suficiente).
    assert rc == 0, f"o script nao rodou; stderr={stderr!r}"

    visto = json.loads(out.read_text(encoding="utf-8"))
    # EnvVar do projeto chega ao subprocesso.
    assert visto["PROJ_TOKEN"] == "visivel"
    # Segredos do servidor NÃO vazam.
    assert visto["SECRET_KEY"] is None
    assert visto["OPENAI_API_KEY"] is None
    assert visto["SUPABASE_DB_URL"] is None
