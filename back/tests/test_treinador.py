from app.services import treinador


def test_store_reads_empty_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    assert treinador._examples() == []
    assert treinador._proposals() == []
    assert treinador._repairs() == []


def test_treinador_has_default_prompt():
    assert isinstance(treinador.TREINADOR_PROMPT, str)
    assert treinador.TREINADOR_PROMPT.strip()
