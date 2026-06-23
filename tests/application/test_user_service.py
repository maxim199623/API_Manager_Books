import uuid

import pytest

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
