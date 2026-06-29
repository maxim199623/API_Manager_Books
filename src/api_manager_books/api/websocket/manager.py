import asyncio
import uuid

from fastapi import WebSocket

BROADCAST_CONCURRENCY = 100
WEBSOCKET_SEND_TIMEOUT = 5


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
        connections = list(self.active_connections.get(user_id, set()))
        if not connections:
            return

        dead = await self._send_many(
            [(user_id, ws) for ws in connections],
            message,
        )
        for dead_user_id, ws in dead:
            self.disconnect(ws, dead_user_id)

    async def broadcast(self, message: dict):
        """Отправить сообщение **всем** подключённым пользователям"""
        targets = [
            (user_id, ws)
            for user_id, connections in list(self.active_connections.items())
            for ws in list(connections)
        ]
        dead = await self._send_many(targets, message)

        for user_id, ws in dead:
            self.disconnect(ws, user_id)

    async def _send_many(
        self,
        targets: list[tuple[uuid.UUID, WebSocket]],
        message: dict,
    ) -> list[tuple[uuid.UUID, WebSocket]]:
        """Отправить сообщение группе соединений с ограничением параллелизма."""
        semaphore = asyncio.Semaphore(BROADCAST_CONCURRENCY)

        async def send_one(user_id: uuid.UUID, ws: WebSocket):
            async with semaphore:
                try:
                    await asyncio.wait_for(
                        ws.send_json(message),
                        timeout=WEBSOCKET_SEND_TIMEOUT,
                    )
                except Exception:
                    return user_id, ws
                return None

        results = await asyncio.gather(
            *(send_one(user_id, ws) for user_id, ws in targets)
        )
        return [result for result in results if result is not None]

    async def disconnect_all(self, user_id: uuid.UUID):
        """Закрыть все соединения пользователя (при logout/re-login)"""
        if user_id in self.active_connections:
            for ws in list(self.active_connections[user_id]):
                try:
                    await ws.close(code=4001, reason="Session replaced")
                except Exception:
                    pass
            del self.active_connections[user_id]

