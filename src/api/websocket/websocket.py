

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends

from src.api.security.utils import get_current_user_from_ws
from src.DB.Repository import User
from src.api.websocket import manager


router = APIRouter(prefix="/ws", tags=["websocket"])

@router.websocket("/notifications")
async def websocket_endpoint(
    websocket: WebSocket,
    current_user: User = Depends(get_current_user_from_ws)

):
    await manager.connect(websocket, current_user.id)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, current_user.id)
    except Exception:
        manager.disconnect(websocket, current_user.id)