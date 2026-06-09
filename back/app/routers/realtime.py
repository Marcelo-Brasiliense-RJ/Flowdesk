"""WebSocket endpoint for the realtime workflow monitor."""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from ..auth import ALGORITHM
from ..config import settings
from ..database import SessionLocal
from ..models import Project, User
from ..services.ws import hub

router = APIRouter(tags=["realtime"])


def _authorized(token: str | None, project_id: int) -> bool:
    """Require a valid JWT whose user's org owns the project."""
    if not token:
        return False
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return False
    email = payload.get("sub")
    if not email:
        return False
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user is None or not user.is_active:
            return False
        project = db.get(Project, project_id)
        return project is not None and project.org_id == user.org_id
    finally:
        db.close()


@router.websocket("/ws/projects/{project_id}")
async def workflow_ws(websocket: WebSocket, project_id: int):
    token = websocket.query_params.get("token")
    if not _authorized(token, project_id):
        await websocket.close(code=4401)
        return
    await hub.connect(project_id, websocket)
    try:
        await websocket.send_json({"type": "connected", "project_id": project_id})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(project_id, websocket)
    except Exception:
        await hub.disconnect(project_id, websocket)
