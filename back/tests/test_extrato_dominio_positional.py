from app.routers.templates import TEMPLATES


def test_extrato_dominio_usa_get_file_posicional():
    code = TEMPLATES["extrato-dominio"]["code"]
    assert "get_file(0)" in code          # PDF pelo índice
    assert "get_file(1)" in code          # plano de contas pelo índice
