import uuid
from typing import Protocol

from src.schemas.logs import LogCreate


class BookLookup(Protocol):
    async def ensure_exists(self, book_id: uuid.UUID) -> None:
        ...


class FavoriteBooks(Protocol):
    async def add_favorite(self, user_id: uuid.UUID, book_id: uuid.UUID) -> bool:
        ...

    async def remove_favorite(self, user_id: uuid.UUID, book_id: uuid.UUID) -> bool:
        ...


class LogWriter(Protocol):
    async def log_from_dto(self, payload: LogCreate) -> None:
        ...


class FavoriteService:
    """Сервис сценариев добавления и удаления книг из избранного."""

    def __init__(
        self,
        book_repo: BookLookup,
        favorite_book_repo: FavoriteBooks,
        log_repo: LogWriter,
    ):
        self._book_repo = book_repo
        self._favorite_book_repo = favorite_book_repo
        self._log_repo = log_repo

    async def favorite_book(self, user_id: uuid.UUID, book_id: uuid.UUID) -> None:
        """Добавить книгу в избранное и залогировать реальное изменение."""
        await self._book_repo.ensure_exists(book_id)

        added = await self._favorite_book_repo.add_favorite(user_id, book_id)
        if added:
            await self._log_repo.log_from_dto(
                LogCreate(
                    user_id=user_id,
                    action="favorite_book",
                    entity="books",
                    entity_id=book_id,
                    details=f"Книга с id={book_id} добавлена в избранное",
                )
            )

    async def unfavorite_book(self, user_id: uuid.UUID, book_id: uuid.UUID) -> None:
        """Удалить книгу из избранного и залогировать реальное изменение."""
        await self._book_repo.ensure_exists(book_id)

        removed = await self._favorite_book_repo.remove_favorite(user_id, book_id)
        if removed:
            await self._log_repo.log_from_dto(
                LogCreate(
                    user_id=user_id,
                    action="unfavorite_book",
                    entity="books",
                    entity_id=book_id,
                    details=f"Книга с id={book_id} удалена из избранного",
                )
            )
