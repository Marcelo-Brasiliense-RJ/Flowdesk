from app.services import ai_config


def test_apply_prompt_writes_to_graph_node_when_graph_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_config, "_PATH", tmp_path / "ai_config.json")
    ai_config.set_graph({"agents": [{"id": "construtor", "prompt": "velho"}], "edges": []})
    ai_config.apply_prompt("construtor", "novo prompt")
    # get_prompt lê o grafo primeiro; tem que refletir o novo valor
    assert ai_config.get_prompt("construtor", "DEFAULT") == "novo prompt"


def test_apply_prompt_falls_back_to_override_without_graph(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_config, "_PATH", tmp_path / "ai_config.json")
    ai_config.apply_prompt("planejador", "prompt override")
    assert ai_config.get_prompt("planejador", "DEFAULT") == "prompt override"
