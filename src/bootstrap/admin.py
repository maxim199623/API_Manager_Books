from sqlalchemy import select

from src.DB.Manager.manager import AsyncDBManager
from src.DB.Repository.UserRepository.Enums import UserRole
from src.DB.Repository.UserRepository.ORM import User
from src.schemas.users import UserCreate
from src.DB.Repository.UserRepository.user_repository import UserRepository


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
