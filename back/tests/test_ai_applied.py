from app.routers import ai


def test_orchestration_marcada_como_aplicada():
    assert ai.APPLIED["orchestration"] is True
    assert ai.APPLIED["assistant_prompt"] is True
    assert ai.APPLIED["shared_model"] is True


def test_seed_sem_descritor_e_planejador_colorido():
    graph = ai._default_graph()
    ids = {a["id"] for a in graph["agents"]}
    assert "descritor" not in ids
    assert "planejador" in ids
    planejador = next(a for a in graph["agents"] if a["id"] == "planejador")
    # planejador recebe a cor dedicada (não a default)
    assert planejador["c1"] == "#1f6fb2"
    assert "descritor" not in ai._COLORS
