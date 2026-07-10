"""B4: resolução do alvo de download rejeita traversal, mantém o legítimo."""
import sys
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

from app.routers.published import _resolve_download_target


def test_traversal_rejeitado(tmp_path):
    assert _resolve_download_target(tmp_path, "out", "../../etc/passwd") is None
    assert _resolve_download_target(tmp_path, "out", "sub/../../x") is None


def test_relativo_legitimo(tmp_path):
    (tmp_path / "resultado.xlsx").write_text("x")
    alvo = _resolve_download_target(tmp_path, "out", "resultado.xlsx")
    assert alvo == (tmp_path / "resultado.xlsx").resolve()


def test_absoluto_sob_raiz_ok(tmp_path):
    # arquivo_resultado é um caminho absoluto sob a raiz do projeto: continua válido
    f = tmp_path / "out" / "r.xlsx"
    f.parent.mkdir()
    f.write_text("x")
    alvo = _resolve_download_target(tmp_path, "out", str(f))
    assert alvo == f.resolve()
