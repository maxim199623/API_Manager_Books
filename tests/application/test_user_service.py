import uuid
from datetime import datetime

import pytest

from src.schemas.users import UserRead, UserUpdate
from src.DB.Repository.UserRepository.user_repository import UserNotFoundError as RepositoryUserNotFoundError
from src.application.services import user_service as user_service_module
from src.application.services.user_service import UserService


class FakeUserRepo:
    def __init__(self):
        self.session_calls: list[tuple[uuid.UUID, uuid.UUID | None]] = []

    async def set_session_id(self, user_id: uuid.UUID, session_id: uuid.UUID | None):
        self.session_calls.append((user_id, session_id))


class FakeLogRepo:
    pass


class FakeNotificationManager:
    async def send_to_user(self, user_id: uuid.UUID, message: dict):
        raise AssertionError("logout не должен отправлять уведомления")


def fake_token_factory(payload: dict) -> str:
    raise AssertionError("logout не должен выпускать токен")


@pytest.mark.asyncio
async def test_logout_closes_current_session():
    user_id = uuid.uuid4()
    user_repo = FakeUserRepo()
    service = UserService(
        user_repo=user_repo,
        log_repo=FakeLogRepo(),
        token_factory=fake_token_factory,
        notification_manager=FakeNotificationManager(),
    )

    result = await service.logout(user_id)

    assert result is None
    assert user_repo.session_calls == [(user_id, None)]


class UserRepoWithMissingUser:
    async def ensure_exists(self, user_id: uuid.UUID):
        raise RepositoryUserNotFoundError(f"User #{user_id} not found")


@pytest.mark.asyncio
async def test_update_user_converts_repository_not_found_to_service_error():
    service = UserService(
        user_repo=UserRepoWithMissingUser(),
        log_repo=FakeLogRepo(),
        token_factory=fake_token_factory,
        notification_manager=FakeNotificationManager(),
    )
    current_user = UserRead(
        id=uuid.uuid4(),
        email="admin@example.com",
        role="admin",
        created_at=datetime.now(),
    )

    with pytest.raises(user_service_module.UserNotFoundInServiceError):
        await service.update_user(uuid.uuid4(), UserUpdate(email="missing@example.com"), current_user)
