from app.services import ai_config


def test_defaults_por_agente(monkeypatch):
    # sem grafo salvo e sem override de modelo compartilhado
    monkeypatch.setattr(ai_config, "_load", lambda: {})
    monkeypatch.setattr(ai_config, "get_graph", lambda: None)
    assert ai_config.get_agent_model("construtor") == "gpt-5.3-codex"
    assert ai_config.get_agent_model("reparador") == "gpt-4.1"
    assert ai_config.get_agent_model("treinador") == "gpt-4.1"
    # agente sem default cai no modelo compartilhado
    assert ai_config.get_agent_model("planejador") == ai_config.get_model()
