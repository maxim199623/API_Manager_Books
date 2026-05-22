from fastapi import Depends, Request
from starlette.requests import HTTPConnection

from src.DB.Manager.manager import AsyncDBManager
from src.DB.Repository.BookChapterRepository.book_chapter_repository import BookChapterRepository
from src.DB.Repository.BookRepository.book_repository import BookRepository
from src.DB.Repository.FavoriteBookRepository.favorite_book_repository import FavoriteBookRepository
from src.DB.Repository.LogRepository.log_repository import LogRepository
from src.DB.Repository.UserRepository.user_repository import UserRepository
from src.core.config import SettingsManager


def get_db_manager(conn: HTTPConnection) -> AsyncDBManager:
    """Получаем db_manager"""
    return conn.app.state.db_manager


async def get_session(db_manager: AsyncDBManager = Depends(get_db_manager)):
    """Получаем сессию"""
    async with db_manager.session() as session:
        yield session


async def get_user_repo(session=Depends(get_session)) -> UserRepository:
    """Получаем UserRepository"""
    return UserRepository(session)


async def get_log_repo(session=Depends(get_session)) -> LogRepository:
    """Получаем LogRepository"""
    return LogRepository(session)


async def get_book_repo(session=Depends(get_session)) -> BookRepository:
    """Получаем BookRepository"""
    return BookRepository(session)


async def get_favorite_book_repo(session=Depends(get_session)) -> FavoriteBookRepository:
    """Получаем FavoriteBookRepository"""
    return FavoriteBookRepository(session)


async def get_book_chapter_repo(session=Depends(get_session)) -> BookChapterRepository:
    """Получаем BookChapterRepository"""
    return BookChapterRepository(session)

def get_settings_manager(request: Request) -> SettingsManager:
    """Получаем settings_manager"""
    return request.app.state.settings_manager


async def create_default_admin(db_manager: AsyncDBManager) -> None:
    """
    Создаёт администратора, если таблица users пуста.
    """
    async with db_manager.session() as session:
        from src.DB.Repository.UserRepository.user_repository import UserRepository
        from src.DB.Repository.UserRepository.Shems import UserCreate
        from src.DB.Repository.UserRepository.Enums import UserRole
        from src.DB.Repository.UserRepository.ORM import User

        repo = UserRepository(session)

        # Проверяем, есть ли уже пользователи
        from sqlalchemy import select
        result = await session.execute(select(User.id).limit(1))
        exists = result.scalar_one_or_none()

        if exists is not None:
            return  # Юзеры есть — ничего не делаем

        # хеш пароля
        default_password_hash = "default"

        admin = await repo.create_user(
            UserCreate(
                email="default@default.ru",
                password=default_password_hash,
                role=UserRole.ADMIN,
            )
        )
        print(f"[INIT] Создан администратор: {admin.email}")

