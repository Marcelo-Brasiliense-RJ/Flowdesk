"""Testa os helpers novos do SDK executando-o como módulo isolado."""
import json
import sys
import importlib.util
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))


def _load_sdk(tmp_path, monkeypatch):
    """Materializa o _SDK_SOURCE num arquivo e importa com env de runtime fake."""
    from app.services.storage import _SDK_SOURCE
    sdk_file = tmp_path / "flowdesk_sdk.py"
    sdk_file.write_text(_SDK_SOURCE, encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (tmp_path / "input.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("FLOWDESK_INPUT", str(tmp_path / "input.json"))
    monkeypatch.setenv("FLOWDESK_OUTPUT", str(tmp_path / "output.json"))
    monkeypatch.setenv("FLOWDESK_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("FLOWDESK_RUN_DIR", str(run_dir))
    spec = importlib.util.spec_from_file_location("flowdesk_sdk_t", sdk_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, run_dir


def test_progress_appends_jsonl(tmp_path, monkeypatch):
    sdk, run_dir = _load_sdk(tmp_path, monkeypatch)
    sdk.progress("Lendo extrato", "564 lançamentos")
    sdk.progress("Aplicando regras")
    lines = (run_dir / "progress.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["etapa"] == "Lendo extrato"
    assert first["detalhe"] == "564 lançamentos"


def test_get_table_reads_materialized_json(tmp_path, monkeypatch):
    sdk, run_dir = _load_sdk(tmp_path, monkeypatch)
    (run_dir / "tables.json").write_text(
        json.dumps({"regras_classificacao": [{"padrao": "TARIFA BANCARIA", "conta_codigo": "999"}]}),
        encoding="utf-8",
    )
    rows = sdk.get_table("regras_classificacao")
    assert rows[0]["conta_codigo"] == "999"
    assert sdk.get_table("inexistente") == []


def test_read_table_xlsx_and_csv(tmp_path, monkeypatch):
    import pandas as pd
    sdk, _ = _load_sdk(tmp_path, monkeypatch)
    df0 = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    xlsx = tmp_path / "t.xlsx"
    df0.to_excel(xlsx, index=False)
    csv = tmp_path / "t.csv"
    df0.to_csv(csv, index=False)
    assert sdk.read_table(str(xlsx)).shape == (2, 2)
    assert sdk.read_table(str(csv)).shape == (2, 2)


def test_set_output_preserva_numpy_como_numero(tmp_path, monkeypatch):
    import numpy as np
    sdk, _ = _load_sdk(tmp_path, monkeypatch)
    sdk.set_output({"total": np.int64(1700), "frac": np.float64(2.5)})
    saved = json.loads((tmp_path / "output.json").read_text(encoding="utf-8"))
    assert saved["total"] == 1700 and isinstance(saved["total"], int)
    assert saved["frac"] == 2.5 and isinstance(saved["frac"], float)
