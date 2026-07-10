"""B1: _attachment_context lê anexos via storage.read_table (contrato do .xls
legado), não pd.read_excel direto."""
import sys
from pathlib import Path

import pandas as pd

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

from app.routers import chat
from app.services import storage


def test_attachment_usa_read_table(monkeypatch, tmp_path):
    (tmp_path / "extrato.xls").write_bytes(b"conteudo-xls-legado")
    monkeypatch.setattr(storage, "project_root", lambda pid: tmp_path)
    chamou = {}
    def fake_read_table(path, **k):
        chamou["path"] = str(path)
        return pd.DataFrame({"Data": ["01/04"], "Valor": [10]})
    monkeypatch.setattr(storage, "read_table", fake_read_table)

    ctx = chat._attachment_context(1, ["extrato.xls"])
    assert chamou.get("path", "").endswith("extrato.xls")   # passou pelo read_table
    assert "['Data', 'Valor']" in ctx                        # colunas reais no contexto
    assert "não foi possível ler" not in ctx
