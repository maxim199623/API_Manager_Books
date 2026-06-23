import uuid
from typing import Any, AsyncIterable, Literal, Protocol, Sequence

from src.schemas.books import (
    BookCreate,
    BookListRead,
    BookMetadataUpdate,
    BookUpdate,
)
from src.DB.Repository.BookRepository.book_repository import (
    BookNotFoundError as RepositoryBookNotFoundError,
    BookRepository,
)
from src.DB.Repository.FavoriteBookRepository.favorite_book_repository import FavoriteBookRepository
from src.schemas.logs import LogCreate
from src.DB.Repository.LogRepository.log_repository import LogRepository

BookSortField = Literal["created_at", "progress", "title"]
SortDirection = Literal["asc", "desc"]


class NotificationManager(Protocol):
    """Менеджер широковещательных уведомлений."""

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Отправить сообщение всем подключенным клиентам."""


class BookAlreadyExistsError(Exception):
    """Книга с таким названием и автором уже существует."""


class BookNotFoundInServiceError(Exception):
    """Книга не найдена в сценарии сервиса."""


class BookService:
    """Сервис сценариев CRUD и листинга книг без привязки к HTTP-слою."""

    def __init__(
        self,
        book_repo: BookRepository,
        favorite_book_repo: FavoriteBookRepository,
        log_repo: LogRepository,
        notification_manager: NotificationManager,
    ):
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
    ) -> list[BookListRead]:
        """Получить книги с признаком избранного для пользователя."""
        books: Sequence[object] = await self._book_repo.list_books(
            author=author,
            series=series,
            offset=offset,
            limit=limit,
            sort_by=sort_by,
            sort_dir=sort_dir,
            user_id=user_id,
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
        except RepositoryBookNotFoundError as exc:
            raise BookNotFoundInServiceError from exc

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
