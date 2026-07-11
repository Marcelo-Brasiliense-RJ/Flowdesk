"""Rate limiter em processo: janela fixa, 429 ao estourar, escopo por chave."""
import pytest
from fastapi import HTTPException
from app import ratelimit


def setup_function():
    ratelimit.reset()


def test_permite_ate_o_limite_e_bloqueia_depois():
    allowed = [ratelimit._check("k", 3, 60)[0] for _ in range(4)]
    assert allowed == [True, True, True, False]


def test_chaves_distintas_nao_compartilham_balde():
    assert ratelimit._check("a", 1, 60)[0] is True
    assert ratelimit._check("b", 1, 60)[0] is True  # outra chave, balde próprio
    assert ratelimit._check("a", 1, 60)[0] is False  # 'a' já estourou


def test_enforce_levanta_429_com_retry_after():
    ratelimit.enforce("login:email:x", 1, 60)  # 1º passa
    with pytest.raises(HTTPException) as exc:
        ratelimit.enforce("login:email:x", 1, 60)  # 2º estoura
    assert exc.value.status_code == 429
    assert "Retry-After" in exc.value.headers


def test_janela_expira_e_reseta(monkeypatch):
    t = {"now": 1000.0}
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: t["now"])
    assert ratelimit._check("w", 1, 10)[0] is True
    assert ratelimit._check("w", 1, 10)[0] is False  # dentro da janela
    t["now"] += 11  # passou a janela
    assert ratelimit._check("w", 1, 10)[0] is True  # reabriu
