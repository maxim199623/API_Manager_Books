import os

from sqlalchemy import select

from api_manager_books.db.Manager.manager import AsyncDBManager
from api_manager_books.db.Repository.UserRepository.ORM import User
from api_manager_books.db.Repository.UserRepository.user_repository import UserRepository
from api_manager_books.schemas.enums import UserRole
from api_manager_books.schemas.users import UserCreate
from api_manager_books.security.password_policy import WeakPasswordError, validate_password_strength


class InitialAdminRequiredError(RuntimeError):
    """Начальный администратор не настроен безопасно."""


def _initial_admin_credentials() -> tuple[str, str]:
    email = os.environ.get("INITIAL_ADMIN_EMAIL", "").strip()
    password = os.environ.get("INITIAL_ADMIN_PASSWORD", "")

    if not email or not password:
        raise InitialAdminRequiredError(
            "INITIAL_ADMIN_EMAIL and INITIAL_ADMIN_PASSWORD are required for first startup"
        )

    try:
        validate_password_strength(password)
    except WeakPasswordError as exc:
        raise InitialAdminRequiredError("INITIAL_ADMIN_PASSWORD is too weak") from exc

    return email, password


async def create_initial_admin(db_manager: AsyncDBManager) -> None:
    """Создает первого администратора только из явно заданных переменных окружения."""
    async with db_manager.session() as session:
        repo = UserRepository(session)
        result = await session.execute(select(User.id).limit(1))
        exists = result.scalar_one_or_none()

        if exists is not None:
            return

        email, password = _initial_admin_credentials()

        await repo.create_user(
            UserCreate(
                email=email,
                password=password,
                role=UserRole.ADMIN,
            )
        )
