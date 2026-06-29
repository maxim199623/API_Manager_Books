import uuid
from datetime import datetime
from typing import Protocol

from api_manager_books.schemas.logs import LogCreate


class BookLookup(Protocol):
    """Хранилище проверки книг."""

    async def ensure_exists(self, book_id: uuid.UUID) -> object:
        """Возвращает существующую книгу."""
        ...


class ChapterLookup(Protocol):
    """Хранилище поиска глав."""

    async def get_chapters_numbers_by_ids(self, chapter_ids: list[uuid.UUID]) -> list[int]:
        """Возвращает номера глав по идентификаторам."""
        ...


class ReadingProgressStorage(Protocol):
    """Хранилище прогресса чтения."""

    async def list_read_chapter_ids_for_user(
        self,
        *,
        user_id: uuid.UUID,
        offset: int,
        limit: int,
        cursor_read_at: datetime | None = None,
        cursor_chapter_id: uuid.UUID | None = None,
    ) -> list[uuid.UUID]:
        """Возвращает ID прочитанных глав пользователя."""
        ...

    async def list_read_chapter_ids_for_user_and_book(
        self,
        *,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
        offset: int,
        limit: int,
        cursor_read_at: datetime | None = None,
        cursor_chapter_id: uuid.UUID | None = None,
    ) -> list[uuid.UUID]:
        """Возвращает ID прочитанных глав пользователя по книге."""
        ...

    async def count_read_chapters_for_user_and_book(
        self,
        *,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
    ) -> int:
        """Возвращает число прочитанных глав пользователя по книге."""
        ...

    async def clear_read_history_for_user_and_book(
        self,
        *,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
    ) -> None:
        """Очищает историю чтения пользователя по книге."""
        ...


class LogWriter(Protocol):
    """Хранилище аудита."""

    async def log_from_dto(self, payload: LogCreate) -> None:
        """Записывает аудит-событие."""
        ...


class ReadingHistoryService:
    """Сервис сценариев истории чтения."""

    def __init__(
        self,
        book_repo: BookLookup,
        chapter_repo: ChapterLookup,
        progress_repo: ReadingProgressStorage,
        log_repo: LogWriter,
    ):
        """Инициализирует зависимости истории чтения."""
        self._book_repo = book_repo
        self._chapter_repo = chapter_repo
        self._progress_repo = progress_repo
        self._log_repo = log_repo

    async def list_read_chapters(
        self,
        user_id: uuid.UUID,
        book_id: uuid.UUID | None,
        offset: int,
        limit: int,
        cursor_read_at: datetime | None = None,
        cursor_chapter_id: uuid.UUID | None = None,
    ) -> list[int]:
        """Вернуть номера прочитанных глав пользователя."""
        cursor_kwargs = {}
        if cursor_read_at is not None and cursor_chapter_id is not None:
            cursor_kwargs = {
                "cursor_read_at": cursor_read_at,
                "cursor_chapter_id": cursor_chapter_id,
            }
        if book_id is None:
            chapter_ids = await self._progress_repo.list_read_chapter_ids_for_user(
                user_id=user_id,
                offset=offset,
                limit=limit,
                **cursor_kwargs,
            )
        else:
            chapter_ids = await self._progress_repo.list_read_chapter_ids_for_user_and_book(
                user_id=user_id,
                book_id=book_id,
                offset=offset,
                limit=limit,
                **cursor_kwargs,
            )

        if not chapter_ids:
            return []

        return await self._chapter_repo.get_chapters_numbers_by_ids(chapter_ids)

    async def count_read_chapters(self, user_id: uuid.UUID, book_id: uuid.UUID) -> int:
        """Вернуть количество прочитанных глав существующей книги."""
        await self._book_repo.ensure_exists(book_id)
        return await self._progress_repo.count_read_chapters_for_user_and_book(
            user_id=user_id,
            book_id=book_id,
        )

    async def clear_read_history_for_book(
        self,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
    ) -> None:
        """Очистить историю чтения книги для пользователя."""
        deleted_count = await self._progress_repo.clear_read_history_for_user_and_book(
            user_id=user_id,
            book_id=book_id,
        )
        await self._log_repo.log_from_dto(
            LogCreate(
                user_id=user_id,
                action="clear_read_history",
                entity="books",
                entity_id=book_id,
                details=(
                    f"Пользователь #{user_id} очистил историю чтения книги #{book_id} "
                    f"(удалено {deleted_count} записей прогресса)"
                ),
            )
        )
