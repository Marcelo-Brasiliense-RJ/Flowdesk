"""Camada única de chamada ao provedor de IA (cliente OpenAI-compatível).

Ponto único que decide COMO falar com o modelo, para que trocar o modelo
compartilhado no builder não quebre nenhum fluxo:

- Modelos de raciocínio (``gpt-5*``, ``o3*``, ``o4*``, ``*codex``) usam a
  Responses API, que NÃO aceita ``temperature`` nem ``response_format`` no
  formato do chat.completions. O JSON, quando exigido, é garantido pelo próprio
  prompt do agente (que já pede "SOMENTE JSON").
- Os demais modelos seguem em ``chat.completions``, com ``temperature`` e
  ``response_format`` normais.

Antes disto cada router repetia o ``client.chat.completions.create(...)`` com
``temperature`` fixa; um GPT-5 selecionado no dropdown quebrava todos eles.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterator

from ..config import settings

# gpt-5 (qualquer subversão), o3/o4 e variantes codex são de raciocínio.
_REASONING_MODEL = re.compile(r"gpt-5|o3|o4|codex", re.I)

# Piso de tokens abaixo do qual um teto de saída não é repassado a um modelo de
# raciocínio: ele gastaria o orçamento "pensando" e devolveria resposta vazia.
_REASONING_MIN_OUTPUT = 256


def is_reasoning(model: str) -> bool:
    """True se o modelo exige a Responses API (raciocínio/codex)."""
    return bool(_REASONING_MODEL.search(model or ""))


def _client():
    from openai import OpenAI

    return OpenAI(api_key=settings.openai_api_key)


def complete(
    model: str,
    messages: list[dict],
    *,
    temperature: float | None = None,
    json_mode: bool = False,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
) -> str:
    """Uma chamada, devolve o texto da resposta. Roteia raciocínio x chat.

    ``reasoning_effort`` (low|medium|high) só vale para modelos de raciocínio: é o
    esforço de "pensamento" da Responses API. Menor esforço = resposta mais rápida
    (troca latência por profundidade). Ignorado em chat.completions."""
    client = _client()
    if is_reasoning(model):
        kw: dict = {"model": model, "input": messages}
        if max_tokens and max_tokens >= _REASONING_MIN_OUTPUT:
            kw["max_output_tokens"] = max_tokens
        if reasoning_effort:
            kw["reasoning"] = {"effort": reasoning_effort}
        resp = client.responses.create(**kw)
        return resp.output_text or ""

    kw = {"model": model, "messages": messages}
    if temperature is not None:
        kw["temperature"] = temperature
    if json_mode:
        kw["response_format"] = {"type": "json_object"}
    if max_tokens:
        kw["max_tokens"] = max_tokens
    resp = client.chat.completions.create(**kw)
    return resp.choices[0].message.content or ""


def stream_text(
    model: str,
    messages: list[dict],
    *,
    temperature: float | None = None,
) -> Iterator[str]:
    """Gera pedaços de texto. Em modelos de raciocínio não há streaming nativo
    aqui: faz uma chamada única e entrega o texto de uma vez."""
    if is_reasoning(model):
        yield complete(model, messages, temperature=temperature)
        return

    client = _client()
    kw: dict = {"model": model, "messages": messages, "stream": True}
    if temperature is not None:
        kw["temperature"] = temperature
    for event in client.chat.completions.create(**kw):
        delta = event.choices[0].delta.content if event.choices else None
        if delta:
            yield delta


_FENCE = re.compile(r"^```[a-zA-Z]*\n?|\n?```$")


def parse_json(text: str | None) -> dict:
    """Parse tolerante do JSON de resposta, sempre devolve dict (``{}`` em falha).

    Modelos de raciocínio não usam ``response_format``: confiam no prompt, então
    a resposta pode vir cercada com ```json ... ``` ou com texto em volta. Aqui
    tiramos a cerca e, se preciso, extraímos o maior bloco ``{...}``.
    """
    s = (text or "").strip()
    if s.startswith("```"):
        s = _FENCE.sub("", s).strip()
    try:
        return json.loads(s or "{}")
    except json.JSONDecodeError:
        i, j = s.find("{"), s.rfind("}")
        if 0 <= i < j:
            try:
                return json.loads(s[i:j + 1])
            except json.JSONDecodeError:
                return {}
        return {}
