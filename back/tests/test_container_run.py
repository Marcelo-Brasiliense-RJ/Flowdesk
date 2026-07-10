import json
import sys
from pathlib import Path

import pytest

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

import subprocess

from app.runtime.container import _container_name, docker_available, run_in_container

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


def test_timeout_nao_deixa_container_orfao(tmp_path):
    src, run, out = _prep(tmp_path, "import time\ntime.sleep(30)\n")
    rc, so, se = run_in_container(
        src_dir=src, output_dir=out, run_dir=run, entry="proc.py",
        env_vars={}, timeout=3,
    )
    assert rc == 1
    assert "Tempo limite" in se
    ps = subprocess.run(
        ["docker", "ps", "--filter", f"name={_container_name(run)}", "--format", "{{.Names}}"],
        capture_output=True, text=True, timeout=30,
    )
    assert _container_name(run) not in ps.stdout  # container encerrado, sem órfão


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


def test_staging_ignora_arquivo_fora_da_raiz_do_projeto(tmp_path):
    # run_dir = <root>/runs/<id>; a raiz do projeto é run_dir.parent.parent
    from app.runtime.container import _stage_inputs

    root = tmp_path / "proj"
    run = root / "runs" / "exec1"
    run.mkdir(parents=True)
    segredo = tmp_path / "segredo.env"  # FORA da raiz do projeto
    segredo.write_text("SECRET_KEY=vaza", encoding="utf-8")
    (run / "input.json").write_text(
        json.dumps({"arquivo": str(segredo)}), encoding="utf-8"
    )

    _stage_inputs(run)

    data = json.loads((run / "input.json").read_text(encoding="utf-8"))
    assert data["arquivo"] == str(segredo)  # caminho NÃO reescrito
    assert not (run / "in").exists()  # nada copiado para dentro do sandbox


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
    assert (run / "in" / "arquivo" / "planilha.csv").exists()
    saida = json.loads((run / "output.json").read_text(encoding="utf-8"))
    assert saida["linhas"] == 1
