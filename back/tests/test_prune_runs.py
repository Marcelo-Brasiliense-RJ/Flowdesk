"""I3: retenção de pastas de execução (runs/<id>)."""
import os
import sys
import time
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

from app.services import storage


def test_prune_remove_antigas_mantem_recentes(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "project_root", lambda pid: tmp_path)
    runs = tmp_path / "runs"
    runs.mkdir()
    velha = runs / "velha"; velha.mkdir()
    nova = runs / "nova"; nova.mkdir()
    antigo = time.time() - 40 * 86400
    os.utime(velha, (antigo, antigo))

    removed = storage.prune_runs(1, max_age_days=30)

    assert removed == 1
    assert not velha.exists()
    assert nova.exists()


def test_prune_zero_dias_nao_remove(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "project_root", lambda pid: tmp_path)
    runs = tmp_path / "runs"; runs.mkdir()
    (runs / "x").mkdir()
    assert storage.prune_runs(1, max_age_days=0) == 0
    assert (runs / "x").exists()
