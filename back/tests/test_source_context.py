from types import SimpleNamespace

from app.routers.chat import _format_sources


def _f(path, content, is_dir=False):
    return SimpleNamespace(path=path, content=content, is_dir=is_dir)


def test_format_sources_inclui_codigo_e_pula_vazios_e_dirs():
    out = _format_sources([
        _f("processar.py", "import pandas as pd\nset_output({})"),
        _f("vazio.py", "   "),
        _f("pasta", "", is_dir=True),
    ])
    assert "processar.py" in out
    assert "import pandas" in out
    assert "vazio.py" not in out
    assert "pasta" not in out


def test_format_sources_vazio_quando_nada():
    assert _format_sources([]) == ""
    assert _format_sources([_f("x.py", "", is_dir=False)]) == ""
