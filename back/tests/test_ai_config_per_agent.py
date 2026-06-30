from app.services import ai_config


def test_temp_parses_string_and_falls_back(monkeypatch):
    monkeypatch.setattr(ai_config, "_load", lambda: {"graph": {"agents": [
        {"id": "construtor", "temp": "0.2", "model": "gpt-4.1"},
        {"id": "nomeador", "temp": "padrão"},
    ]}})
    assert ai_config.get_temp("construtor") == 0.2
    assert ai_config.get_temp("nomeador", default=0.3) == 0.3   # "padrão" -> default
    assert ai_config.get_temp("inexistente", default=0.1) == 0.1


def test_agent_model_falls_back_to_shared(monkeypatch):
    monkeypatch.setattr(ai_config, "_load", lambda: {"model": "gpt-4o", "graph": {"agents": [
        {"id": "construtor", "model": "gpt-4.1"},
        {"id": "nomeador", "model": ""},
    ]}})
    assert ai_config.get_agent_model("construtor") == "gpt-4.1"
    assert ai_config.get_agent_model("nomeador") == "gpt-4o"   # vazio -> compartilhado
