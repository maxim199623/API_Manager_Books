import uuid
from dataclasses import dataclass
from datetime import datetime

import jwt
import pytest
from fastapi import HTTPException, WebSocketException
from fastapi.security import HTTPAuthorizationCredentials

from api_manager_books.api.security import utils as security_utils
from api_manager_books.schemas.enums import UserRole


@dataclass
class FakeUser:
    """Тестовый пользователь из БД."""

    id: uuid.UUID
    email: str
    role: UserRole
    session: uuid.UUID | None
    created_at: datetime


class FakeUserRepo:
    """Тестовый репозиторий пользователей."""

    def __init__(self, user: FakeUser | None):
        self.user = user

    async def get_by_id(self, user_id: uuid.UUID):
        """Возвращает пользователя по ID."""
        if self.user is not None and self.user.id == user_id:
            return self.user
        return None


def bearer() -> HTTPAuthorizationCredentials:
    """Создает Bearer credentials."""
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")


class FakeWebSocket:
    """Минимальный WebSocket для проверки auth dependency."""

    def __init__(self):
        self.closed = False
        self.close_code = None
        self.close_reason = None

    async def close(self, code: int = 1000, reason: str | None = None):
        """Запоминает параметры закрытия."""
        self.closed = True
        self.close_code = code
        self.close_reason = reason


@pytest.mark.asyncio
async def test_get_current_user_rejects_token_without_access_type(monkeypatch):
    """Проверяет отказ для JWT без type=access."""
    user_id = uuid.uuid4()
    session = uuid.uuid4()
    monkeypatch.setattr(
        security_utils,
        "decode_access_token",
        lambda token: {"sub": str(user_id), "sid": str(session)},
    )

    with pytest.raises(HTTPException) as excinfo:
        await security_utils.get_current_user(
            credentials=bearer(),
            user_repo=FakeUserRepo(
                FakeUser(
                    id=user_id,
                    email="user@example.com",
                    role=UserRole.USER,
                    session=session,
                    created_at=datetime.now(),
                )
            ),
        )

    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_rejects_invalid_sid_payload(monkeypatch):
    """Проверяет 401 для битого sid."""
    monkeypatch.setattr(
        security_utils,
        "decode_access_token",
        lambda token: {"sub": str(uuid.uuid4()), "sid": "not-a-uuid", "type": "access"},
    )

    with pytest.raises(HTTPException) as excinfo:
        await security_utils.get_current_user(credentials=bearer(), user_repo=FakeUserRepo(None))

    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_returns_401_for_oversized_token(monkeypatch):
    """Проверяет HTTP 401 для слишком большого Bearer token."""

    def reject_oversized_token(token: str):
        raise jwt.InvalidTokenError

    monkeypatch.setattr(security_utils, "decode_access_token", reject_oversized_token)

    with pytest.raises(HTTPException) as excinfo:
        await security_utils.get_current_user(credentials=bearer(), user_repo=FakeUserRepo(None))

    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_from_ws_closes_oversized_token(monkeypatch):
    """Проверяет закрытие WebSocket auth path для слишком большого token."""

    def reject_oversized_token(token: str):
        raise jwt.InvalidTokenError

    websocket = FakeWebSocket()
    monkeypatch.setattr(security_utils, "decode_access_token", reject_oversized_token)

    with pytest.raises(WebSocketException) as excinfo:
        await security_utils.get_current_user_from_ws(
            websocket=websocket,
            token="token",
            user_repo=FakeUserRepo(None),
        )

    assert excinfo.value.code == 1008
    assert websocket.closed is True
    assert websocket.close_code == 1008
    assert websocket.close_reason == "Invalid token"


@pytest.mark.asyncio
async def test_require_admin_uses_database_role_not_jwt_claim():
    """Проверяет, что права берутся из пользователя БД."""
    current_user = FakeUser(
        id=uuid.uuid4(),
        email="user@example.com",
        role=UserRole.USER,
        session=uuid.uuid4(),
        created_at=datetime.now(),
    )

    with pytest.raises(HTTPException) as excinfo:
        await security_utils.require_admin(current_user=current_user)

    assert excinfo.value.status_code == 403
