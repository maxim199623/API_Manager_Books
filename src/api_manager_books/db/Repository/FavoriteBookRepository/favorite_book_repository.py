import uuid

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api_manager_books.db.Repository.FavoriteBookRepository.ORM import FavoriteBook


class FavoriteBookRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_user_and_book(
        self,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
    ) -> FavoriteBook | None:
        stmt = select(FavoriteBook).where(
            FavoriteBook.user_id == user_id,
            FavoriteBook.book_id == book_id,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def add_favorite(self, user_id: uuid.UUID, book_id: uuid.UUID) -> bool:
        existing = await self.get_by_user_and_book(user_id, book_id)
        if existing is not None:
            return False

        favorite = FavoriteBook(user_id=user_id, book_id=book_id)

        try:
            async with self._session.begin_nested():
                self._session.add(favorite)
                await self._session.flush()
        except IntegrityError:
            existing = await self.get_by_user_and_book(user_id, book_id)
            if existing is not None:
                return False
            raise

        return True

    async def remove_favorite(self, user_id: uuid.UUID, book_id: uuid.UUID) -> bool:
        stmt = delete(FavoriteBook).where(
            FavoriteBook.user_id == user_id,
            FavoriteBook.book_id == book_id,
        ).returning(FavoriteBook.id)
        res = await self._session.execute(stmt)
        deleted_id = res.scalar_one_or_none()
        return deleted_id is not None

    async def is_favorite(self, user_id: uuid.UUID, book_id: uuid.UUID) -> bool:
        favorite = await self.get_by_user_and_book(user_id, book_id)
        return favorite is not None

    async def list_favorite_book_ids(
        self,
        user_id: uuid.UUID,
        book_ids: list[uuid.UUID],
    ) -> set[uuid.UUID]:
        if not book_ids:
            return set()

        stmt = select(FavoriteBook.book_id).where(
            FavoriteBook.user_id == user_id,
            FavoriteBook.book_id.in_(book_ids),
        )
        res = await self._session.execute(stmt)
        return set(res.scalars().all())
