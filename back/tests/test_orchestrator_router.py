from app.routers import orchestrator


def test_route_no_workflow_creation_is_nova(monkeypatch):
    monkeypatch.setattr(orchestrator.settings, "openai_api_key", "")
    assert orchestrator.route_intent("quero conciliar duas planilhas", has_workflow=False) == "nova"


def test_route_with_workflow_edit_is_ajuste(monkeypatch):
    monkeypatch.setattr(orchestrator.settings, "openai_api_key", "")
    assert orchestrator.route_intent("muda a coluna de data para dd/mm/aaaa", has_workflow=True) == "ajuste"


def test_route_question_is_duvida(monkeypatch):
    monkeypatch.setattr(orchestrator.settings, "openai_api_key", "")
    assert orchestrator.route_intent("o que essa automação faz?", has_workflow=True) == "duvida"


def test_route_no_workflow_question_is_duvida(monkeypatch):
    monkeypatch.setattr(orchestrator.settings, "openai_api_key", "")
    assert orchestrator.route_intent("como funciona o upload?", has_workflow=False) == "duvida"
