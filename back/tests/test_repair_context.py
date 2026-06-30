from app.routers.repair import _plan_profile_context


def test_context_inclui_plano_e_perfil():
    ctx = _plan_profile_context({"regra_negocio": "conciliar"}, {"regime": "simples"})
    assert "regra_negocio" in ctx
    assert "conciliar" in ctx
    assert "simples" in ctx


def test_context_vazio_quando_nada():
    assert _plan_profile_context({}, {}) == ""
    assert _plan_profile_context(None, None) == ""


def test_context_so_plano():
    ctx = _plan_profile_context({"regra_negocio": "x"}, {})
    assert "regra_negocio" in ctx
    assert "PERFIL" not in ctx
