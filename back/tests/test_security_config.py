"""Blindagem do SECRET_KEY: recusa subir em produção com o default público."""
import types

import pytest
from app.config import _DEFAULT_SECRET, validate_secret


def _settings(secret, db_url):
    # espelha só o que validate_secret lê (db_url é property em Settings)
    return types.SimpleNamespace(secret_key=secret, db_url=db_url)


def test_default_secret_em_producao_falha():
    with pytest.raises(RuntimeError):
        validate_secret(_settings(_DEFAULT_SECRET, "postgresql://x"))


def test_default_secret_em_dev_apenas_avisa():
    # SQLite (db_url vazio) não deve levantar
    validate_secret(_settings(_DEFAULT_SECRET, ""))


def test_secret_proprio_passa_em_producao():
    validate_secret(_settings("um-segredo-longo-e-aleatorio", "postgresql://x"))
