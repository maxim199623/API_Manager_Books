import asyncio
import importlib
import uuid

import pytest

from api_manager_books.api.websocket.manager import ConnectionManager

websocket_manager_module = importlib.import_module(
    "api_manager_books.api.websocket.manager"
)

pytestmark = pytest.mark.asyncio


class FakeWebSocket:
    """Минимальный WebSocket для проверки менеджера."""

    def __init__(self, *, delay: float = 0.0, error: Exception | None = None):
        self.delay = delay
        self.error = error
        self.accepted = False
        self.closed = False
        self.messages: list[dict] = []

    async def accept(self):
        self.accepted = True

    async def send_json(self, message: dict):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        self.messages.append(message)

    async def close(self, code: int, reason: str):
        self.closed = True
        self.close_code = code
        self.close_reason = reason


async def test_broadcast_sends_message_to_all_working_connections():
    manager = ConnectionManager()
    user_1 = uuid.uuid4()
    user_2 = uuid.uuid4()
    first = FakeWebSocket()
    second = FakeWebSocket()
    message = {"type": "ping"}

    await manager.connect(first, user_1)
    await manager.connect(second, user_2)

    await manager.broadcast(message)

    assert first.messages == [message]
    assert second.messages == [message]


async def test_broadcast_removes_failed_connections():
    manager = ConnectionManager()
    user_id = uuid.uuid4()
    working = FakeWebSocket()
    broken = FakeWebSocket(error=RuntimeError("closed"))

    await manager.connect(working, user_id)
    await manager.connect(broken, user_id)

    await manager.broadcast({"type": "update"})

    assert working in manager.active_connections[user_id]
    assert broken not in manager.active_connections[user_id]


async def test_broadcast_slow_connection_does_not_block_fast_connection(monkeypatch):
    monkeypatch.setattr(
        websocket_manager_module,
        "WEBSOCKET_SEND_TIMEOUT",
        0.01,
        raising=False,
    )
    manager = ConnectionManager()
    slow_user = uuid.uuid4()
    fast_user = uuid.uuid4()
    slow = FakeWebSocket(delay=0.2)
    fast = FakeWebSocket()
    message = {"type": "new_book"}

    await manager.connect(slow, slow_user)
    await manager.connect(fast, fast_user)

    await asyncio.wait_for(manager.broadcast(message), timeout=0.08)

    assert fast.messages == [message]
    assert slow_user not in manager.active_connections


async def test_send_to_user_does_not_write_stdout_and_removes_failed_connections(capsys):
    manager = ConnectionManager()
    user_id = uuid.uuid4()
    working = FakeWebSocket()
    broken = FakeWebSocket(error=RuntimeError("closed"))

    await manager.connect(working, user_id)
    await manager.connect(broken, user_id)

    await manager.send_to_user(user_id, {"type": "personal"})

    captured = capsys.readouterr()
    assert captured.out == ""
    assert working.messages == [{"type": "personal"}]
    assert broken not in manager.active_connections[user_id]
