from app.services.plan_schema import Plan, PlanFonte, PlanSaida, plan_missing_fields, plan_is_complete

def test_empty_plan_lists_all_critical_fields():
    assert plan_missing_fields(Plan()) == ["fonte.formato", "regra_negocio", "saida.formato", "gatilho"]
    assert plan_is_complete(Plan()) is False

def test_full_plan_is_complete():
    p = Plan(
        fonte=PlanFonte(formato="xlsx"),
        regra_negocio="somar valores por cliente",
        saida=PlanSaida(formato="xlsx"),
        gatilho="manual",
    )
    assert plan_missing_fields(p) == []
    assert plan_is_complete(p) is True

def test_partial_plan_reports_only_missing():
    p = Plan(fonte=PlanFonte(formato="csv"), gatilho="manual")
    assert plan_missing_fields(p) == ["regra_negocio", "saida.formato"]
