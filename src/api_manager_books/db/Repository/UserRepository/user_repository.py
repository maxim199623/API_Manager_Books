import uuid
from collections.abc import Sequence
from datetime import datetime

from pydantic import EmailStr
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api_manager_books.db.Repository.UserRepository.ORM import User
from api_manager_books.schemas.enums import UserRole
from api_manager_books.schemas.users import UserCreate
from api_manager_books.security.passwords import hash_password


class EmailAlreadyExistsError(Exception):
    """Email уже занят."""

    pass


class UserNotFoundError(Exception):
    """Пользователь не найден."""

    pass


class UserRepository:
    """Репозиторий пользователей."""

    def __init__(self, session: AsyncSession):
        """Инициализировать репозиторий пользователей."""
        self._session = session

    async def create_user(self, data: UserCreate) -> User:
        """
        Создать пользователя.
        """

        user = User(
            email=data.email,
            password_hash=hash_password(data.password),
            role=data.role,
        )

        self._session.add(user)

        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise EmailAlreadyExistsError(f"User with email {data.email} already exists") from exc

        await self._session.refresh(user)
        return user

    async def get_by_email(self, email: EmailStr) -> User | None:
        """Получение пользователя по email"""
        stmt = select(User).where(User.email == email)
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_users(self, *, offset: int = 0, limit: int = 100) -> Sequence[User]:
        """Получение списка пользователей"""
        stmt = select(User).order_by(User.id).offset(offset).limit(limit)
        res = await self._session.execute(stmt)
        return res.scalars().all()

    async def count_admins(self) -> int:
        """Посчитать пользователей с ролью администратора."""
        stmt = select(func.count()).select_from(User).where(User.role == UserRole.ADMIN)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def delete_user(self, user_id: uuid.UUID) -> bool:
        """Удаление пользователя"""
        stmt = delete(User).where(User.id == user_id).returning(User.id)
        res = await self._session.execute(stmt)
        deleted_id = res.scalar_one_or_none()
        return deleted_id is not None

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Получение пользователя по id"""
        stmt = select(User).where(User.id == user_id)
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def ensure_exists(self, user_id: uuid.UUID) -> User:
        """Проверка существует ли пользователь"""
        user = await self.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"User #{user_id} not found")
        return user

    async def update_user(
            self,
            user_id: uuid.UUID,
            *,
            email: str | None = None,
            password: str | None = None,
            role: UserRole | None = None,
    ) -> User:
        """
        Обновить данные пользователя.
        Обновляются только поля, которые переданы.
        """
        user = await self.ensure_exists(user_id)

        # -------- email --------
        if email is not None and email != user.email:
            # проверяем уникальность нового email
            existing = await self.get_by_email(email)
            if existing and existing.id != user_id:
                raise EmailAlreadyExistsError(f"Email {email} already taken")

            user.email = email

        # -------- password_hash --------
        if password is not None:
            user.password_hash = hash_password(password)  # bytes

        # -------- role --------
        if role is not None:
            # Явно приводим к enum
            user.role = UserRole(role)

        # Запрос изменённого объекта к БД произойдёт при flush или commit
        await self._session.flush()
        await self._session.refresh(user)

        return user

    async def set_auth_session(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        refresh_token_hash: bytes,
        refresh_token_expires_at: datetime,
    ) -> None:
        """Сохранить текущую auth-сессию пользователя."""
        user = await self.ensure_exists(user_id)
        user.session = session_id
        user.refresh_token_hash = refresh_token_hash
        user.refresh_token_expires_at = refresh_token_expires_at
        await self._session.flush()
        await self._session.refresh(user)

    async def clear_auth_session(self, user_id: uuid.UUID) -> None:
        """Очистить текущую auth-сессию пользователя."""
        user = await self.ensure_exists(user_id)
        user.session = None
        user.refresh_token_hash = None
        user.refresh_token_expires_at = None
        await self._session.flush()
        await self._session.refresh(user)

    async def get_by_refresh_token_hash(self, refresh_token_hash: bytes) -> User | None:
        """Получить пользователя по хешу refresh token."""
        stmt = select(User).where(User.refresh_token_hash == refresh_token_hash)
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()
