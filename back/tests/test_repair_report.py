from app.routers.repair import _execution_context


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
