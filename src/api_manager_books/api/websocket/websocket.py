

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends

from api_manager_books.api.security.utils import get_current_user_from_ws
from api_manager_books.db.Repository import User
from api_manager_books.api.websocket import manager


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