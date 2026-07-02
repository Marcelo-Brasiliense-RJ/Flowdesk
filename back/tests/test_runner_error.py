from app.runtime.runner import _last_error_line


def test_last_error_line_prefere_a_excecao():
    tb = (
        "Traceback (most recent call last):\n"
        '  File "processar.py", line 12, in <module>\n'
        '    raise ValueError("PDF invalido: sem paginas legiveis")\n'
        "ValueError: PDF invalido: sem paginas legiveis\n"
    )
    assert _last_error_line(tb) == "ValueError: PDF invalido: sem paginas legiveis"


def test_last_error_line_cai_na_ultima_linha_quando_nao_ha_excecao():
    assert _last_error_line("aviso qualquer\nmensagem final") == "mensagem final"


def test_last_error_line_vazio_tem_mensagem_padrao():
    msg = _last_error_line("")
    assert msg and "falhou" in msg.lower()
