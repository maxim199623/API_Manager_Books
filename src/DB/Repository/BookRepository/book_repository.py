import uuid
from typing import Sequence

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.DB.Repository.BookRepository.ORM import Book
from src.DB.Repository.BookRepository.Shems import BookCreate, BookUpdate
from src.DB.Repository.utils import patch_model_from_schema, build_model_from_schema


class BookNotFoundError(Exception):
    """Книга не найдена."""
    pass


class BookRepository:
    """
    Репозиторий для работы с таблицей books.

    Поля: ID, COVER(bytea), TITLE, AUTHOR, DESCRIPTION, SERIES, FORMAT, FILE(bytea).
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_book(self, data: BookCreate) -> Book:
        """
        Создать новую книгу.
        """
        book = build_model_from_schema(Book, data)

        self._session.add(book)
        await self._session.flush()
        await self._session.refresh(book)
        return book

    async def get_by_id(self, book_id: uuid.UUID) -> Book | None:
        """Получение Книги по ID"""
        stmt = select(Book).where(Book.id == book_id)
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def ensure_exists(self, book_id: uuid.UUID) -> Book:
        """Проверка существования книги"""
        book = await self.get_by_id(book_id)
        if book is None:
            raise BookNotFoundError(f"Book #{book_id} not found")
        return book

    async def delete_book(self, book_id: uuid.UUID) -> bool:
        """Удаление книги"""
        book = await self.get_by_id(book_id)
        if book is None:
            return False

        await self._session.delete(book)
        await self._session.flush()
        return True

    async def list_books(
        self,
        *,
        author: str | None = None,
        series: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Book]:
        """
        Общий метод выборки книг с фильтрами по автору и серии.
        """
        stmt = select(Book)

        if author is not None:
            stmt = stmt.where(Book.author == author)

        if series is not None:
            stmt = stmt.where(Book.series == series)

        stmt = stmt.order_by(Book.id).offset(offset).limit(limit)

        res = await self._session.execute(stmt)
        return res.scalars().all()

    async def get_by_author(
        self,
        author: str,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Book]:
        return await self.list_books(author=author, offset=offset, limit=limit)

    async def get_by_series(
        self,
        series: str,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Book]:
        return await self.list_books(series=series, offset=offset, limit=limit)

    async def update_book(self, book_id: uuid.UUID, data: BookUpdate) -> Book:
        """
        Частично обновить книгу.

        Обновляются только поля, которые:
        - переданы в Pydantic-схеме (exclude_unset),
        - существуют в ORM-модели Book.
        """
        book = await self.ensure_exists(book_id)

        patch_model_from_schema(book, data)

        await self._session.flush()
        await self._session.refresh(book)
        return book

    async def get_by_title_author(self, title: str, author: str|None) -> Book | None:
        """
        Поиск книги по названию и автору (для проверки дубликатов).
        """
        stmt = select(Book).where(
            Book.title == title,
            Book.author == author,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()