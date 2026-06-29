import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from api_manager_books.application.services import user_service as user_service_module
from api_manager_books.application.services.user_service import (
    CannotDemoteLastAdminError,
    CannotRemoveLastAdminError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    UserService,
)
from api_manager_books.db.Repository.UserRepository.user_repository import (
    UserNotFoundError as RepositoryUserNotFoundError,
)
from api_manager_books.schemas.enums import UserRole
from api_manager_books.schemas.users import UserRead, UserUpdate
from api_manager_books.security.auth_throttle import TooManyAuthAttemptsError
from api_manager_books.security.refresh_tokens import hash_refresh_token


@dataclass
class FakeUser:
    """Тестовый пользователь."""

    id: uuid.UUID
    email: str
    password_hash: bytes
    role: UserRole
    created_at: datetime
    session: uuid.UUID | None = None
    refresh_token_hash: bytes | None = None
    refresh_token_expires_at: datetime | None = None


class FakeUserRepo:
    """Тестовый репозиторий пользователей."""
    def __init__(self):
        """Инициализирует тестовый объект."""
        self.session_calls: list[tuple[uuid.UUID, uuid.UUID | None]] = []
        self.auth_session_calls: list[tuple[uuid.UUID, uuid.UUID, bytes, datetime]] = []
        self.user = FakeUser(
            id=uuid.uuid4(),
            email="user@example.com",
            password_hash=b"",
            role=UserRole.USER,
            created_at=datetime.now(UTC),
        )

    async def set_session_id(self, user_id: uuid.UUID, session_id: uuid.UUID | None):
        """Имитирует смену сессии пользователя."""
        self.session_calls.append((user_id, session_id))

    async def set_auth_session(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        refresh_token_hash: bytes,
        refresh_token_expires_at: datetime,
    ):
        """Имитирует сохранение auth-сессии."""
        self.auth_session_calls.append(
            (user_id, session_id, refresh_token_hash, refresh_token_expires_at)
        )

    async def clear_auth_session(self, user_id: uuid.UUID):
        """Имитирует очистку auth-сессии."""
        self.session_calls.append((user_id, None))


class FakeLogRepo:
    """Тестовый репозиторий логов."""

    def __init__(self):
        self.actions = []

    async def log_action(self, **kwargs):
        """Сохраняет действие в памяти."""
        self.actions.append(kwargs)


class FakeNotificationManager:
    """Тестовый менеджер уведомлений."""
    async def send_to_user(self, user_id: uuid.UUID, message: dict):
        """Запрещает отправку уведомлений в этом тесте."""
        raise AssertionError("logout не должен отправлять уведомления")


def fake_token_factory(payload: dict) -> str:
    """Запрещает выпуск токена в этом тесте."""
    raise AssertionError("logout не должен выпускать токен")


@pytest.mark.asyncio
async def test_logout_closes_current_session():
    """Проверяет закрытие текущей сессии при logout."""
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


class LoginUserRepo(FakeUserRepo):
    """Репозиторий для проверки login."""

    def __init__(self, user: FakeUser):
        super().__init__()
        self.user = user

    async def get_by_email(self, email: str):
        """Возвращает пользователя по email."""
        if email == self.user.email:
            return self.user
        return None


class RefreshUserRepo(FakeUserRepo):
    """Репозиторий для проверки refresh."""

    def __init__(self, user: FakeUser):
        super().__init__()
        self.user = user

    async def get_by_refresh_token_hash(self, refresh_token_hash: bytes):
        """Возвращает пользователя по хешу refresh token."""
        if self.user.refresh_token_hash == refresh_token_hash:
            return self.user
        return None


class CapturingLogRepo:
    """Тестовый репозиторий логов."""

    def __init__(self):
        self.logs = []

    async def log_from_dto(self, payload):
        """Сохраняет лог в памяти."""
        self.logs.append(payload)


class CapturingNotificationManager:
    """Тестовый менеджер уведомлений."""

    def __init__(self):
        self.messages = []

    async def send_to_user(self, user_id: uuid.UUID, message: dict):
        """Сохраняет уведомление в памяти."""
        self.messages.append((user_id, message))


def capturing_token_factory(payload: dict) -> str:
    """Кодирует payload в строку для проверки сервиса."""
    return f"token:{payload}"


def make_login_service(user: FakeUser | None = None) -> tuple[UserService, LoginUserRepo]:
    """Собирает сервис для проверки login."""
    from api_manager_books.security.passwords import hash_password

    login_user = user or FakeUser(
        id=uuid.uuid4(),
        email="user@example.com",
        password_hash=hash_password("valid-password-42"),
        role=UserRole.USER,
        created_at=datetime.now(UTC),
    )
    user_repo = LoginUserRepo(login_user)
    service = UserService(
        user_repo=user_repo,
        log_repo=CapturingLogRepo(),
        token_factory=capturing_token_factory,
        notification_manager=CapturingNotificationManager(),
    )
    return service, user_repo


@pytest.mark.asyncio
async def test_login_returns_access_and_refresh_tokens_with_access_payload():
    """Проверяет выдачу пары токенов при login."""
    from api_manager_books.security.passwords import hash_password

    user = FakeUser(
        id=uuid.uuid4(),
        email="user@example.com",
        password_hash=hash_password("secret"),
        role=UserRole.ADMIN,
        created_at=datetime.now(UTC),
    )
    user_repo = LoginUserRepo(user)
    service = UserService(
        user_repo=user_repo,
        log_repo=CapturingLogRepo(),
        token_factory=capturing_token_factory,
        notification_manager=CapturingNotificationManager(),
    )

    result = await service.login(user.email, "secret")

    assert result.access_token.startswith("token:")
    assert result.refresh_token
    assert result.token_type == "bearer"
    assert "'sub':" in result.access_token
    assert "'sid':" in result.access_token
    assert "'role': <UserRole.ADMIN: 'admin'>" in result.access_token
    assert "'type': 'access'" in result.access_token
    assert len(user_repo.auth_session_calls) == 1
    _, _, stored_hash, expires_at = user_repo.auth_session_calls[0]
    assert stored_hash != result.refresh_token.encode()
    assert expires_at > datetime.now(UTC) + timedelta(days=13)


@pytest.mark.asyncio
async def test_login_blocks_after_five_failed_attempts_for_same_email():
    """Проверяет лимит ошибок входа по email."""
    service, _ = make_login_service()

    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            await service.login("user@example.com", "wrong-password", client_ip="127.0.0.1")

    with pytest.raises(TooManyAuthAttemptsError):
        await service.login("user@example.com", "wrong-password", client_ip="127.0.0.1")


@pytest.mark.asyncio
async def test_login_ip_limit_blocks_noisy_source():
    """Проверяет лимит ошибок входа по IP."""
    service, _ = make_login_service()

    for index in range(30):
        with pytest.raises(InvalidCredentialsError):
            await service.login(f"user{index}@example.com", "wrong-password", client_ip="127.0.0.1")

    with pytest.raises(TooManyAuthAttemptsError):
        await service.login("another@example.com", "wrong-password", client_ip="127.0.0.1")


@pytest.mark.asyncio
async def test_successful_login_clears_email_counter_but_not_ip_counter():
    """Проверяет очистку счетчика email после успешного входа."""
    service, _ = make_login_service()

    for _ in range(4):
        with pytest.raises(InvalidCredentialsError):
            await service.login("user@example.com", "wrong-password", client_ip="127.0.0.1")

    await service.login("user@example.com", "valid-password-42", client_ip="127.0.0.1")

    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            await service.login("user@example.com", "wrong-password", client_ip="127.0.0.1")


@pytest.mark.asyncio
async def test_refresh_rotates_refresh_token_and_rejects_old_token():
    """Проверяет ротацию refresh token."""
    old_refresh = "old-refresh-token"
    user = FakeUser(
        id=uuid.uuid4(),
        email="user@example.com",
        password_hash=b"",
        role=UserRole.USER,
        created_at=datetime.now(UTC),
        session=uuid.uuid4(),
        refresh_token_hash=hash_refresh_token(old_refresh),
        refresh_token_expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    user_repo = RefreshUserRepo(user)
    service = UserService(
        user_repo=user_repo,
        log_repo=CapturingLogRepo(),
        token_factory=capturing_token_factory,
        notification_manager=CapturingNotificationManager(),
    )

    result = await service.refresh(old_refresh)
    _, _, new_hash, _ = user_repo.auth_session_calls[0]
    user.refresh_token_hash = new_hash

    assert result.refresh_token
    assert result.refresh_token != old_refresh
    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(old_refresh)


@pytest.mark.asyncio
async def test_refresh_rejects_expired_refresh_token():
    """Проверяет отказ для истекшего refresh token."""
    refresh = "expired-refresh-token"
    user = FakeUser(
        id=uuid.uuid4(),
        email="user@example.com",
        password_hash=b"",
        role=UserRole.USER,
        created_at=datetime.now(UTC),
        session=uuid.uuid4(),
        refresh_token_hash=hash_refresh_token(refresh),
        refresh_token_expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    service = UserService(
        user_repo=RefreshUserRepo(user),
        log_repo=CapturingLogRepo(),
        token_factory=capturing_token_factory,
        notification_manager=CapturingNotificationManager(),
    )

    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(refresh)


@pytest.mark.asyncio
async def test_refresh_blocks_after_five_failed_attempts_for_same_token():
    """Проверяет лимит ошибок refresh по token."""
    user = FakeUser(
        id=uuid.uuid4(),
        email="user@example.com",
        password_hash=b"",
        role=UserRole.USER,
        created_at=datetime.now(UTC),
    )
    service = UserService(
        user_repo=RefreshUserRepo(user),
        log_repo=CapturingLogRepo(),
        token_factory=capturing_token_factory,
        notification_manager=CapturingNotificationManager(),
    )

    for _ in range(5):
        with pytest.raises(InvalidRefreshTokenError):
            await service.refresh("bad-refresh-token", client_ip="127.0.0.1")

    with pytest.raises(TooManyAuthAttemptsError):
        await service.refresh("bad-refresh-token", client_ip="127.0.0.1")


class UserRepoWithMissingUser:
    """Репозиторий, имитирующий отсутствующего пользователя."""
    async def ensure_exists(self, user_id: uuid.UUID):
        """Имитирует проверку существования записи."""
        raise RepositoryUserNotFoundError(f"User #{user_id} not found")


@pytest.mark.asyncio
async def test_update_user_converts_repository_not_found_to_service_error():
    """Проверяет преобразование ошибки отсутствующего пользователя."""
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


class AdminGuardUserRepo:
    """Репозиторий для проверки защиты последнего администратора."""

    def __init__(self, *, target_role: UserRole, admin_count: int):
        self.user = FakeUser(
            id=uuid.uuid4(),
            email="target@example.com",
            password_hash=b"",
            role=target_role,
            created_at=datetime.now(UTC),
        )
        self.admin_count = admin_count
        self.deleted_ids: list[uuid.UUID] = []
        self.updated: list[tuple[uuid.UUID, str | None, str | None, UserRole | None]] = []
        self.cleared_sessions: list[uuid.UUID] = []

    async def ensure_exists(self, user_id: uuid.UUID):
        """Возвращает целевого пользователя."""
        return self.user

    async def count_admins(self) -> int:
        """Возвращает заданное количество администраторов."""
        return self.admin_count

    async def delete_user(self, user_id: uuid.UUID) -> bool:
        """Имитирует удаление пользователя."""
        self.deleted_ids.append(user_id)
        return True

    async def update_user(
        self,
        user_id: uuid.UUID,
        *,
        email: str | None = None,
        password: str | None = None,
        role: UserRole | None = None,
    ):
        """Имитирует обновление пользователя."""
        self.updated.append((user_id, email, password, role))
        if role is not None:
            self.user.role = role
        return self.user

    async def clear_auth_session(self, user_id: uuid.UUID):
        """Имитирует очистку auth-сессии."""
        self.cleared_sessions.append(user_id)


def make_current_admin() -> UserRead:
    """Создает текущего администратора."""
    return UserRead(
        id=uuid.uuid4(),
        email="admin@example.com",
        role=UserRole.ADMIN,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_delete_only_admin_raises_error():
    """Проверяет запрет удаления последнего администратора."""
    user_repo = AdminGuardUserRepo(target_role=UserRole.ADMIN, admin_count=1)
    service = UserService(
        user_repo=user_repo,
        log_repo=FakeLogRepo(),
        token_factory=fake_token_factory,
        notification_manager=FakeNotificationManager(),
    )

    with pytest.raises(CannotRemoveLastAdminError):
        await service.delete_user(user_repo.user.id, make_current_admin())

    assert user_repo.deleted_ids == []


@pytest.mark.asyncio
async def test_demote_only_admin_raises_error():
    """Проверяет запрет понижения последнего администратора."""
    user_repo = AdminGuardUserRepo(target_role=UserRole.ADMIN, admin_count=1)
    service = UserService(
        user_repo=user_repo,
        log_repo=FakeLogRepo(),
        token_factory=fake_token_factory,
        notification_manager=FakeNotificationManager(),
    )

    with pytest.raises(CannotDemoteLastAdminError):
        await service.update_user(
            user_repo.user.id,
            UserUpdate(role=UserRole.USER),
            make_current_admin(),
        )

    assert user_repo.updated == []


@pytest.mark.asyncio
async def test_delete_one_admin_allowed_when_multiple_admins_exist():
    """Проверяет удаление администратора, если есть другой администратор."""
    user_repo = AdminGuardUserRepo(target_role=UserRole.ADMIN, admin_count=2)
    service = UserService(
        user_repo=user_repo,
        log_repo=FakeLogRepo(),
        token_factory=fake_token_factory,
        notification_manager=FakeNotificationManager(),
    )

    deleted = await service.delete_user(user_repo.user.id, make_current_admin())

    assert deleted is True
    assert user_repo.deleted_ids == [user_repo.user.id]


@pytest.mark.asyncio
async def test_demote_one_admin_allowed_when_multiple_admins_exist():
    """Проверяет понижение администратора, если есть другой администратор."""
    user_repo = AdminGuardUserRepo(target_role=UserRole.ADMIN, admin_count=2)
    service = UserService(
        user_repo=user_repo,
        log_repo=CapturingLogRepo(),
        token_factory=fake_token_factory,
        notification_manager=FakeNotificationManager(),
    )

    await service.update_user(
        user_repo.user.id,
        UserUpdate(role=UserRole.USER),
        make_current_admin(),
    )

    assert user_repo.updated == [(user_repo.user.id, None, None, UserRole.USER)]


class SensitiveUpdateUserRepo(AdminGuardUserRepo):
    """Репозиторий для проверки инвалидации сессий."""

    def __init__(self, *, fail_update: bool = False):
        super().__init__(target_role=UserRole.USER, admin_count=1)
        self.fail_update = fail_update

    async def update_user(
        self,
        user_id: uuid.UUID,
        *,
        email: str | None = None,
        password: str | None = None,
        role: UserRole | None = None,
    ):
        """Имитирует успешное или аварийное обновление пользователя."""
        if self.fail_update:
            raise RuntimeError("update failed")
        return await super().update_user(
            user_id,
            email=email,
            password=password,
            role=role,
        )


@pytest.mark.asyncio
async def test_update_user_password_clears_auth_session_after_successful_update():
    """Проверяет очистку сессии после смены пароля."""
    user_repo = SensitiveUpdateUserRepo()
    service = UserService(
        user_repo=user_repo,
        log_repo=CapturingLogRepo(),
        token_factory=fake_token_factory,
        notification_manager=FakeNotificationManager(),
    )

    await service.update_user(
        user_repo.user.id,
        UserUpdate(password="new-password-long"),
        make_current_admin(),
    )

    assert user_repo.updated == [(user_repo.user.id, None, "new-password-long", None)]
    assert user_repo.cleared_sessions == [user_repo.user.id]


@pytest.mark.asyncio
async def test_update_user_role_clears_auth_session_after_successful_update():
    """Проверяет очистку сессии после смены роли."""
    user_repo = SensitiveUpdateUserRepo()
    service = UserService(
        user_repo=user_repo,
        log_repo=CapturingLogRepo(),
        token_factory=fake_token_factory,
        notification_manager=FakeNotificationManager(),
    )

    await service.update_user(
        user_repo.user.id,
        UserUpdate(role=UserRole.ADMIN),
        make_current_admin(),
    )

    assert user_repo.updated == [(user_repo.user.id, None, None, UserRole.ADMIN)]
    assert user_repo.cleared_sessions == [user_repo.user.id]


@pytest.mark.asyncio
async def test_update_user_email_only_does_not_clear_auth_session():
    """Проверяет, что смена email не сбрасывает сессию."""
    user_repo = SensitiveUpdateUserRepo()
    service = UserService(
        user_repo=user_repo,
        log_repo=CapturingLogRepo(),
        token_factory=fake_token_factory,
        notification_manager=FakeNotificationManager(),
    )

    await service.update_user(
        user_repo.user.id,
        UserUpdate(email="new@example.com"),
        make_current_admin(),
    )

    assert user_repo.updated == [(user_repo.user.id, "new@example.com", None, None)]
    assert user_repo.cleared_sessions == []


@pytest.mark.asyncio
async def test_update_user_does_not_clear_auth_session_when_update_fails():
    """Проверяет, что неуспешное обновление не сбрасывает сессию."""
    user_repo = SensitiveUpdateUserRepo(fail_update=True)
    service = UserService(
        user_repo=user_repo,
        log_repo=CapturingLogRepo(),
        token_factory=fake_token_factory,
        notification_manager=FakeNotificationManager(),
    )

    with pytest.raises(RuntimeError):
        await service.update_user(
            user_repo.user.id,
            UserUpdate(password="new-password-long"),
            make_current_admin(),
        )

    assert user_repo.cleared_sessions == []
