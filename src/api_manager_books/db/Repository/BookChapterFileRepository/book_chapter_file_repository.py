import uuid
from collections.abc import AsyncIterable, AsyncIterator, Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api_manager_books.db.Repository.BookChapterFileRepository.ORM import (
    BookChapterFile,
    BookChapterFileChunk,
)

CHAPTER_FILE_CHUNK_SIZE = 1024 * 1024


class BookChapterFileNotFoundError(Exception):
    """Файл главы не найден."""

    pass


@dataclass(frozen=True)
class BookChapterFileMeta:
    """Метаданные файла главы."""

    id: uuid.UUID
    chapter_id: uuid.UUID
    file_name: str
    extension: str | None
    content_type: str | None
    size: int
    chunks_count: int


class BookChapterFileRepository:
    """Репозиторий файлов глав книг."""

    def __init__(self, session: AsyncSession):
        """Инициализировать репозиторий файлов глав."""
        self._session = session

    async def create_file(
        self,
        chapter_id: uuid.UUID,
        *,
        file_name: str,
        content_type: str | None,
        chunks: AsyncIterable[bytes] | Iterable[bytes] | None,
    ) -> BookChapterFileMeta:
        """Создать файл главы и сохранить его непустые чанки."""
        chapter_file = BookChapterFile(
            chapter_id=chapter_id,
            file_name=file_name,
            extension=self._extract_extension(file_name),
            content_type=content_type,
            size=0,
            chunks_count=0,
        )
        self._session.add(chapter_file)
        await self._session.flush()

        size = 0
        chunks_count = 0
        async for chunk in self._iter_input_chunks(chunks):
            self._session.add(
                BookChapterFileChunk(
                    file_id=chapter_file.id,
                    chunk_index=chunks_count,
                    data=chunk,
                )
            )
            size += len(chunk)
            chunks_count += 1

        chapter_file.size = size
        chapter_file.chunks_count = chunks_count
        await self._session.flush()
        await self._session.refresh(chapter_file)
        return self._to_meta(chapter_file)

    async def list_files(
        self,
        chapter_id: uuid.UUID,
        *,
        name: str | None = None,
        extension: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[BookChapterFileMeta]:
        """Получить список файлов главы с фильтрами."""
        stmt = select(BookChapterFile).where(BookChapterFile.chapter_id == chapter_id)

        if name is not None:
            stmt = stmt.where(BookChapterFile.file_name.contains(name))

        normalized_extension = self._normalize_extension(extension)
        if normalized_extension is not None:
            stmt = stmt.where(BookChapterFile.extension == normalized_extension)

        stmt = (
            stmt.order_by(BookChapterFile.created_at.asc(), BookChapterFile.id.asc())
            .offset(offset)
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return [self._to_meta(chapter_file) for chapter_file in res.scalars().all()]

    async def get_file_meta(self, file_id: uuid.UUID) -> BookChapterFileMeta | None:
        """Получить метаданные файла главы."""
        chapter_file = await self._get_file(file_id)
        if chapter_file is None:
            return None
        return self._to_meta(chapter_file)

    async def ensure_file_belongs_to_chapter(
        self,
        chapter_id: uuid.UUID,
        file_id: uuid.UUID,
    ) -> BookChapterFile:
        """Проверить, что файл принадлежит главе."""
        stmt = select(BookChapterFile).where(
            BookChapterFile.id == file_id,
            BookChapterFile.chapter_id == chapter_id,
        )
        res = await self._session.execute(stmt)
        chapter_file = res.scalar_one_or_none()
        if chapter_file is None:
            raise BookChapterFileNotFoundError(
                f"Chapter file #{file_id} for chapter #{chapter_id} not found"
            )
        return chapter_file

    async def iter_file_chunks(self, file_id: uuid.UUID) -> AsyncIterator[bytes]:
        """Итерировать чанки файла главы в порядке сохранения."""
        stmt = (
            select(BookChapterFileChunk.data)
            .where(BookChapterFileChunk.file_id == file_id)
            .order_by(BookChapterFileChunk.chunk_index.asc())
        )
        result = await self._session.stream_scalars(stmt)
        async for chunk in result:
            yield chunk

    async def delete_file(self, chapter_id: uuid.UUID, file_id: uuid.UUID) -> bool:
        """Удалить файл, только если он принадлежит указанной главе."""
        try:
            chapter_file = await self.ensure_file_belongs_to_chapter(chapter_id, file_id)
        except BookChapterFileNotFoundError:
            return False

        await self._session.execute(
            delete(BookChapterFileChunk).where(BookChapterFileChunk.file_id == file_id)
        )
        await self._session.delete(chapter_file)
        await self._session.flush()
        return True

    async def validate_integrity(self, file_id: uuid.UUID) -> bool:
        """Проверить согласованность метаданных и чанков файла."""
        chapter_file = await self._get_file(file_id)
        if chapter_file is None:
            return False

        stmt = (
            select(BookChapterFileChunk.chunk_index, BookChapterFileChunk.data)
            .where(BookChapterFileChunk.file_id == file_id)
            .order_by(BookChapterFileChunk.chunk_index.asc())
        )
        res = await self._session.execute(stmt)
        rows = res.all()

        actual_chunks_count = len(rows)
        actual_size = sum(len(row.data) for row in rows)
        actual_indexes = [row.chunk_index for row in rows]
        expected_indexes = list(range(chapter_file.chunks_count))

        return (
            chapter_file.chunks_count == actual_chunks_count
            and chapter_file.size == actual_size
            and actual_indexes == expected_indexes
        )

    async def _get_file(self, file_id: uuid.UUID) -> BookChapterFile | None:
        """Получить ORM-файл по ID."""
        stmt = select(BookChapterFile).where(BookChapterFile.id == file_id)
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def _iter_input_chunks(
        self,
        chunks: AsyncIterable[bytes] | Iterable[bytes] | None,
    ) -> AsyncIterator[bytes]:
        """Итерировать входные чанки, пропуская пустые."""
        if chunks is None:
            return

        if isinstance(chunks, AsyncIterable):
            async for chunk in chunks:
                if chunk:
                    yield chunk
            return

        for chunk in chunks:
            if chunk:
                yield chunk

    def _to_meta(self, chapter_file: BookChapterFile) -> BookChapterFileMeta:
        """Преобразовать ORM-модель в метаданные файла."""
        return BookChapterFileMeta(
            id=chapter_file.id,
            chapter_id=chapter_file.chapter_id,
            file_name=chapter_file.file_name,
            extension=chapter_file.extension,
            content_type=chapter_file.content_type,
            size=chapter_file.size,
            chunks_count=chapter_file.chunks_count,
        )

    def _extract_extension(self, file_name: str) -> str | None:
        """Извлечь расширение файла без точки."""
        if "." not in file_name:
            return None

        extension = file_name.rsplit(".", 1)[1].lower()
        return extension or None

    def _normalize_extension(self, extension: str | None) -> str | None:
        """Нормализовать расширение для фильтрации."""
        if extension is None:
            return None

        normalized = extension.lower().lstrip(".")
        return normalized or None
