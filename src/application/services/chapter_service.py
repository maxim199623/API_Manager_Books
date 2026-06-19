import uuid

from src.DB.Repository.BookChapterRepository.book_chapter_repository import BookChapterRepository
from src.DB.Repository.BookRepository.book_repository import BookRepository
from src.DB.Repository.LogRepository.Shems import LogCreate
from src.DB.Repository.LogRepository.log_repository import LogRepository


class ChapterService:
    """Сервис сценариев чтения глав книги."""

    def __init__(
        self,
        book_repo: BookRepository,
        chapter_repo: BookChapterRepository,
        log_repo: LogRepository,
    ):
        self._book_repo = book_repo
        self._chapter_repo = chapter_repo
        self._log_repo = log_repo

    async def list_chapter_headers(self, book_id: uuid.UUID):
        """Вернуть заголовки глав существующей книги."""
        book = await self._book_repo.ensure_exists(book_id)
        return await self._chapter_repo.list_chapter_headers(book.id)

    async def count_chapters(self, book_id: uuid.UUID) -> tuple[uuid.UUID, int]:
        """Вернуть ID существующей книги и количество ее глав."""
        book = await self._book_repo.ensure_exists(book_id)
        count = await self._chapter_repo.count_chapters(book.id)
        return book.id, count

    async def get_chapter(
        self,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
        chapter_num: int,
    ):
        """Вернуть главу по номеру и залогировать чтение."""
        chapter = await self._chapter_repo.ensure_exists_by_book_and_number(
            book_id=book_id,
            chapter_num=chapter_num,
        )

        await self._log_repo.log_from_dto(
            LogCreate(
                user_id=user_id,
                action="get_chapter",
                entity="book_chapters",
                entity_id=chapter.id,
                details=f"Пользователь запросил главу #{chapter_num} книги {book_id}",
            )
        )

        return chapter
