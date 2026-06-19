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

