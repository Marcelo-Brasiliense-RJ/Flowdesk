"""Métricas operacionais em memória, para o painel de admin ao vivo.

Sem persistência: estes contadores são zerados a cada reinício do uvicorn.
Servem para um panorama em tempo real (requisições, usuários ativos), não para
histórico. O histórico fica nas execuções/mensagens persistidas no banco.
"""
from __future__ import annotations

import time
from collections import deque

_BOOT = time.time()
_total_requests = 0
_by_method: dict[str, int] = {}
# timestamps das requisições recentes, para taxa por minuto/hora (limitado)
_req_times: deque[float] = deque(maxlen=20000)
# email -> epoch do último acesso autenticado (para "usuários ativos")
_user_seen: dict[str, float] = {}


def record_request(method: str) -> None:
    global _total_requests
    _total_requests += 1
    _by_method[method] = _by_method.get(method, 0) + 1
    _req_times.append(time.time())


def touch_user(email: str) -> None:
    _user_seen[email] = time.time()


def snapshot() -> dict:
    now = time.time()
    last_hour = sum(1 for t in _req_times if t >= now - 3600)
    last_minute = sum(1 for t in _req_times if t >= now - 60)
    active = sorted(e for e, t in _user_seen.items() if t >= now - 15 * 60)
    return {
        "uptime_seconds": round(now - _BOOT, 1),
        "requests_total": _total_requests,
        "requests_last_hour": last_hour,
        "requests_last_minute": last_minute,
        "by_method": dict(_by_method),
        "active_users": active,
        "active_users_count": len(active),
    }
