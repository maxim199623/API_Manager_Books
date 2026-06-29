import uuid
from collections.abc import AsyncIterable, Sequence
from datetime import datetime
from typing import Any, Literal, Protocol

from api_manager_books.schemas.books import (
    BookCreate,
    BookListRead,
    BookMetadataUpdate,
    BookUpdate,
)
from api_manager_books.schemas.logs import LogCreate

BookSortField = Literal["created_at", "progress", "title"]
SortDirection = Literal["asc", "desc"]


class BookRecord(Protocol):
    """Книга для сервисных сценариев."""

    id: uuid.UUID
    title: str
    author: str | None


class BookStorage(Protocol):
    """Хранилище книг."""

    async def get_by_title_author(self, title: str, author: str | None) -> BookRecord | None:
        """Возвращает книгу по названию и автору."""
        ...

    async def create_book(
        self,
        data: BookCreate,
        *,
        cover_chunks: AsyncIterable[bytes] | None = None,
        file_chunks: AsyncIterable[bytes] | None = None,
    ) -> BookRecord:
        """Создает книгу с опциональными файлами."""
        ...

    async def list_books(
        self,
        *,
        author: str | None = None,
        series: str | None = None,
        offset: int = 0,
        limit: int = 100,
        sort_by: BookSortField = "created_at",
        sort_dir: SortDirection = "desc",
        user_id: uuid.UUID,
        cursor_created_at: datetime | None = None,
        cursor_id: uuid.UUID | None = None,
    ) -> Sequence[BookRecord]:
        """Возвращает список книг по фильтрам."""
        ...

    async def update_book(self, book_id: uuid.UUID, data: BookUpdate) -> BookRecord:
        """Обновляет книгу по идентификатору."""
        ...

    async def delete_book(self, book_id: uuid.UUID) -> bool:
        """Удаляет книгу по идентификатору."""
        ...


class FavoriteBookLookup(Protocol):
    """Хранилище признаков избранных книг."""

    async def list_favorite_book_ids(
        self,
        user_id: uuid.UUID,
        book_ids: list[uuid.UUID],
    ) -> set[uuid.UUID]:
        """Возвращает ID избранных книг пользователя."""
        ...


class LogWriter(Protocol):
    """Хранилище логов действий."""

    async def log_from_dto(self, payload: LogCreate) -> Any:
        """Записывает лог из DTO."""
        ...

    async def log_action(
        self,
        *,
        user_id: uuid.UUID | None,
        action: str,
        entity: str | None = None,
        entity_id: uuid.UUID | None = None,
        details: str | None = None,
        **extra_fields: Any,
    ) -> Any:
        """Записывает лог действия."""
        ...


class NotificationManager(Protocol):
    """Менеджер широковещательных уведомлений."""

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Отправить сообщение всем подключенным клиентам."""


class BookAlreadyExistsError(Exception):
    """Книга с таким названием и автором уже существует."""


class BookNotFoundInServiceError(Exception):
    """Книга не найдена в сценарии сервиса."""


def _is_book_not_found_error(exc: Exception) -> bool:
    """Проверяет ошибку отсутствующей книги."""
    return exc.__class__.__name__ == "BookNotFoundError"


class BookService:
    """Сервис сценариев CRUD и листинга книг без привязки к HTTP-слою."""

    def __init__(
        self,
        book_repo: BookStorage,
        favorite_book_repo: FavoriteBookLookup,
        log_repo: LogWriter,
        notification_manager: NotificationManager,
    ):
        """Инициализирует зависимости сервиса книг."""
        self._book_repo = book_repo
        self._favorite_book_repo = favorite_book_repo
        self._log_repo = log_repo
        self._notification_manager = notification_manager

    async def add_book(
        self,
        user_id: uuid.UUID,
        payload: BookCreate,
        *,
        cover_chunks: AsyncIterable[bytes] | None = None,
        file_chunks: AsyncIterable[bytes] | None = None,
    ) -> uuid.UUID:
        """Добавить книгу, залогировать операцию и отправить уведомление."""
        existing = await self._book_repo.get_by_title_author(payload.title, payload.author)
        if existing is not None:
            raise BookAlreadyExistsError

        book = await self._book_repo.create_book(
            payload,
            cover_chunks=cover_chunks,
            file_chunks=file_chunks,
        )

        await self._log_repo.log_from_dto(
            LogCreate(
                user_id=user_id,
                action="add_book",
                entity="books",
                entity_id=book.id,
                details=f"Добавлена книга '{book.title}' автора {book.author}",
            )
        )
        await self._notification_manager.broadcast(
            {"type": "new_book", "title": f"Добавлена книга '{book.title}'"}
        )

        return book.id

    async def list_books(
        self,
        *,
        user_id: uuid.UUID,
        author: str | None = None,
        series: str | None = None,
        offset: int = 0,
        limit: int = 100,
        sort_by: BookSortField = "created_at",
        sort_dir: SortDirection = "desc",
        cursor_created_at: datetime | None = None,
        cursor_id: uuid.UUID | None = None,
    ) -> list[BookListRead]:
        """Получить книги с признаком избранного для пользователя."""
        cursor_kwargs = {}
        if cursor_created_at is not None and cursor_id is not None:
            cursor_kwargs = {
                "cursor_created_at": cursor_created_at,
                "cursor_id": cursor_id,
            }
        books: Sequence[object] = await self._book_repo.list_books(
            author=author,
            series=series,
            offset=offset,
            limit=limit,
            sort_by=sort_by,
            sort_dir=sort_dir,
            user_id=user_id,
            **cursor_kwargs,
        )
        if not books:
            return []

        favorite_ids = await self._favorite_book_repo.list_favorite_book_ids(
            user_id,
            [book.id for book in books],
        )

        return [
            BookListRead.model_validate(book, from_attributes=True).model_copy(
                update={"is_favorite": book.id in favorite_ids}
            )
            for book in books
        ]

    async def update_metadata(
        self,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
        payload: BookMetadataUpdate,
    ) -> None:
        """Обновить метаданные книги и залогировать операцию."""
        try:
            book = await self._book_repo.update_book(
                book_id,
                BookUpdate(**payload.model_dump(exclude_unset=True)),
            )
        except Exception as exc:
            if _is_book_not_found_error(exc):
                raise BookNotFoundInServiceError from exc
            raise

        await self._log_repo.log_from_dto(
            LogCreate(
                user_id=user_id,
                action="update_book",
                entity="books",
                entity_id=book.id,
                details=f"Книга '{book.title}' (id={book.id}) была обновлена",
            )
        )

    async def delete_book(self, user_id: uuid.UUID, book_id: uuid.UUID) -> None:
        """Удалить книгу, залогировать операцию и отправить уведомление."""
        deleted = await self._book_repo.delete_book(book_id)
        if not deleted:
            raise BookNotFoundInServiceError

        await self._log_repo.log_action(
            user_id=user_id,
            action="delete_book",
            entity="books",
            entity_id=book_id,
            details=f"Книга с id={book_id} была удалена",
        )
        await self._notification_manager.broadcast({"type": "del_book"})
