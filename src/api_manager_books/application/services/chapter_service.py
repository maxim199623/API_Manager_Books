import uuid
from collections.abc import Sequence
from typing import Protocol

from api_manager_books.schemas.book_chapters import BookChapterCreate, BookChapterUpdate
from api_manager_books.schemas.logs import LogCreate


class BookRecord(Protocol):
    """Книга для сценариев глав."""

    id: uuid.UUID
    title: str


class ChapterRecord(Protocol):
    """Глава для сервисных сценариев."""

    id: uuid.UUID


class BookLookup(Protocol):
    """Хранилище проверки книг."""

    async def ensure_exists(self, book_id: uuid.UUID) -> BookRecord:
        """Возвращает существующую книгу."""
        ...


class ChapterStorage(Protocol):
    """Хранилище глав книги."""

    async def list_chapter_headers(self, book_id: uuid.UUID) -> Sequence[object]:
        """Возвращает заголовки глав книги."""
        ...

    async def count_chapters(self, book_id: uuid.UUID) -> int:
        """Возвращает количество глав книги."""
        ...

    async def ensure_exists_by_book_and_number(
        self,
        book_id: uuid.UUID,
        chapter_num: int,
    ) -> ChapterRecord:
        """Возвращает существующую главу по книге и номеру."""
        ...

    async def create_chapters(
        self,
        book_id: uuid.UUID,
        data: list[BookChapterCreate],
    ) -> int:
        """Создает главы книги."""
        ...

    async def update_chapter_by_number(
        self,
        book_id: uuid.UUID,
        chapter_num: int,
        data: BookChapterUpdate,
    ) -> ChapterRecord:
        """Обновляет главу по книге и номеру."""
        ...


class LogWriter(Protocol):
    """Хранилище логов действий."""

    async def log_from_dto(self, payload: LogCreate) -> None:
        """Записывает лог из DTO."""
        ...


class EmptyChapterListError(Exception):
    """Список глав пуст."""


class DuplicateChapterNumbersInRequestError(Exception):
    """В запросе есть повторяющиеся номера глав."""


class ChapterService:
    """Сервис сценариев чтения глав книги."""

    def __init__(
        self,
        book_repo: BookLookup,
        chapter_repo: ChapterStorage,
        log_repo: LogWriter,
    ):
        """Инициализирует зависимости сервиса глав."""
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

    async def add_chapters(
        self,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
        chapters: list[BookChapterCreate],
    ) -> None:
        """Добавить главы к книге и залогировать операцию."""
        book = await self._book_repo.ensure_exists(book_id)

        if not chapters:
            raise EmptyChapterListError

        chapter_numbers = [chapter.chapter for chapter in chapters]
        if len(chapter_numbers) != len(set(chapter_numbers)):
            raise DuplicateChapterNumbersInRequestError

        created_count = await self._chapter_repo.create_chapters(
            book_id=book.id,
            data=chapters,
        )

        await self._log_repo.log_from_dto(
            LogCreate(
                user_id=user_id,
                action="add_book_chapters",
                entity="book_chapters",
                entity_id=book.id,
                details=f"Добавлено глав: {created_count} для книги '{book.title}' (id={book.id})",
            )
        )

    async def update_chapter(
        self,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
        chapter_num: int,
        payload: BookChapterUpdate,
    ) -> None:
        """Обновить главу по номеру и залогировать изменение."""
        chapter = await self._chapter_repo.update_chapter_by_number(
            book_id=book_id,
            chapter_num=chapter_num,
            data=payload,
        )

        await self._log_repo.log_from_dto(
            LogCreate(
                user_id=user_id,
                action="update_chapter",
                entity="book_chapters",
                entity_id=chapter.id,
                details=f"Обновлена глава #{chapter_num} книги #{book_id}",
            )
        )
