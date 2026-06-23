import uuid

from src.DB.Repository.BookChapterRepository.book_chapter_repository import BookChapterRepository
from src.DB.Repository.BookRepository.book_repository import BookRepository
from src.DB.Repository.LogRepository.log_repository import LogRepository


class ReadingHistoryService:
    """Сервис сценариев истории чтения."""

    def __init__(
        self,
        book_repo: BookRepository,
        chapter_repo: BookChapterRepository,
        log_repo: LogRepository,
    ):
        self._book_repo = book_repo
        self._chapter_repo = chapter_repo
        self._log_repo = log_repo

    async def list_read_chapters(
        self,
        user_id: uuid.UUID,
        book_id: uuid.UUID | None,
        offset: int,
        limit: int,
    ) -> list[int]:
        """Вернуть номера прочитанных глав пользователя."""
        if book_id is None:
            chapter_ids = await self._log_repo.list_read_chapter_ids_for_user(
                user_id=user_id,
                offset=offset,
                limit=limit,
            )
        else:
            chapter_ids = await self._log_repo.list_read_chapter_ids_for_user_and_book(
                user_id=user_id,
                book_id=book_id,
                offset=offset,
                limit=limit,
            )

        if not chapter_ids:
            return []

        return await self._chapter_repo.get_chapters_numbers_by_ids(chapter_ids)

    async def count_read_chapters(self, user_id: uuid.UUID, book_id: uuid.UUID) -> int:
        """Вернуть количество прочитанных глав существующей книги."""
        await self._book_repo.ensure_exists(book_id)
        return await self._log_repo.count_read_chapters_for_user_and_book(
            user_id=user_id,
            book_id=book_id,
        )

    async def clear_read_history_for_book(
        self,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
    ) -> None:
        """Очистить историю чтения книги для пользователя."""
        await self._log_repo.clear_read_history_for_user_and_book(
            user_id=user_id,
            book_id=book_id,
        )
