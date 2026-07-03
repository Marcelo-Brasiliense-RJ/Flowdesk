from app.services import treinador


def _isola_store(tmp_path, monkeypatch):
    """Aponta o store do Treinador para um dir temporário (não toca no real)."""
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")


def test_record_repair_grava_e_deduplica(tmp_path, monkeypatch):
    _isola_store(tmp_path, monkeypatch)
    ok = treinador.record_repair(101, "erro X", "causa X", "corrige com read_table")
    assert ok is True
    # mesmo (project_id, symptom, fix) não grava de novo
    assert treinador.record_repair(101, "erro X", "causa Y", "corrige com read_table") is False
    items = treinador._repairs()
    assert len(items) == 1
    assert items[0]["fix"] == "corrige com read_table"
    assert items[0]["fingerprint"]


def test_record_repair_nunca_lanca(tmp_path, monkeypatch):
    _isola_store(tmp_path, monkeypatch)
    # tipos inesperados não podem derrubar (é hook best-effort fora do caminho crítico)
    assert treinador.record_repair(101, None, None, None) in (True, False)
