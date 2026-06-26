"""O download deve achar o arquivo mesmo quando o script grava só o nome nu."""
import sys
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

from app.routers.published import _resolve_download_target


def test_resolve_acha_na_raiz(tmp_path):
    (tmp_path / "r.xlsx").write_text("x")
    assert _resolve_download_target(tmp_path, "output", "r.xlsx") == (tmp_path / "r.xlsx").resolve()


def test_resolve_cai_na_pasta_output(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    (out / "r.xlsx").write_text("x")
    # script gravou só "r.xlsx"; o arquivo real está em output/
    assert _resolve_download_target(tmp_path, "output", "r.xlsx") == (out / "r.xlsx").resolve()


def test_resolve_respeita_caminho_explicito(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    (out / "r.xlsx").write_text("x")
    assert _resolve_download_target(tmp_path, "output", "output/r.xlsx") == (out / "r.xlsx").resolve()
