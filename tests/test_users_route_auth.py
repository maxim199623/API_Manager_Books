import uuid
from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api_manager_books.api.route import users as users_route
from api_manager_books.api.security.utils import require_admin
from api_manager_books.application.services.user_service import (
    CannotDemoteLastAdminError,
    CannotRemoveLastAdminError,
    InvalidRefreshTokenError,
    TokenPair,
)
from api_manager_books.schemas.api import AuthRequest, RefreshTokenRequest
from api_manager_books.schemas.enums import UserRole
from api_manager_books.schemas.users import UserRead
from api_manager_books.security.auth_throttle import TooManyAuthAttemptsError


@dataclass
class FakeUserService:
    """Тестовый сервис пользователей."""

    token_pair: TokenPair | None = None
    refresh_error: bool = False
    delete_last_admin_error: bool = False
    demote_last_admin_error: bool = False

    login_client_ip: str | None = None
    refresh_client_ip: str | None = None

    async def login(self, email: str, password: str, *, client_ip: str = "unknown") -> TokenPair:
        """Имитирует login."""
        self.login_client_ip = client_ip
        return self.token_pair or TokenPair(
            access_token=f"access:{email}:{password}",
            refresh_token="refresh-token",
        )

    async def refresh(self, refresh_token: str, *, client_ip: str = "unknown") -> TokenPair:
        """Имитирует refresh."""
        self.refresh_client_ip = client_ip
        if self.refresh_error:
            raise InvalidRefreshTokenError
        return self.token_pair or TokenPair(
            access_token=f"access:{refresh_token}",
            refresh_token="new-refresh-token",
        )

    async def delete_user(self, user_id: uuid.UUID, current_user: UserRead) -> bool:
        """Имитирует удаление пользователя."""
        if self.delete_last_admin_error:
            raise CannotRemoveLastAdminError
        return True

    async def update_user(
        self,
        user_id: uuid.UUID,
        payload,
        current_user: UserRead,
    ) -> None:
        """Имитирует обновление пользователя."""
        if self.demote_last_admin_error:
            raise CannotDemoteLastAdminError


class ThrottledUserService:
    """Сервис, имитирующий срабатывание auth throttle."""

    async def login(self, email: str, password: str, *, client_ip: str = "unknown"):
        """Имитирует блокировку login."""
        raise TooManyAuthAttemptsError

    async def refresh(self, refresh_token: str, *, client_ip: str = "unknown"):
        """Имитирует блокировку refresh."""
        raise TooManyAuthAttemptsError


def make_request(host: str):
    """Создает минимальный объект Request для прямого вызова route."""
    return SimpleNamespace(client=SimpleNamespace(host=host))


@pytest.mark.asyncio
async def test_login_route_returns_access_and_refresh_token():
    """Проверяет контракт ответа /users/auth."""
    result = await users_route.login(
        AuthRequest(email="user@example.com", password="secret"),
        request=make_request("127.0.0.1"),
        user_service=FakeUserService(),
    )

    assert result.access_token == "access:user@example.com:secret"
    assert result.refresh_token == "refresh-token"
    assert result.token_type == "bearer"


@pytest.mark.asyncio
async def test_refresh_route_returns_rotated_token_pair():
    """Проверяет контракт ответа /users/refresh."""
    result = await users_route.refresh(
        RefreshTokenRequest(refresh_token="old-refresh"),
        request=make_request("127.0.0.1"),
        user_service=FakeUserService(),
    )

    assert result.access_token == "access:old-refresh"
    assert result.refresh_token == "new-refresh-token"
    assert result.token_type == "bearer"


@pytest.mark.asyncio
async def test_refresh_route_returns_401_for_invalid_refresh_token():
    """Проверяет отказ для невалидного refresh token."""
    with pytest.raises(HTTPException) as excinfo:
        await users_route.refresh(
            RefreshTokenRequest(refresh_token="bad-refresh"),
            request=make_request("127.0.0.1"),
            user_service=FakeUserService(refresh_error=True),
        )

    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_login_route_returns_429_when_throttled():
    """Проверяет HTTP 429 при превышении лимита login."""
    with pytest.raises(HTTPException) as excinfo:
        await users_route.login(
            AuthRequest(email="user@example.com", password="valid-password-42"),
            request=make_request("127.0.0.1"),
            user_service=ThrottledUserService(),
        )

    assert excinfo.value.status_code == 429
    assert excinfo.value.detail == "Too many authentication attempts"


@pytest.mark.asyncio
async def test_login_route_passes_client_ip_to_service():
    """Проверяет передачу IP клиента в login."""
    service = FakeUserService()

    await users_route.login(
        AuthRequest(email="user@example.com", password="valid-password-42"),
        request=make_request("203.0.113.10"),
        user_service=service,
    )

    assert service.login_client_ip == "203.0.113.10"


@pytest.mark.asyncio
async def test_refresh_route_returns_429_when_throttled():
    """Проверяет HTTP 429 при превышении лимита refresh."""
    with pytest.raises(HTTPException) as excinfo:
        await users_route.refresh(
            RefreshTokenRequest(refresh_token="refresh-token"),
            request=make_request("127.0.0.1"),
            user_service=ThrottledUserService(),
        )

    assert excinfo.value.status_code == 429
    assert excinfo.value.detail == "Too many authentication attempts"


@pytest.mark.asyncio
async def test_me_route_returns_current_database_user():
    """Проверяет контракт /users/me."""
    current_user = UserRead(
        id=uuid.uuid4(),
        email="user@example.com",
        role=UserRole.ADMIN,
        created_at=datetime.now(),
    )

    result = await users_route.me(current_user=current_user)

    assert result == current_user


@pytest.mark.asyncio
async def test_delete_last_admin_route_returns_409():
    """Проверяет HTTP-маппинг запрета удаления последнего администратора."""
    with pytest.raises(HTTPException) as excinfo:
        await users_route.dell_users(
            uuid.uuid4(),
            user_service=FakeUserService(delete_last_admin_error=True),
            current_user=UserRead(
                id=uuid.uuid4(),
                email="admin@example.com",
                role=UserRole.ADMIN,
                created_at=datetime.now(),
            ),
        )

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail == "Cannot remove the last admin"


@pytest.mark.asyncio
async def test_demote_last_admin_route_returns_409():
    """Проверяет HTTP-маппинг запрета понижения последнего администратора."""
    with pytest.raises(HTTPException) as excinfo:
        await users_route.patch_user(
            uuid.uuid4(),
            payload=users_route.UserUpdate(role=UserRole.USER),
            user_service=FakeUserService(demote_last_admin_error=True),
            current_user=UserRead(
                id=uuid.uuid4(),
                email="admin@example.com",
                role=UserRole.ADMIN,
                created_at=datetime.now(),
            ),
        )

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail == "Cannot demote the last admin"


@pytest.mark.asyncio
async def test_require_admin_keeps_403_for_non_admin_user():
    """Проверяет, что non-admin по-прежнему получает 403."""
    with pytest.raises(HTTPException) as excinfo:
        await require_admin(
            UserRead(
                id=uuid.uuid4(),
                email="user@example.com",
                role=UserRole.USER,
                created_at=datetime.now(),
            )
        )

    assert excinfo.value.status_code == 403
