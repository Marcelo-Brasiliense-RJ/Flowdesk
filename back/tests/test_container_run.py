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


def test_staging_copia_upload_e_reescreve_caminho(tmp_path):
    upload = tmp_path / "_uploads" / "abc"
    upload.mkdir(parents=True)
    arq = upload / "planilha.csv"
    arq.write_text("a,b\n1,2\n", encoding="utf-8")
    src, run, out = _prep(
        tmp_path,
        "import os, json, pandas as pd\n"
        "caminho = json.load(open(os.environ['FLOWDESK_INPUT']))['arquivo']\n"
        "df = pd.read_csv(caminho)\n"
        "open(os.environ['FLOWDESK_OUTPUT'],'w').write(json.dumps({'linhas':len(df), 'caminho':caminho}))\n",
        input_data={"arquivo": str(arq)},
    )
    rc, so, se = run_in_container(
        src_dir=src, output_dir=out, run_dir=run, entry="proc.py",
        env_vars={}, timeout=60,
    )
    assert rc == 0, se
    assert (run / "in" / "planilha.csv").exists()
    saida = json.loads((run / "output.json").read_text(encoding="utf-8"))
    assert saida["linhas"] == 1
