from app.routers.ai import _default_graph


def test_default_graph_is_pipeline_not_star():
    g = _default_graph()
    ids = {a["id"] for a in g["agents"]}
    assert "treinador" in ids  # Task 1 já adicionou o Treinador ao roster
    pairs = {(e["from"], e["to"]) for e in g["edges"]}
    # pipeline real: Planejador -> Construtor -> Nomeador
    assert ("planejador", "construtor") in pairs
    assert ("construtor", "nomeador") in pairs
    # Classificador alimenta o Construtor
    assert ("classificador", "construtor") in pairs
    # Assistente roteia para o Planejador (entrada do pipeline)
    assert ("assistente", "planejador") in pairs
    # NÃO é mais estrela: Assistente não liga direto no Construtor/Nomeador
    assert ("assistente", "construtor") not in pairs
    assert ("assistente", "nomeador") not in pairs


def test_treinador_edges_are_learn_kind():
    g = _default_graph()
    learn = [e for e in g["edges"] if e.get("kind") == "learn"]
    # Treinador melhora todos os agentes de build via arestas tracejadas
    assert learn, "esperava arestas 'learn' saindo do Treinador"
    assert all(e["from"] == "treinador" for e in learn)
