"""WebSocket connection manager for realtime workflow updates.

Clients subscribe per-project. The runtime broadcasts execution status
changes so the Workflow monitor updates without reloading.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import WebSocket


class WorkflowHub:
    def __init__(self) -> None:
        self._conns: dict[int, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, project_id: int, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._conns[project_id].add(ws)

    async def disconnect(self, project_id: int, ws: WebSocket) -> None:
        async with self._lock:
            self._conns[project_id].discard(ws)

    async def broadcast(self, project_id: int, message: dict) -> None:
        async with self._lock:
            targets = list(self._conns.get(project_id, set()))
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._conns[project_id].discard(ws)


hub = WorkflowHub()
