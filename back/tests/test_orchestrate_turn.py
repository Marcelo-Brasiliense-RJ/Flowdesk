from app.routers import orchestrator


def test_planning_runs_planejador(monkeypatch):
    monkeypatch.setattr(orchestrator, "run_planejador", lambda h, p, c="": {
        "message": "oi", "questions": [{"id": "x"}], "plan": {"fonte": {"formato": "xlsx"}},
        "missing": ["gatilho"], "contabil": False, "profile_questions": [{"id": "regime"}]})
    res = orchestrator.orchestrate_turn(phase="", plan={}, profile={}, intent="nova",
                                        user_confirmed=False, history=[], project_context="")
    assert res["mode"] == "planning" and res["phase"] == "planning"
    assert res["text"] == "oi"   # a mensagem do Planejador vira o texto da bolha
    assert res["plan"]["fonte"]["formato"] == "xlsx"
    ids = [q["id"] for q in res["questions"]]
    assert "x" in ids and "regime" in ids   # profile_questions juntadas


def test_planning_passes_context_to_planejador(monkeypatch):
    captured = {}

    def fake_pj(h, p, c=""):
        captured["ctx"] = c
        return {"message": "", "questions": [{"id": "x"}], "plan": {}, "missing": ["gatilho"],
                "contabil": False, "profile_questions": []}

    monkeypatch.setattr(orchestrator, "run_planejador", fake_pj)
    orchestrator.orchestrate_turn(phase="", plan={}, profile={}, intent="nova",
                                  user_confirmed=False, history=[], project_context="COLUNAS: Data, Valor")
    assert "COLUNAS" in captured["ctx"]   # Planejador recebe o contexto dos arquivos


def test_planning_converges_to_build_when_confirmed_and_complete(monkeypatch):
    monkeypatch.setattr(orchestrator, "run_planejador", lambda h, p, c="": {
        "message": "tudo certo", "questions": [], "plan": FULL, "missing": [],
        "contabil": False, "profile_questions": []})
    monkeypatch.setattr(orchestrator, "run_construtor", lambda p, pr, ctx: {
        "message": "montado", "actions": [{"kind": "create_file", "path": "x.py", "content": "set_output({})"}]})
    monkeypatch.setattr(orchestrator, "run_nomeador", lambda p, code: {"name": "N", "description": "D"})
    res = orchestrator.orchestrate_turn(phase="planning", plan={}, profile={}, intent="nova",
                                        user_confirmed=True, history=[], project_context="")
    assert res["mode"] == "building" and res["phase"] == "done"
    assert res["actions"][0]["path"] == "x.py"


FULL = {"fonte": {"formato": "xlsx"}, "regra_negocio": "x",
        "saida": {"formato": "xlsx"}, "gatilho": "manual"}


def test_building_runs_construtor_and_nomeador(monkeypatch):
    monkeypatch.setattr(orchestrator, "run_construtor", lambda p, pr, ctx: {
        "message": "feito", "actions": [{"kind": "create_file", "path": "x.py", "content": "set_output({})"}]})
    monkeypatch.setattr(orchestrator, "run_nomeador", lambda p, code: {"name": "Conciliação", "description": "desc"})
    res = orchestrator.orchestrate_turn(phase="planning", plan=FULL, profile={}, intent="nova",
                                        user_confirmed=True, history=[], project_context="")
    assert res["mode"] == "building" and res["phase"] == "done"
    assert res["actions"][0]["path"] == "x.py"
    assert res["suggested_name"] == "Conciliação"
    assert res["plan_for_review"] == res["plan"]


def test_building_enriches_when_contabil(monkeypatch):
    called = {}

    def fake_enrich(p, pr):
        called["e"] = True
        return {"plan": {**p, "saida": {"contrato": "Domínio"}}, "profile": {"regime": "simples"}, "avisos": []}

    monkeypatch.setattr(orchestrator, "enrich_accounting", fake_enrich)
    monkeypatch.setattr(orchestrator, "run_construtor", lambda p, pr, ctx: {"message": "ok", "actions": []})
    monkeypatch.setattr(orchestrator, "run_nomeador", lambda p, code: {"name": "N", "description": "D"})
    plan = {**FULL, "contabil": True}
    res = orchestrator.orchestrate_turn(phase="planning", plan=plan, profile={}, intent="nova",
                                        user_confirmed=True, history=[], project_context="")
    assert called.get("e") is True
    assert res["profile"]["regime"] == "simples"


def test_duvida_is_answer():
    res = orchestrator.orchestrate_turn(phase="planning", plan={}, profile={}, intent="duvida",
                                        user_confirmed=False, history=[], project_context="")
    assert res["mode"] == "answer"


def test_incomplete_plan_stays_planning(monkeypatch):
    monkeypatch.setattr(orchestrator, "run_planejador", lambda h, p, c="": {
        "message": "", "questions": [], "plan": p, "missing": ["gatilho"], "contabil": False, "profile_questions": []})
    res = orchestrator.orchestrate_turn(phase="planning", plan={"fonte": {"formato": "xlsx"}}, profile={},
                                        intent="nova", user_confirmed=True, history=[], project_context="")
    assert res["mode"] == "planning"   # incompleto, não sela mesmo confirmado
