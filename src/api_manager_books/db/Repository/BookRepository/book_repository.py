import uuid
from collections.abc import AsyncIterable, AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api_manager_books.db.Repository.BookChapterRepository.ORM import BookChapter
from api_manager_books.db.Repository.BookRepository.ORM import Book, BookCoverChunk, BookFileChunk
from api_manager_books.db.Repository.LogRepository.ORM import LogEntry
from api_manager_books.db.Repository.utils import build_model_from_schema, patch_model_from_schema
from api_manager_books.schemas.books import BookCreate, BookUpdate

BOOK_BINARY_CHUNK_SIZE = 1024 * 1024

BookSortField = Literal["created_at", "progress", "title"]
SortDirection = Literal["asc", "desc"]


class BookNotFoundError(Exception):
    """Книга не найдена."""
    pass


@dataclass(frozen=True)
class BookBinaryMeta:
    """Метаданные бинарного файла книги."""

    content_type: str | None
    file_name: str | None
    size: int


class BookRepository:
    """
    Репозиторий для работы с таблицей books.

    Крупные бинарные данные книги хранятся chunk-таблицах, а не в books.
    """

    def __init__(self, session: AsyncSession):
        """Инициализировать репозиторий книг."""
        self._session = session

    async def create_book(
        self,
        data: BookCreate,
        *,
        cover_chunks: AsyncIterable[bytes] | None = None,
        file_chunks: AsyncIterable[bytes] | None = None,
    ) -> Book:
        """
        Создать новую книгу.
        """
        book = build_model_from_schema(Book, data)

        self._session.add(book)
        await self._session.flush()
        await self._replace_cover(
            book,
            payload=data.cover,
            chunks=cover_chunks,
            content_type=data.cover_mime,
        )
        await self._replace_file(
            book,
            payload=data.file,
            chunks=file_chunks,
            content_type=data.file_mime,
            file_name=data.file_name,
        )
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
        sort_by: BookSortField = "created_at",
        sort_dir: SortDirection = "desc",
        user_id: uuid.UUID | None = None,
    ) -> Sequence[Book]:
        """
        Общий метод выборки книг с фильтрами по автору и серии.
        """
        stmt = select(Book)

        if author is not None:
            stmt = stmt.where(Book.author == author)

        if series is not None:
            stmt = stmt.where(Book.series == series)

        if sort_by == "progress":
            if user_id is None:
                raise ValueError("user_id is required for progress sorting")

            chapters_count = (
                select(
                    BookChapter.book_id.label("book_id"),
                    func.count(BookChapter.id).label("chapters_count"),
                )
                .group_by(BookChapter.book_id)
                .subquery()
            )
            read_count = (
                select(
                    BookChapter.book_id.label("book_id"),
                    func.count(func.distinct(LogEntry.entity_id)).label("read_count"),
                )
                .join(LogEntry, LogEntry.entity_id == BookChapter.id)
                .where(
                    LogEntry.user_id == user_id,
                    LogEntry.action == "get_chapter",
                    LogEntry.entity == "book_chapters",
                )
                .group_by(BookChapter.book_id)
                .subquery()
            )

            stmt = (
                stmt.outerjoin(chapters_count, chapters_count.c.book_id == Book.id)
                .outerjoin(read_count, read_count.c.book_id == Book.id)
            )
            total_chapters = func.coalesce(chapters_count.c.chapters_count, 0)
            read_chapters = func.coalesce(read_count.c.read_count, 0)
            sort_expression = case(
                (total_chapters == 0, 0.0),
                else_=read_chapters * 1.0 / total_chapters,
            )
        else:
            sort_columns = {
                "created_at": Book.created_at,
                "title": Book.title,
            }
            sort_expression = sort_columns[sort_by]

        ordered_expression = (
            sort_expression.desc()
            if sort_dir == "desc"
            else sort_expression.asc()
        )

        stmt = stmt.order_by(ordered_expression, Book.id.asc()).offset(offset).limit(limit)

        res = await self._session.execute(stmt)
        return res.scalars().all()

    async def get_by_author(
        self,
        author: str,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Book]:
        """Получить книги автора."""
        return await self.list_books(author=author, offset=offset, limit=limit)

    async def get_by_series(
        self,
        series: str,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Book]:
        """Получить книги серии."""
        return await self.list_books(series=series, offset=offset, limit=limit)

    async def update_book(
        self,
        book_id: uuid.UUID,
        data: BookUpdate,
        *,
        cover_chunks: AsyncIterable[bytes] | None = None,
        file_chunks: AsyncIterable[bytes] | None = None,
    ) -> Book:
        """
        Частично обновить книгу.

        Обновляются только поля, которые:
        - переданы в Pydantic-схеме (exclude_unset),
        - существуют в ORM-модели Book.
        """
        book = await self.ensure_exists(book_id)

        patch_model_from_schema(book, data)

        if cover_chunks is not None or "cover" in data.model_fields_set:
            await self._replace_cover(
                book,
                payload=data.cover,
                chunks=cover_chunks,
                content_type=data.cover_mime,
                preserve_meta=cover_chunks is None and data.cover is not None,
            )

        if file_chunks is not None or "file" in data.model_fields_set:
            await self._replace_file(
                book,
                payload=data.file,
                chunks=file_chunks,
                content_type=data.file_mime,
                file_name=data.file_name,
                preserve_meta=file_chunks is None and data.file is not None,
            )

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

    async def get_cover_meta(self, book_id: uuid.UUID) -> BookBinaryMeta | None:
        """Получить метаданные обложки книги."""
        book = await self.get_by_id(book_id)
        if book is None or book.cover_size <= 0:
            return None

        return BookBinaryMeta(
            content_type=book.cover_mime,
            file_name=None,
            size=book.cover_size,
        )

    async def get_file_meta(self, book_id: uuid.UUID) -> BookBinaryMeta | None:
        """Получить метаданные файла книги."""
        book = await self.get_by_id(book_id)
        if book is None or book.file_size <= 0:
            return None

        return BookBinaryMeta(
            content_type=book.file_mime,
            file_name=book.file_name,
            size=book.file_size,
        )

    async def get_cover_bytes(self, book_id: uuid.UUID) -> bytes | None:
        """Получить байты обложки книги."""
        chunks = [chunk async for chunk in self.iter_cover_chunks(book_id)]
        if not chunks:
            return None
        return b"".join(chunks)

    async def get_file_bytes(self, book_id: uuid.UUID) -> bytes | None:
        """Получить байты файла книги."""
        chunks = [chunk async for chunk in self.iter_file_chunks(book_id)]
        if not chunks:
            return None
        return b"".join(chunks)

    async def iter_cover_chunks(self, book_id: uuid.UUID) -> AsyncIterator[bytes]:
        """Итерировать чанки обложки книги."""
        stmt = (
            select(BookCoverChunk.data)
            .where(BookCoverChunk.book_id == book_id)
            .order_by(BookCoverChunk.chunk_index)
        )
        result = await self._session.stream_scalars(stmt)
        async for chunk in result:
            yield chunk

    async def iter_file_chunks(self, book_id: uuid.UUID) -> AsyncIterator[bytes]:
        """Итерировать чанки файла книги."""
        stmt = (
            select(BookFileChunk.data)
            .where(BookFileChunk.book_id == book_id)
            .order_by(BookFileChunk.chunk_index)
        )
        result = await self._session.stream_scalars(stmt)
        async for chunk in result:
            yield chunk

    async def _replace_cover(
        self,
        book: Book,
        *,
        payload: bytes | None,
        chunks: AsyncIterable[bytes] | None,
        content_type: str | None,
        preserve_meta: bool = False,
    ) -> None:
        """Заменить чанки обложки книги."""
        await self._delete_chunks(BookCoverChunk, book.id)
        size = await self._store_chunks(
            BookCoverChunk,
            book.id,
            payload=payload,
            chunks=chunks,
        )
        if size > 0:
            if content_type is not None:
                book.cover_mime = content_type
        else:
            book.cover_mime = book.cover_mime if preserve_meta else None
        book.cover_size = size

    async def _replace_file(
        self,
        book: Book,
        *,
        payload: bytes | None,
        chunks: AsyncIterable[bytes] | None,
        content_type: str | None,
        file_name: str | None,
        preserve_meta: bool = False,
    ) -> None:
        """Заменить чанки файла книги."""
        await self._delete_chunks(BookFileChunk, book.id)
        size = await self._store_chunks(
            BookFileChunk,
            book.id,
            payload=payload,
            chunks=chunks,
        )
        if size > 0:
            if content_type is not None:
                book.file_mime = content_type
            if file_name is not None:
                book.file_name = file_name
        else:
            if not preserve_meta:
                book.file_mime = None
                book.file_name = None
        book.file_size = size

    async def _delete_chunks(self, chunk_model, book_id: uuid.UUID) -> None:
        """Удалить чанки книги."""
        stmt = delete(chunk_model).where(chunk_model.book_id == book_id)
        await self._session.execute(stmt)

    async def _store_chunks(
        self,
        chunk_model,
        book_id: uuid.UUID,
        *,
        payload: bytes | None,
        chunks: AsyncIterable[bytes] | None,
    ) -> int:
        """Сохранить чанки книги."""
        if chunks is None and payload is None:
            return 0

        total_size = 0
        chunk_index = 0

        async for chunk in self._iter_input_chunks(payload=payload, chunks=chunks):
            self._session.add(
                chunk_model(
                    book_id=book_id,
                    chunk_index=chunk_index,
                    data=chunk,
                )
            )
            total_size += len(chunk)
            chunk_index += 1

        await self._session.flush()
        return total_size

    async def _iter_input_chunks(
        self,
        *,
        payload: bytes | None,
        chunks: AsyncIterable[bytes] | None,
    ) -> AsyncIterator[bytes]:
        """Итерировать входные бинарные данные."""
        if chunks is not None:
            async for chunk in chunks:
                if chunk:
                    yield chunk
            return

        if payload is None:
            return

        for start in range(0, len(payload), BOOK_BINARY_CHUNK_SIZE):
            chunk = payload[start:start + BOOK_BINARY_CHUNK_SIZE]
            if chunk:
                yield chunk
