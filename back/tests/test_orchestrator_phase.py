from app.routers.orchestrator import next_phase
from app.services.plan_schema import Plan, PlanFonte, PlanSaida

FULL = Plan(
    fonte=PlanFonte(formato="xlsx"),
    regra_negocio="x",
    saida=PlanSaida(formato="xlsx"),
    gatilho="manual",
)


def test_nova_enters_planning():
    assert next_phase("", "nova", Plan(), False) == "planning"


def test_planning_seals_only_when_complete_and_confirmed():
    assert next_phase("planning", "nova", Plan(), True) == "planning"      # incompleto
    assert next_phase("planning", "nova", FULL, False) == "planning"       # não confirmado
    assert next_phase("planning", "nova", FULL, True) == "building"        # sela


def test_ajuste_goes_straight_to_building():
    assert next_phase("done", "ajuste", FULL, False) == "building"


def test_duvida_keeps_phase():
    assert next_phase("planning", "duvida", Plan(), False) == "planning"
    assert next_phase("done", "duvida", FULL, False) == "done"
