from app.routers.repair import _execution_context, _execution_report_snapshot, _repair_action_payload
from app.schemas import RepairProposeOut


class _Exec:
    def __init__(self, stderr="", output_data=None):
        self.stderr = stderr
        self.output_data = output_data or {}


def test_contexto_inclui_stderr_e_resumo_do_output():
    ex = _Exec(stderr="Traceback: KeyError 'Valor'",
               output_data={"resumo": "10 casados, 3 nao casados", "arquivo_resultado": "x.xlsx"})
    ctx = _execution_context(ex)
    assert "KeyError 'Valor'" in ctx
    assert "10 casados, 3 nao casados" in ctx


def test_contexto_em_falso_sucesso_sem_stderr():
    # rodou sem erro, mas o resultado esta errado: o contexto ainda traz o output
    ex = _Exec(stderr="", output_data={"resumo": "0 casados"})
    ctx = _execution_context(ex)
    assert "0 casados" in ctx


def test_snapshot_do_reporte():
    class E:
        id = "abc"
        status = "success"
        stderr = ""
        output_data = {"resumo": "10 casados", "arquivo_resultado": "r.xlsx", "_oculto": 1}
        input_data = {"arquivo1": "uploads/extrato.xlsx", "arquivo2": "uploads/razao.xlsx"}
    snap = _execution_report_snapshot(E())
    assert snap["execution_id"] == "abc"
    assert snap["status"] == "success"
    assert snap["resumo"] == "10 casados"
    assert snap["input_files"] == ["extrato.xlsx", "razao.xlsx"]
    assert "_oculto" not in snap["output_keys"]


def test_repair_action_payload_com_correcao():
    proposal = RepairProposeOut(
        diagnosis="Entendi o problema.",
        change_summary="Vou ajustar a leitura.",
        fixed_code="from flowdesk_sdk import get_file, set_output\n# corrigido\n",
        has_changes=True,
    )
    payload = _repair_action_payload("script.py", proposal)
    assert payload == {
        "path": "script.py",
        "content": "from flowdesk_sdk import get_file, set_output\n# corrigido\n",
    }


def test_repair_action_payload_sem_correcao():
    proposal = RepairProposeOut(
        diagnosis="Não entendi o problema.",
        change_summary="",
        fixed_code="",
        has_changes=False,
    )
    assert _repair_action_payload("script.py", proposal) is None
