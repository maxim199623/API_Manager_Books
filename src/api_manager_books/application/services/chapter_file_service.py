import uuid
from collections.abc import AsyncIterable, AsyncIterator, Callable, Sequence
from typing import Any, Protocol

from api_manager_books.schemas.logs import LogCreate


class SessionManager(Protocol):
    """Менеджер сессий для stream-чтения файла главы."""

    def session(self) -> Any:
        """Вернуть async context manager сессии."""
        ...


class ChapterRecord(Protocol):
    """Глава, найденная по книге и номеру."""

    id: uuid.UUID


class ChapterStorage(Protocol):
    """Хранилище глав, нужное файловому сервису."""

    async def ensure_exists_by_book_and_number(
        self,
        book_id: uuid.UUID,
        chapter_num: int,
    ) -> ChapterRecord:
        """Вернуть главу или выбросить ошибку отсутствия."""
        ...


class ChapterFileMeta(Protocol):
    """Метаданные файла главы."""

    id: uuid.UUID
    chapter_id: uuid.UUID
    file_name: str
    extension: str | None
    content_type: str | None
    size: int
    chunks_count: int


class ChapterFileStorage(Protocol):
    """Хранилище файлов главы."""

    async def create_file(
        self,
        chapter_id: uuid.UUID,
        *,
        file_name: str,
        content_type: str | None,
        chunks: AsyncIterable[bytes],
    ) -> ChapterFileMeta:
        """Создать файл главы."""
        ...

    async def list_files(
        self,
        chapter_id: uuid.UUID,
        *,
        name: str | None = None,
        extension: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[ChapterFileMeta]:
        """Получить список файлов главы."""
        ...

    async def get_file_meta(self, file_id: uuid.UUID) -> ChapterFileMeta | None:
        """Получить метаданные файла."""
        ...

    async def ensure_file_belongs_to_chapter(
        self,
        chapter_id: uuid.UUID,
        file_id: uuid.UUID,
    ) -> Any:
        """Проверить принадлежность файла главе."""
        ...

    async def delete_file(self, chapter_id: uuid.UUID, file_id: uuid.UUID) -> bool:
        """Удалить файл главы."""
        ...


class ChapterFileStreamer(Protocol):
    """Источник stream-данных файла главы."""

    async def iter_file_chunks(self, file_id: uuid.UUID) -> AsyncIterator[bytes]:
        """Вернуть chunks файла главы."""
        ...


class LogWriter(Protocol):
    """Хранилище логов действий."""

    async def log_from_dto(self, payload: LogCreate) -> Any:
        """Записать лог из DTO."""
        ...


class ChapterFileNotFoundInServiceError(Exception):
    """Глава или файл главы не найдены."""


def _is_not_found_error(exc: Exception) -> bool:
    """Маппинг по имени класса сохраняет сервис независимым от repository-классов."""
    return exc.__class__.__name__ in {
        "BookChapterNotFoundError",
        "BookChapterFileNotFoundError",
    }


class ChapterFileService:
    """Сервис сценариев работы с несколькими файлами главы."""

    def __init__(
        self,
        chapter_repo: ChapterStorage,
        file_repo: ChapterFileStorage,
        log_repo: LogWriter,
        session_manager: SessionManager,
        file_repo_factory: Callable[[Any], ChapterFileStreamer],
    ):
        self._chapter_repo = chapter_repo
        self._file_repo = file_repo
        self._log_repo = log_repo
        self._session_manager = session_manager
        self._file_repo_factory = file_repo_factory

    async def create_file(
        self,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
        chapter_num: int,
        file_name: str,
        content_type: str | None,
        chunks: AsyncIterable[bytes],
    ) -> ChapterFileMeta:
        """Создать файл главы и записать лог."""
        chapter = await self._get_chapter(book_id, chapter_num)
        meta = await self._file_repo.create_file(
            chapter.id,
            file_name=file_name,
            content_type=content_type,
            chunks=chunks,
        )

        await self._log_repo.log_from_dto(
            LogCreate(
                user_id=user_id,
                action="create_chapter_file",
                entity="book_chapter_files",
                entity_id=meta.id,
                details=(
                    f"Добавлен файл главы #{chapter_num} книги #{book_id}: "
                    f"{meta.file_name} (id={meta.id})"
                ),
            )
        )
        return meta

    async def list_files(
        self,
        book_id: uuid.UUID,
        chapter_num: int,
        *,
        name: str | None = None,
        extension: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[ChapterFileMeta]:
        """Получить файлы главы с фильтрами."""
        chapter = await self._get_chapter(book_id, chapter_num)
        return await self._file_repo.list_files(
            chapter.id,
            name=name,
            extension=extension,
            offset=offset,
            limit=limit,
        )

    async def get_file_meta(
        self,
        book_id: uuid.UUID,
        chapter_num: int,
        file_id: uuid.UUID,
    ) -> ChapterFileMeta:
        """Получить метаданные конкретного файла главы."""
        chapter = await self._get_chapter(book_id, chapter_num)
        try:
            await self._file_repo.ensure_file_belongs_to_chapter(chapter.id, file_id)
        except Exception as exc:
            if _is_not_found_error(exc):
                raise ChapterFileNotFoundInServiceError from exc
            raise

        meta = await self._file_repo.get_file_meta(file_id)
        if meta is None:
            raise ChapterFileNotFoundInServiceError
        return meta

    async def iter_file_chunks(self, file_id: uuid.UUID) -> AsyncIterator[bytes]:
        """Читать chunks файла главы в отдельной сессии на время stream."""
        async with self._session_manager.session() as session:
            file_repo = self._file_repo_factory(session)
            async for chunk in file_repo.iter_file_chunks(file_id):
                yield chunk

    async def delete_file(
        self,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
        chapter_num: int,
        file_id: uuid.UUID,
    ) -> None:
        """Удалить файл главы и записать лог."""
        chapter = await self._get_chapter(book_id, chapter_num)
        deleted = await self._file_repo.delete_file(chapter.id, file_id)
        if not deleted:
            raise ChapterFileNotFoundInServiceError

        await self._log_repo.log_from_dto(
            LogCreate(
                user_id=user_id,
                action="delete_chapter_file",
                entity="book_chapter_files",
                entity_id=file_id,
                details=f"Удален файл главы #{chapter_num} книги #{book_id} (id={file_id})",
            )
        )

    async def _get_chapter(self, book_id: uuid.UUID, chapter_num: int) -> ChapterRecord:
        """Получить главу и привести repository-ошибку к ошибке сервиса."""
        try:
            return await self._chapter_repo.ensure_exists_by_book_and_number(
                book_id,
                chapter_num,
            )
        except Exception as exc:
            if _is_not_found_error(exc):
                raise ChapterFileNotFoundInServiceError from exc
            raise
