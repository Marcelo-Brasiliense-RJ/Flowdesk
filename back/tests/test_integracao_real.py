"""Integração com arquivos reais de cliente (existem só nesta máquina; pula no CI)."""
import sys
from pathlib import Path

import pytest

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

PDF = BACK / "storage" / "37" / "uploads" / "JBB GIG - EXTRATO BRADESCO 04.2026.pdf"
CONTAS = Path(r"C:\Users\mbrasiliense98\Downloads\Contas.xls")

pytestmark = pytest.mark.skipif(
    not (PDF.exists() and CONTAS.exists()), reason="arquivos reais ausentes"
)


def _mod(tmp_path, monkeypatch):
    from tests.test_extrato_dominio import _load_template_module
    return _load_template_module(tmp_path, monkeypatch)


def test_parser_fecha_ao_centavo(tmp_path, monkeypatch):
    m = _mod(tmp_path, monkeypatch)
    ext = m.parse_extrato(PDF)
    lanc = ext["lancamentos"]
    assert len(lanc) > 500
    assert ext["linhas_inconsistentes"] == 0
    calc = ext["saldo_anterior"] + sum(l["credito"] or 0 for l in lanc) - sum(l["debito"] or 0 for l in lanc)
    assert abs(calc - ext["saldo_final"]) < 0.01
    assert ext["periodo"] == ("01/04/2026", "30/04/2026")


def test_plano_de_contas_real(tmp_path, monkeypatch):
    m = _mod(tmp_path, monkeypatch)
    contas = m.carregar_plano(str(CONTAS))
    assert len(contas) > 500
    bradesco = [c for c in contas if "BRADESCO" in c["nome"].upper()]
    assert any(c["codigo"] == "9" for c in bradesco)
    assert all(c["codigo"].isdigit() for c in contas)
