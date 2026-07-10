"""A1-1: aging e conciliação viraram templates próprios da galeria, alcançáveis
sob demanda (reference injetado quando a tarefa casa) e com exemplo funcional."""
import sys
import types
from pathlib import Path

import pandas as pd

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

from app.routers.templates import TEMPLATES
from app.services.reference_code import REF_LOW, reference_for_task


def _run_template(code: str, df: pd.DataFrame, tmp_path: Path):
    """Executa o code do template com um flowdesk_sdk falso, devolve o set_output."""
    captured: dict = {}
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    m = types.ModuleType("flowdesk_sdk")
    m.get_file = lambda *a, **k: "entrada"
    m.read_table = lambda p, **k: df.copy()
    m.output_path = lambda name: out_dir / name
    m.set_output = lambda d: captured.update(d)
    m.log = lambda *a, **k: None
    m.get_input = lambda: {}
    sys.modules["flowdesk_sdk"] = m
    try:
        exec(compile(code, "<template>", "exec"), {})
    finally:
        sys.modules.pop("flowdesk_sdk", None)
    return captured


# ---- alcançabilidade (o conhecimento chega à tarefa certa) ----

def test_tarefa_de_aging_casa_template_aging():
    ref = reference_for_task("relatorio de aging por faixa de atraso dos clientes")
    assert ref is not None and ref["score"] >= REF_LOW
    assert ref["template_key"] == "aging"
    assert "A vencer" in ref["reference"]


def test_tarefa_de_conciliacao_casa_template_conciliacao():
    ref = reference_for_task("conciliar lancamentos de debito e credito que se anulam")
    assert ref is not None and ref["score"] >= REF_LOW
    assert ref["template_key"] == "conciliacao-contabil"
    assert "VALOR ABSOLUTO" in ref["reference"]


# ---- o exemplo de cada template roda e produz o resultado esperado ----

def test_exemplo_aging_classifica_por_faixa(tmp_path):
    df = pd.DataFrame({
        "cliente": ["A", "B", "C"],
        "vencimento": ["01/01/2020", "31/12/2099", "15/06/2026"],
        "valor": [100.0, 200.0, 300.0],
    })
    out = _run_template(TEMPLATES["aging"]["code"], df, tmp_path)
    assert "arquivo_resultado" in out
    assert out["resumo"]["titulos"] == 3


def test_exemplo_conciliacao_pareia_que_zera(tmp_path):
    df = pd.DataFrame({"valor": [100.0, -100.0, 50.0]})
    out = _run_template(TEMPLATES["conciliacao-contabil"]["code"], df, tmp_path)
    assert out["resumo"]["conciliados"] == 2
    assert out["resumo"]["nao_conciliados"] == 1
