"""Rate limiting em processo (sem dependência nova).

O FlowDesk roda como um único processo uvicorn (fila asyncio, runtime de subprocess,
métricas em memória), então um contador em memória é suficiente e honesto. Aplica
janelas fixas por chave, com limpeza oportunista para não crescer sem limite.

ponytail: contador por processo, em memória. Se um dia rodar com múltiplos workers,
troque `_check` por um backend compartilhado (Redis/Memcached); o resto da API fica igual.

Uso:
- enforce(key, limit, window): levanta HTTP 429 quando estoura (usado no login, por e-mail).
- rate_limit_middleware: aplica RULES por método + prefixo de rota (IP ou usuário).
"""
from __future__ import annotations

import logging
import re
import threading
import time

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from jose import JWTError, jwt

from .auth import ALGORITHM
from .config import settings

log = logging.getLogger("flowdesk.security")

_lock = threading.Lock()
# chave -> (início_da_janela_monotonic, contagem)
_hits: dict[str, tuple[float, int]] = {}
_MAX_KEYS = 50_000  # teto de memória; acima disto faz limpeza dos expirados


def _check(key: str, limit: int, window: int) -> tuple[bool, int]:
    """Registra um hit e diz se está dentro do limite. Retorna (permitido, retry_after_s)."""
    now = time.monotonic()
    with _lock:
        start, count = _hits.get(key, (now, 0))
        if now - start >= window:
            start, count = now, 0
        count += 1
        _hits[key] = (start, count)
        if len(_hits) > _MAX_KEYS:
            for k, (s, _c) in list(_hits.items()):
                if now - s >= window:
                    _hits.pop(k, None)
    if count <= limit:
        return True, 0
    return False, int(window - (now - start)) + 1


def reset() -> None:
    """Zera o estado (usado em testes)."""
    with _lock:
        _hits.clear()


def enforce(key: str, limit: int, window: int, *, context: str = "") -> None:
    """Levanta HTTP 429 quando a chave excede `limit` hits na janela `window` (s).

    Usado onde a identidade certa vem do corpo já parseado (ex.: login por e-mail),
    que o middleware não enxerga sem reler o body."""
    allowed, retry = _check(key, limit, window)
    if not allowed:
        log.warning("rate_limit_exceeded key=%s limit=%s/%ss %s", key, limit, window, context)
        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas. Aguarde alguns instantes e tente novamente.",
            headers={"Retry-After": str(retry)},
        )


def _client_ip(request: Request) -> str:
    # Atrás de proxy/reverse, o IP real vem no primeiro hop do X-Forwarded-For.
    # ponytail: XFF é falsificável; para um app interno é aceitável. Com WAF/proxy
    # confiável na frente, confie só no header que ele injeta.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _user_or_ip(request: Request) -> str:
    """Identidade para limites de rota autenticada: 'sub' do JWT, senão o IP.

    Decodifica sem tocar no banco (best-effort). Assim usuários distintos atrás de um
    mesmo NAT de escritório não compartilham o balde de rate limit em rotas de IA."""
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        try:
            sub = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM]).get("sub")
            if sub:
                return f"u:{sub}"
        except JWTError:
            pass
    return f"ip:{_client_ip(request)}"


# (método, regex da rota, limite, janela_s, escopo). Ordem importa: para no 1º match.
# - login: baixo, por conta (o login em si é limitado no handler, por e-mail).
# - IA / consumo de tokens: rígido, por usuário (cai para IP sem token).
# - upload / submit público: moderado, por IP/usuário.
# - webhook público: moderado, por IP.
RULES: list[tuple[str, re.Pattern, int, int, str]] = [
    ("POST", re.compile(r"^/api/hooks/[^/]+/?$"), 60, 60, "ip"),
    ("POST", re.compile(r"^/api/app/[^/]+/stages/\d+/submit/?$"), 60, 60, "ip"),
    ("POST", re.compile(r"^/api/projects/\d+/fs/upload/?$"), 60, 60, "user"),
    ("POST", re.compile(r"^/api/projects/\d+/chat/(stream|report-repair)/?$"), 30, 60, "user"),
    ("POST", re.compile(r"^/api/projects/\d+/wizard/(analyze|build|describe)/?$"), 30, 60, "user"),
    ("POST", re.compile(r"^/api/projects/\d+/classificar-grupos/?$"), 30, 60, "user"),
    ("POST", re.compile(r"^/api/projects/\d+/stages/\d+/repair/propose/?$"), 30, 60, "user"),
]


async def rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    method = request.method
    for m, pat, limit, window, scope in RULES:
        if m == method and pat.match(path):
            ident = _client_ip(request) if scope == "ip" else _user_or_ip(request)
            allowed, retry = _check(f"{pat.pattern}|{ident}", limit, window)
            if not allowed:
                log.warning(
                    "rate_limit_exceeded route=%s ident=%s limit=%s/%ss",
                    pat.pattern, ident, limit, window,
                )
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Muitas requisições. Aguarde alguns instantes."},
                    headers={"Retry-After": str(retry)},
                )
            break
    return await call_next(request)
