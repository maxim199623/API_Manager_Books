from sqlalchemy import select

from api_manager_books.db.Manager.manager import AsyncDBManager
from api_manager_books.schemas.enums import UserRole
from api_manager_books.db.Repository.UserRepository.ORM import User
from api_manager_books.schemas.users import UserCreate
from api_manager_books.db.Repository.UserRepository.user_repository import UserRepository


async def create_default_admin(db_manager: AsyncDBManager) -> None:
    """Создает администратора по умолчанию, если пользователей еще нет."""
    async with db_manager.session() as session:
        repo = UserRepository(session)
        result = await session.execute(select(User.id).limit(1))
        exists = result.scalar_one_or_none()

        if exists is not None:
            return

        await repo.create_user(
            UserCreate(
                email="default@default.ru",
                password="default",
                role=UserRole.ADMIN,
            )
        )
