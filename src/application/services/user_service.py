import uuid
from typing import Any, Callable, Protocol, Sequence

from src.DB.Repository.LogRepository.Shems import LogCreate
from src.DB.Repository.LogRepository.log_repository import LogRepository
from src.DB.Repository.UserRepository.Enums import UserRole
from src.DB.Repository.UserRepository.Shems import UserCreate, UserRead, UserUpdate
from src.DB.Repository.UserRepository.user_repository import UserRepository
from src.security.passwords import verify_password


class NotificationManager(Protocol):
    """Менеджер уведомлений пользователя."""

    async def send_to_user(self, user_id: uuid.UUID, message: dict[str, Any]) -> None:
        """Отправить сообщение пользователю."""


class InvalidCredentialsError(Exception):
    """Неверный email или пароль пользователя."""


class UserAlreadyExistsError(Exception):
    """Пользователь с таким email уже существует."""


class FirstUserMustBeAdminError(Exception):
    """Первый пользователь после default-пользователя должен быть администратором."""


class UserUpdateFailedError(Exception):
    """Репозиторий не вернул обновленного пользователя."""


class UserService:
    """Сервис пользовательских сценариев без привязки к HTTP-слою."""

    def __init__(
        self,
        user_repo: UserRepository,
        log_repo: LogRepository,
        token_factory: Callable[[dict[str, Any]], str],
        notification_manager: NotificationManager,
    ):
        self._user_repo = user_repo
        self._log_repo = log_repo
        self._token_factory = token_factory
        self._notification_manager = notification_manager

    async def login(self, email: str, password: str) -> str:
        """Авторизовать пользователя и вернуть JWT access token."""
        user = await self._user_repo.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError

        if user.session is not None:
            await self._notification_manager.send_to_user(
                user.id,
                {"type": "re_login", "message": "Сессия закрыта"},
            )

        session = uuid.uuid4()
        await self._user_repo.set_session_id(user.id, session)
        token = self._token_factory(
            {
                "sub": str(user.id),
                "sid": str(session),
                "role": user.role,
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
        return token

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
        await self._user_repo.ensure_exists(user_id)
        update_user = await self._user_repo.update_user(
            user_id=user_id,
            password=payload.password,
            role=payload.role,
            email=payload.email,
        )
        if update_user is None:
            raise UserUpdateFailedError

        await self._log_repo.log_from_dto(
            LogCreate(
                user_id=current_user.id,
                action="update_user",
                entity="users",
                entity_id=update_user.id,
                details="Обновлен поля пользователь",
            )
        )
