import uuid
from typing import Any, AsyncIterable, AsyncIterator, Callable, Protocol

from src.DB.Repository.BookRepository.Shems import BookUpdate
from src.DB.Repository.BookRepository.book_repository import (
    BOOK_BINARY_CHUNK_SIZE,
    BookNotFoundError as RepositoryBookNotFoundError,
    BookRepository,
)
from src.DB.Repository.LogRepository.Shems import LogCreate
from src.DB.Repository.LogRepository.log_repository import LogRepository


class SessionManager(Protocol):
    """Менеджер сессий для чтения stream-данных."""

    def session(self) -> Any:
        """Вернуть async context manager сессии."""


class BookFileNotFoundInServiceError(Exception):
    """Книга не найдена при обновлении файла или обложки."""


class BookFileService:
    """Сервис сценариев работы с бинарными файлами книги."""

    def __init__(
        self,
        book_repo: BookRepository,
        log_repo: LogRepository,
        session_manager: SessionManager,
        book_repo_factory: Callable[[Any], BookRepository] = BookRepository,
    ):
        self._book_repo = book_repo
        self._log_repo = log_repo
        self._session_manager = session_manager
        self._book_repo_factory = book_repo_factory

    async def get_cover_meta(self, book_id: uuid.UUID):
        """Вернуть метаданные обложки или None."""
        return await self._book_repo.get_cover_meta(book_id)

    async def get_file_meta(self, book_id: uuid.UUID):
        """Вернуть метаданные файла или None."""
        return await self._book_repo.get_file_meta(book_id)

    async def iter_cover_chunks(self, book_id: uuid.UUID) -> AsyncIterator[bytes]:
        """Читать chunks обложки в отдельной сессии на время stream."""
        async with self._session_manager.session() as session:
            book_repo = self._book_repo_factory(session)
            async for chunk in book_repo.iter_cover_chunks(book_id):
                yield chunk

    async def iter_file_chunks(self, book_id: uuid.UUID) -> AsyncIterator[bytes]:
        """Читать chunks файла в отдельной сессии на время stream."""
        async with self._session_manager.session() as session:
            book_repo = self._book_repo_factory(session)
            async for chunk in book_repo.iter_file_chunks(book_id):
                yield chunk

    async def update_cover(
        self,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
        content_type: str | None,
        cover_chunks: AsyncIterable[bytes],
    ) -> None:
        """Обновить обложку книги и записать лог."""
        try:
            book = await self._book_repo.update_book(
                book_id,
                BookUpdate(cover_mime=content_type),
                cover_chunks=cover_chunks,
            )
        except RepositoryBookNotFoundError as exc:
            raise BookFileNotFoundInServiceError from exc

        await self._log_repo.log_from_dto(
            LogCreate(
                user_id=user_id,
                action="update_book_cover",
                entity="books",
                entity_id=book.id,
                details=f"Обновлена обложка книги '{book.title}' (id={book.id})",
            )
        )

    async def update_file(
        self,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
        filename: str | None,
        content_type: str | None,
        file_chunks: AsyncIterable[bytes],
    ) -> None:
        """Обновить файл книги и записать лог."""
        try:
            book = await self._book_repo.update_book(
                book_id,
                BookUpdate(
                    file_name=filename,
                    file_mime=content_type,
                ),
                file_chunks=file_chunks,
            )
        except RepositoryBookNotFoundError as exc:
            raise BookFileNotFoundInServiceError from exc

        await self._log_repo.log_from_dto(
            LogCreate(
                user_id=user_id,
                action="update_book_file",
                entity="books",
                entity_id=book.id,
                details=f"Обновлен файл книги '{book.title}' (id={book.id})",
            )
        )
