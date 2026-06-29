import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from api_manager_books.schemas.enums import UserRole
from api_manager_books.schemas.logs import LogCreate
from api_manager_books.schemas.users import UserCreate, UserRead, UserUpdate
from api_manager_books.security.auth_throttle import AuthThrottle
from api_manager_books.security.passwords import verify_password_async
from api_manager_books.security.refresh_tokens import create_refresh_token, hash_refresh_token

REFRESH_TOKEN_EXPIRE_DAYS = 14
LOGIN_TARGET_LIMIT = 5
LOGIN_IP_LIMIT = 30
REFRESH_TARGET_LIMIT = 5
REFRESH_IP_LIMIT = 60
AUTH_THROTTLE_WINDOW = timedelta(minutes=15)


@dataclass(frozen=True)
class TokenPair:
    """Пара access/refresh токенов."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserRecord(Protocol):
    """Пользователь для сервисных сценариев."""

    id: uuid.UUID
    email: str
    password_hash: bytes
    role: UserRole
    session: uuid.UUID | None
    refresh_token_hash: bytes | None
    refresh_token_expires_at: datetime | None


class UserStorage(Protocol):
    """Хранилище пользователей."""

    async def get_by_email(self, email: str) -> UserRecord | None:
        """Возвращает пользователя по email."""
        ...

    async def set_session_id(self, user_id: uuid.UUID, session_id: uuid.UUID | None) -> None:
        """Обновляет идентификатор сессии пользователя."""
        ...

    async def set_auth_session(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        refresh_token_hash: bytes,
        refresh_token_expires_at: datetime,
    ) -> None:
        """Сохраняет auth-сессию пользователя."""
        ...

    async def clear_auth_session(self, user_id: uuid.UUID) -> None:
        """Очищает auth-сессию пользователя."""
        ...

    async def count_admins(self) -> int:
        """Возвращает количество администраторов."""
        ...

    async def get_by_refresh_token_hash(self, refresh_token_hash: bytes) -> UserRecord | None:
        """Возвращает пользователя по хешу refresh token."""
        ...

    async def create_user(self, data: UserCreate) -> UserRecord:
        """Создает пользователя."""
        ...

    async def delete_user(self, user_id: uuid.UUID) -> bool:
        """Удаляет пользователя по идентификатору."""
        ...

    async def list_users(self) -> Sequence[object]:
        """Возвращает список пользователей."""
        ...

    async def ensure_exists(self, user_id: uuid.UUID) -> UserRecord:
        """Возвращает существующего пользователя."""
        ...

    async def update_user(
        self,
        user_id: uuid.UUID,
        *,
        email: str | None = None,
        password: str | None = None,
        role: UserRole | None = None,
    ) -> UserRecord | None:
        """Обновляет пользователя."""
        ...


class LogWriter(Protocol):
    """Хранилище логов действий."""

    async def log_from_dto(self, payload: LogCreate) -> Any:
        """Записывает лог из DTO."""
        ...

    async def log_action(
        self,
        *,
        user_id: uuid.UUID | None,
        action: str,
        entity: str | None = None,
        entity_id: uuid.UUID | None = None,
        details: str | None = None,
        **extra_fields: Any,
    ) -> Any:
        """Записывает лог действия."""
        ...


class NotificationManager(Protocol):
    """Менеджер уведомлений пользователя."""

    async def send_to_user(self, user_id: uuid.UUID, message: dict[str, Any]) -> None:
        """Отправить сообщение пользователю."""


class InvalidCredentialsError(Exception):
    """Неверный email или пароль пользователя."""


class InvalidRefreshTokenError(Exception):
    """Невалидный refresh token."""


class UserAlreadyExistsError(Exception):
    """Пользователь с таким email уже существует."""


class FirstUserMustBeAdminError(Exception):
    """Первый пользователь после default-пользователя должен быть администратором."""


class UserUpdateFailedError(Exception):
    """Репозиторий не вернул обновленного пользователя."""


class UserNotFoundInServiceError(Exception):
    """Пользователь не найден в пользовательском сценарии."""


class CannotRemoveLastAdminError(Exception):
    """Нельзя удалить последнего администратора."""


class CannotDemoteLastAdminError(Exception):
    """Нельзя понизить последнего администратора."""


def _is_user_not_found_error(exc: Exception) -> bool:
    """Проверяет ошибку отсутствующего пользователя."""
    return exc.__class__.__name__ == "UserNotFoundError"


def _utc_now() -> datetime:
    """Возвращает текущее UTC-время."""
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    """Нормализует дату из БД для сравнения с UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class UserService:
    """Сервис пользовательских сценариев без привязки к HTTP-слою."""

    def __init__(
        self,
        user_repo: UserStorage,
        log_repo: LogWriter,
        token_factory: Callable[[dict[str, Any]], str],
        notification_manager: NotificationManager,
        auth_throttle: AuthThrottle | None = None,
    ):
        """Инициализирует зависимости сервиса пользователей."""
        self._user_repo = user_repo
        self._log_repo = log_repo
        self._token_factory = token_factory
        self._notification_manager = notification_manager
        self._auth_throttle = auth_throttle or AuthThrottle()

    def _login_throttle_keys(self, email: str, client_ip: str) -> tuple[str, str]:
        return f"login:{email.strip().lower()}", f"login_ip:{client_ip}"

    def _refresh_throttle_keys(self, refresh_token: str, client_ip: str) -> tuple[str, str]:
        token_hash = hash_refresh_token(refresh_token).hex()
        return f"refresh:{token_hash}", f"refresh_ip:{client_ip}"

    async def login(self, email: str, password: str, *, client_ip: str = "unknown") -> TokenPair:
        """Авторизовать пользователя и вернуть пару токенов."""
        target_key, ip_key = self._login_throttle_keys(email, client_ip)
        self._auth_throttle.check(target_key, limit=LOGIN_TARGET_LIMIT, window=AUTH_THROTTLE_WINDOW)
        self._auth_throttle.check(ip_key, limit=LOGIN_IP_LIMIT, window=AUTH_THROTTLE_WINDOW)

        user = await self._user_repo.get_by_email(email)
        if user is None or not await verify_password_async(password, user.password_hash):
            self._auth_throttle.record_failure(
                target_key,
                limit=LOGIN_TARGET_LIMIT,
                window=AUTH_THROTTLE_WINDOW,
            )
            self._auth_throttle.record_failure(
                ip_key,
                limit=LOGIN_IP_LIMIT,
                window=AUTH_THROTTLE_WINDOW,
            )
            raise InvalidCredentialsError

        self._auth_throttle.clear(target_key)

        if user.session is not None:
            await self._notification_manager.send_to_user(
                user.id,
                {"type": "re_login", "message": "Сессия закрыта"},
            )

        session = uuid.uuid4()
        refresh_token = create_refresh_token()
        refresh_token_expires_at = _utc_now() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        await self._user_repo.set_auth_session(
            user.id,
            session,
            hash_refresh_token(refresh_token),
            refresh_token_expires_at,
        )
        token = self._token_factory(
            {
                "sub": str(user.id),
                "sid": str(session),
                "role": user.role,
                "type": "access",
            }
        )

        await self._log_repo.log_from_dto(
            LogCreate(
                user_id=user.id,
                action="login",
                entity="users",
                entity_id=user.id,
                details="Пользователь успешно авторизовался",
            )
        )
        return TokenPair(access_token=token, refresh_token=refresh_token)

    async def refresh(self, refresh_token: str, *, client_ip: str = "unknown") -> TokenPair:
        """Обновить пару токенов по валидному refresh token."""
        target_key, ip_key = self._refresh_throttle_keys(refresh_token, client_ip)
        self._auth_throttle.check(target_key, limit=REFRESH_TARGET_LIMIT, window=AUTH_THROTTLE_WINDOW)
        self._auth_throttle.check(ip_key, limit=REFRESH_IP_LIMIT, window=AUTH_THROTTLE_WINDOW)

        refresh_token_hash = hash_refresh_token(refresh_token)
        user = await self._user_repo.get_by_refresh_token_hash(refresh_token_hash)
        if user is None or user.refresh_token_expires_at is None:
            self._auth_throttle.record_failure(
                target_key,
                limit=REFRESH_TARGET_LIMIT,
                window=AUTH_THROTTLE_WINDOW,
            )
            self._auth_throttle.record_failure(
                ip_key,
                limit=REFRESH_IP_LIMIT,
                window=AUTH_THROTTLE_WINDOW,
            )
            raise InvalidRefreshTokenError

        if _as_utc(user.refresh_token_expires_at) <= _utc_now():
            self._auth_throttle.record_failure(
                target_key,
                limit=REFRESH_TARGET_LIMIT,
                window=AUTH_THROTTLE_WINDOW,
            )
            self._auth_throttle.record_failure(
                ip_key,
                limit=REFRESH_IP_LIMIT,
                window=AUTH_THROTTLE_WINDOW,
            )
            raise InvalidRefreshTokenError

        self._auth_throttle.clear(target_key)

        session = uuid.uuid4()
        new_refresh_token = create_refresh_token()
        refresh_token_expires_at = _utc_now() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        await self._user_repo.set_auth_session(
            user.id,
            session,
            hash_refresh_token(new_refresh_token),
            refresh_token_expires_at,
        )
        access_token = self._token_factory(
            {
                "sub": str(user.id),
                "sid": str(session),
                "role": user.role,
                "type": "access",
            }
        )
        return TokenPair(access_token=access_token, refresh_token=new_refresh_token)

    async def logout(self, user_id: uuid.UUID) -> None:
        """Закрыть текущую сессию пользователя."""
        await self._user_repo.clear_auth_session(user_id)

    async def add_user(self, payload: UserCreate, current_user: UserRead) -> dict[str, object]:
        """Добавить пользователя по текущим правилам HTTP-маршрута."""
        existing = await self._user_repo.get_by_email(payload.email)
        if existing is not None:
            raise UserAlreadyExistsError

        def_user = await self._user_repo.get_by_email("default@default.ru")
        if def_user is not None and payload.role != UserRole.ADMIN:
            raise FirstUserMustBeAdminError

        new_user = await self._user_repo.create_user(
            UserCreate(
                email=payload.email,
                password=payload.password,
                role=payload.role,
            )
        )

        await self._log_repo.log_from_dto(
            LogCreate(
                user_id=current_user.id,
                action="add_user",
                entity="users",
                entity_id=new_user.id,
                details=f"Добавлен пользователь {payload.email}",
            )
        )

        if def_user is not None and payload.role == UserRole.ADMIN:
            await self._notification_manager.send_to_user(
                def_user.id,
                {"type": "re_login", "message": "Сессия закрыта"},
            )
            await self._user_repo.delete_user(def_user.id)

        return {"message": "User added", "id": new_user.id}

    async def list_users(self) -> Sequence[object]:
        """Получить список пользователей."""
        return await self._user_repo.list_users()

    async def delete_user(self, user_id: uuid.UUID, current_user: UserRead) -> bool:
        """Залогировать удаление пользователя и удалить его."""
        try:
            target_user = await self._user_repo.ensure_exists(user_id)
        except Exception as exc:
            if _is_user_not_found_error(exc):
                raise UserNotFoundInServiceError from exc
            raise

        if target_user.role == UserRole.ADMIN and await self._user_repo.count_admins() <= 1:
            raise CannotRemoveLastAdminError

        await self._log_repo.log_action(
            user_id=current_user.id,
            action="delete",
            entity="users",
            entity_id=user_id,
            details="Пользователь удалён",
        )

        return await self._user_repo.delete_user(user_id)

    async def update_user(
        self,
        user_id: uuid.UUID,
        payload: UserUpdate,
        current_user: UserRead,
    ) -> None:
        """Обновить пользователя по текущим правилам HTTP-маршрута."""
        try:
            target_user = await self._user_repo.ensure_exists(user_id)
            if (
                target_user.role == UserRole.ADMIN
                and payload.role == UserRole.USER
                and await self._user_repo.count_admins() <= 1
            ):
                raise CannotDemoteLastAdminError

            update_user = await self._user_repo.update_user(
                user_id=user_id,
                password=payload.password,
                role=payload.role,
                email=payload.email,
            )
        except Exception as exc:
            if _is_user_not_found_error(exc):
                raise UserNotFoundInServiceError from exc
            raise

        if update_user is None:
            raise UserUpdateFailedError

        sensitive_update = payload.password is not None or payload.role is not None
        if sensitive_update:
            await self._user_repo.clear_auth_session(user_id)

        await self._log_repo.log_from_dto(
            LogCreate(
                user_id=current_user.id,
                action="update_user",
                entity="users",
                entity_id=update_user.id,
                details="Обновлен поля пользователь",
            )
        )
