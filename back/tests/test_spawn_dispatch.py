"""S1: o _spawn despacha por settings.execution_backend."""
import asyncio

import pytest

from app.config import settings
from app.runtime import runner


def test_backend_local_chama_spawn_local(monkeypatch):
    monkeypatch.setattr(settings, "execution_backend", "local", raising=False)
    mgr = runner.RuntimeManager()
    chamado = {}

    async def fake_local(**kwargs):
        chamado["local"] = kwargs
        return (0, "ok", "")

    monkeypatch.setattr(mgr, "_spawn_local", fake_local)
    rc, out, err = asyncio.run(mgr._spawn(entry="x.py", env_vars={}))
    assert rc == 0 and out == "ok"
    assert chamado["local"]["entry"] == "x.py"


def test_backend_desconhecido_levanta(monkeypatch):
    monkeypatch.setattr(settings, "execution_backend", "invalido", raising=False)
    mgr = runner.RuntimeManager()
    with pytest.raises(ValueError, match="execution_backend"):
        asyncio.run(mgr._spawn(entry="x.py", env_vars={}))
