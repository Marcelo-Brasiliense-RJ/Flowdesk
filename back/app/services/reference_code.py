"""Seleciona o código de referência da galeria mais parecido com a tarefa, para
injetar como few-shot no Construtor (e semente determinística em casamento claro)."""
from __future__ import annotations

import re
import unicodedata

from ..routers.templates import TEMPLATES

REF_LOW = 2   # limiar mínimo para injetar como referência (few-shot)
REF_HIGH = 4  # limiar de casamento claro (semente determinística)

_STOP = {"para", "com", "dos", "das", "uma", "que", "por", "gerar", "arquivo", "dados"}


def _norm(s: str) -> str:
    """Minúsculas sem acentos, para 'bancário' casar com 'bancario'."""
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _tokens(s: str) -> set:
    toks = re.findall(r"[a-z0-9]{3,}", _norm(s))
    return {t for t in toks if t not in _STOP}


def reference_for_task(task_text: str):
    tt = _tokens(task_text)
    if not tt:
        return None
    best = None
    for key, tpl in TEMPLATES.items():
        base = _tokens(tpl["name"] + " " + tpl["description"])
        score = len(tt & base)
        if best is None or score > best["score"]:
            best = {"template_key": key, "code": tpl["code"], "score": score}
    if best is None or best["score"] < REF_LOW:
        return None
    return best
