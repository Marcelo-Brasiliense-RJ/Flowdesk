from app.routers.classify import _perfil_contas


def test_perfil_contas_extrai_validas():
    profile = {"plano_de_contas": [
        {"codigo": "1.1", "nome": "Caixa"},
        {"codigo": "", "nome": "sem codigo"},
        {"nome": "sem chave codigo"},
    ]}
    out = _perfil_contas(profile)
    assert len(out) == 1
    assert out[0].codigo == "1.1" and out[0].nome == "Caixa"


def test_perfil_contas_vazio():
    assert _perfil_contas({}) == []
    assert _perfil_contas(None) == []
