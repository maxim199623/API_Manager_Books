import uuid

from fastapi import WebSocket


class ConnectionManager:
    """Хранит активные WebSocket-подключения."""

    def __init__(self):
        """Создает пустое хранилище подключений."""
        self.active_connections: dict[uuid.UUID, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: uuid.UUID):
        """Регистрирует подключение пользователя."""
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        self.active_connections[user_id].add(websocket)

    def disconnect(self, websocket: WebSocket, user_id: uuid.UUID):
        """Удаляет подключение пользователя."""
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def send_to_user(self, user_id: uuid.UUID, message: dict):
        """Отправляет сообщение пользователю."""
        if user_id in self.active_connections:
            for ws in list(self.active_connections[user_id]):
                print(ws)
                await ws.send_json(message)

    async def broadcast(self, message: dict):
        """Отправить сообщение **всем** подключённым пользователям"""
        dead = []
        for user_id, connections in list(self.active_connections.items()):
            for ws in list(connections):
                try:
                    await ws.send_json(message)
                except Exception:
                    dead.append((user_id, ws))

        for user_id, ws in dead:
            self.disconnect(ws, user_id)

    async def disconnect_all(self, user_id: uuid.UUID):
        """Закрыть все соединения пользователя (при logout/re-login)"""
        if user_id in self.active_connections:
            for ws in list(self.active_connections[user_id]):
                try:
                    await ws.close(code=4001, reason="Session replaced")
                except Exception:
                    pass
            del self.active_connections[user_id]

