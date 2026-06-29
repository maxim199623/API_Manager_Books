from fastapi import Depends, Request
from starlette.requests import HTTPConnection

from api_manager_books.api.security.jwt_tokens import create_access_token
from api_manager_books.api.websocket import manager as ws_manager
from api_manager_books.application.services.book_file_service import BookFileService
from api_manager_books.application.services.book_service import BookService
from api_manager_books.application.services.chapter_file_service import ChapterFileService
from api_manager_books.application.services.chapter_service import ChapterService
from api_manager_books.application.services.favorite_service import FavoriteService
from api_manager_books.application.services.reading_history_service import ReadingHistoryService
from api_manager_books.application.services.settings_service import SettingsService
from api_manager_books.application.services.user_service import UserService
from api_manager_books.config.config import SettingsManager
from api_manager_books.db.base import Base
from api_manager_books.db.Manager.manager import AsyncDBManager
from api_manager_books.db.Repository.BookChapterFileRepository.book_chapter_file_repository import (
    BookChapterFileRepository,
)
from api_manager_books.db.Repository.BookChapterRepository.book_chapter_repository import BookChapterRepository
from api_manager_books.db.Repository.BookRepository.book_repository import BookRepository
from api_manager_books.db.Repository.FavoriteBookRepository.favorite_book_repository import FavoriteBookRepository
from api_manager_books.db.Repository.LogRepository.log_repository import LogRepository
from api_manager_books.db.Repository.ReadingProgressRepository.reading_progress_repository import (
    ReadingProgressRepository,
)
from api_manager_books.db.Repository.UserRepository.user_repository import UserRepository
from api_manager_books.schemas.config import DatabaseSettings


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


async def get_reading_progress_repo(session=Depends(get_session)) -> ReadingProgressRepository:
    """Получаем ReadingProgressRepository"""
    return ReadingProgressRepository(session)


async def get_user_service(
    user_repo: UserRepository = Depends(get_user_repo),
    log_repo: LogRepository = Depends(get_log_repo),
) -> UserService:
    """Получаем UserService"""
    return UserService(
        user_repo=user_repo,
        log_repo=log_repo,
        token_factory=create_access_token,
        notification_manager=ws_manager,
    )


async def get_book_repo(session=Depends(get_session)) -> BookRepository:
    """Получаем BookRepository"""
    return BookRepository(session)


async def get_book_file_service(
    db_manager: AsyncDBManager = Depends(get_db_manager),
    book_repo: BookRepository = Depends(get_book_repo),
    log_repo: LogRepository = Depends(get_log_repo),
) -> BookFileService:
    """Получаем BookFileService"""
    return BookFileService(
        book_repo=book_repo,
        log_repo=log_repo,
        session_manager=db_manager,
        book_repo_factory=BookRepository,
    )


async def get_favorite_book_repo(session=Depends(get_session)) -> FavoriteBookRepository:
    """Получаем FavoriteBookRepository"""
    return FavoriteBookRepository(session)


async def get_book_service(
    book_repo: BookRepository = Depends(get_book_repo),
    favorite_book_repo: FavoriteBookRepository = Depends(get_favorite_book_repo),
    log_repo: LogRepository = Depends(get_log_repo),
) -> BookService:
    """Получаем BookService"""
    return BookService(
        book_repo=book_repo,
        favorite_book_repo=favorite_book_repo,
        log_repo=log_repo,
        notification_manager=ws_manager,
    )


async def get_favorite_service(
    book_repo: BookRepository = Depends(get_book_repo),
    favorite_book_repo: FavoriteBookRepository = Depends(get_favorite_book_repo),
    log_repo: LogRepository = Depends(get_log_repo),
) -> FavoriteService:
    """Получаем FavoriteService"""
    return FavoriteService(
        book_repo=book_repo,
        favorite_book_repo=favorite_book_repo,
        log_repo=log_repo,
    )


async def get_book_chapter_repo(session=Depends(get_session)) -> BookChapterRepository:
    """Получаем BookChapterRepository"""
    return BookChapterRepository(session)


async def get_book_chapter_file_repo(session=Depends(get_session)) -> BookChapterFileRepository:
    """Получаем BookChapterFileRepository"""
    return BookChapterFileRepository(session)


async def get_chapter_service(
    book_repo: BookRepository = Depends(get_book_repo),
    chapter_repo: BookChapterRepository = Depends(get_book_chapter_repo),
    log_repo: LogRepository = Depends(get_log_repo),
    reading_progress_repo: ReadingProgressRepository = Depends(get_reading_progress_repo),
) -> ChapterService:
    """Получаем ChapterService"""
    return ChapterService(
        book_repo=book_repo,
        chapter_repo=chapter_repo,
        log_repo=log_repo,
        reading_progress_repo=reading_progress_repo,
    )


async def get_chapter_file_service(
    db_manager: AsyncDBManager = Depends(get_db_manager),
    chapter_repo: BookChapterRepository = Depends(get_book_chapter_repo),
    file_repo: BookChapterFileRepository = Depends(get_book_chapter_file_repo),
    log_repo: LogRepository = Depends(get_log_repo),
) -> ChapterFileService:
    """Получаем ChapterFileService"""
    return ChapterFileService(
        chapter_repo=chapter_repo,
        file_repo=file_repo,
        log_repo=log_repo,
        session_manager=db_manager,
        file_repo_factory=BookChapterFileRepository,
    )


async def get_reading_history_service(
    book_repo: BookRepository = Depends(get_book_repo),
    chapter_repo: BookChapterRepository = Depends(get_book_chapter_repo),
    reading_progress_repo: ReadingProgressRepository = Depends(get_reading_progress_repo),
    log_repo: LogRepository = Depends(get_log_repo),
) -> ReadingHistoryService:
    """Получаем ReadingHistoryService"""
    return ReadingHistoryService(
        book_repo=book_repo,
        chapter_repo=chapter_repo,
        progress_repo=reading_progress_repo,
        log_repo=log_repo,
    )


def get_settings_manager(request: Request) -> SettingsManager:
    """Получаем settings_manager"""
    return request.app.state.settings_manager


def create_settings_db_manager(db_settings: DatabaseSettings) -> AsyncDBManager:
    """Создаем менеджер базы данных для обновленных настроек."""
    return AsyncDBManager(db_settings, Base)


def get_settings_service(
    settings_manager: SettingsManager = Depends(get_settings_manager),
) -> SettingsService:
    """Получаем SettingsService"""
    return SettingsService(
        settings_manager=settings_manager,
        db_manager_factory=create_settings_db_manager,
    )

