from dataclasses import dataclass
import uuid
from typing import Sequence

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.DB.Repository.BookChapterRepository.ORM import BookChapter
from src.DB.Repository.BookChapterRepository.Shems import BookChapterCreate, BookChapterUpdate
from src.DB.Repository.utils import patch_model_from_schema, build_model_from_schema


class BookChapterNotFoundError(Exception):
    """Глава не найдена."""
    pass


@dataclass(frozen=True)
class BookChapterHeader:
    chapter: int
    chapter_name: str | None


class BookChapterRepository:
    """
    Репозиторий для работы с главами книг (book_chapters).
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_chapters(
        self,
        book_id: uuid.UUID,
        data: Sequence[BookChapterCreate],
    ) -> int:
        """
        Добавить список глав для книги book_id.
        """
        if not data:
            return 0

        chapters = [
        build_model_from_schema(
            BookChapter,
            chapter,
            extra={"book_id": book_id},
        )
        for chapter in data
    ]


        self._session.add_all(chapters)
        await self._session.flush()
        return len(chapters)

    async def get_by_id(self, chapter_id: uuid.UUID) -> BookChapter | None:
        """Получение главы по ID"""
        stmt = select(BookChapter).where(BookChapter.id == chapter_id)
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_book_and_number(
        self,
        book_id: uuid.UUID,
        chapter_num: int,
    ) -> BookChapter | None:
        """Получаем корректную главу конкретной книги"""
        stmt = select(BookChapter).where(
            BookChapter.book_id == book_id,
            BookChapter.chapter == chapter_num,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def ensure_exists_by_id(self, chapter_id: uuid.UUID) -> BookChapter:
        """Проверка на существование"""
        chapter = await self.get_by_id(chapter_id)
        if chapter is None:
            raise BookChapterNotFoundError(f"Chapter #{chapter_id} not found")
        return chapter

    async def ensure_exists_by_book_and_number(
        self,
        book_id: uuid.UUID,
        chapter_num: int,
    ) -> BookChapter:
        """Проверка на существование"""
        chapter = await self.get_by_book_and_number(book_id, chapter_num)
        if chapter is None:
            raise BookChapterNotFoundError(
                f"Chapter {chapter_num} for book #{book_id} not found"
            )
        return chapter

    async def list_chapters(
        self,
        book_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 1000,
    ) -> Sequence[BookChapter]:
        """
        Список глав книги, отсортированных по номеру.
        """
        stmt = (
            select(BookChapter)
            .where(BookChapter.book_id == book_id)
            .order_by(BookChapter.chapter)
            .offset(offset)
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return res.scalars().all()

    async def list_chapter_headers(
        self,
        book_id: uuid.UUID,
    ) -> Sequence[BookChapterHeader]:
        """
        Получение списка с названием и номером главы
        """
        stmt = (
            select(BookChapter.chapter, BookChapter.chapter_name)
            .where(BookChapter.book_id == book_id)
            .order_by(BookChapter.chapter)
        )
        res = await self._session.execute(stmt)
        return [
            BookChapterHeader(
                chapter=row.chapter,
                chapter_name=row.chapter_name,
            )
            for row in res.all()
        ]

    async def count_chapters(self, book_id: uuid.UUID) -> int:
        """
        Количество глав книги.
        """
        stmt = select(func.count()).select_from(BookChapter).where(
            BookChapter.book_id == book_id
        )
        res = await self._session.execute(stmt)
        return res.scalar_one()

    async def update_chapter_by_number(
        self,
        book_id: uuid.UUID,
        chapter_num: int,
        data: BookChapterUpdate,
    ) -> BookChapter:
        """
        Частично обновить главу по (book_id, chapter_num).

        Меняется любой набор полей, который есть одновременно
        в Pydantic-схеме и ORM-модели.
        """
        chapter = await self.ensure_exists_by_book_and_number(book_id, chapter_num)

        patch_model_from_schema(chapter, data)

        await self._session.flush()
        await self._session.refresh(chapter)
        return chapter

    async def delete_chapter_by_number(
        self,
        book_id: uuid.UUID,
        chapter_num: int,
    ) -> bool:
        """
        Удалить главу по (book_id, chapter_num).
        Возвращает True, если была удалена.
        """
        stmt = (
            delete(BookChapter)
            .where(
                BookChapter.book_id == book_id,
                BookChapter.chapter == chapter_num,
            )
            .returning(BookChapter.id)
        )
        res = await self._session.execute(stmt)
        deleted_id = res.scalar_one_or_none()
        return deleted_id is not None

    async def delete_all_for_book(self, book_id: uuid.UUID) -> int:
        """
        Удалить все главы конкретной книги.
        Возвращает количество удалённых глав.
        """
        stmt = (
            delete(BookChapter)
            .where(BookChapter.book_id == book_id)
            .returning(BookChapter.id)
        )
        res = await self._session.execute(stmt)
        deleted_ids = res.scalars().all()
        return len(deleted_ids)

    async def get_by_ids(self, ids: Sequence[uuid.UUID]) -> Sequence[BookChapter]:
        """
        Получить главы по списку их ID.
        """
        if not ids:
            return []

        stmt = select(BookChapter).where(BookChapter.id.in_(ids))
        res = await self._session.execute(stmt)
        return res.scalars().all()

    async def get_chapters_numbers_by_ids(self, ids: Sequence[uuid.UUID]) -> list[int]:
        """
        Получить список номеров глав (chapter) по списку ID.
        """
        if not ids:
            return []

        stmt = select(BookChapter.chapter).where(BookChapter.id.in_(ids))
        res = await self._session.execute(stmt)
        return list(res.scalars().all())
