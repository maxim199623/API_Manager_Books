import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from api_manager_books.db.Repository.ReadingProgressRepository.ORM import ReadingProgress


class ReadingProgressRepository:
    """Репозиторий прогресса чтения."""

    def __init__(self, session: AsyncSession):
        """Инициализировать репозиторий прогресса чтения."""
        self._session = session

    async def mark_chapter_read(
        self,
        *,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
        chapter_id: uuid.UUID,
        read_at: datetime | None = None,
    ) -> ReadingProgress:
        """Создать или обновить отметку чтения главы."""
        effective_read_at = read_at or datetime.now(UTC)
        dialect = self._session.bind.dialect.name if self._session.bind is not None else ""
        payload = {
            "user_id": user_id,
            "book_id": book_id,
            "chapter_id": chapter_id,
            "read_at": effective_read_at,
        }

        if dialect == "postgresql":
            stmt = pg_insert(ReadingProgress).values(**payload)
        else:
            stmt = sqlite_insert(ReadingProgress).values(**payload)

        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "chapter_id"],
            set_={
                "book_id": book_id,
                "read_at": effective_read_at,
            },
        )
        await self._session.execute(stmt)
        await self._session.flush()

        progress = await self._session.get(
            ReadingProgress,
            {"user_id": user_id, "chapter_id": chapter_id},
        )
        if progress is None:
            raise RuntimeError("reading_progress upsert failed")
        return progress

    async def list_read_chapter_ids_for_user(
        self,
        *,
        user_id: uuid.UUID,
        offset: int = 0,
        limit: int = 100,
        cursor_read_at: datetime | None = None,
        cursor_chapter_id: uuid.UUID | None = None,
    ) -> list[uuid.UUID]:
        """Вернуть прочитанные главы пользователя."""
        stmt = (
            select(ReadingProgress.chapter_id)
            .where(ReadingProgress.user_id == user_id)
        )
        stmt = self._apply_cursor(
            stmt,
            cursor_read_at=cursor_read_at,
            cursor_chapter_id=cursor_chapter_id,
        )
        stmt = (
            stmt.order_by(ReadingProgress.read_at.desc(), ReadingProgress.chapter_id.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_read_chapter_ids_for_user_and_book(
        self,
        *,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
        offset: int = 0,
        limit: int = 100,
        cursor_read_at: datetime | None = None,
        cursor_chapter_id: uuid.UUID | None = None,
    ) -> list[uuid.UUID]:
        """Вернуть прочитанные главы пользователя в книге."""
        stmt = (
            select(ReadingProgress.chapter_id)
            .where(
                ReadingProgress.user_id == user_id,
                ReadingProgress.book_id == book_id,
            )
        )
        stmt = self._apply_cursor(
            stmt,
            cursor_read_at=cursor_read_at,
            cursor_chapter_id=cursor_chapter_id,
        )
        stmt = (
            stmt.order_by(ReadingProgress.read_at.desc(), ReadingProgress.chapter_id.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_read_chapters_for_user_and_book(
        self,
        *,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
    ) -> int:
        """Посчитать прочитанные главы пользователя в книге."""
        stmt = select(func.count()).select_from(ReadingProgress).where(
            ReadingProgress.user_id == user_id,
            ReadingProgress.book_id == book_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def clear_read_history_for_user_and_book(
        self,
        *,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
    ) -> int:
        """Удалить прогресс чтения пользователя по книге."""
        count = await self.count_read_chapters_for_user_and_book(
            user_id=user_id,
            book_id=book_id,
        )
        if count == 0:
            return 0

        stmt = delete(ReadingProgress).where(
            ReadingProgress.user_id == user_id,
            ReadingProgress.book_id == book_id,
        )
        await self._session.execute(stmt)
        return count

    def _apply_cursor(
        self,
        stmt,
        *,
        cursor_read_at: datetime | None,
        cursor_chapter_id: uuid.UUID | None,
    ):
        """Применить keyset-курсор истории чтения."""
        if cursor_read_at is None or cursor_chapter_id is None:
            return stmt

        return stmt.where(
            or_(
                ReadingProgress.read_at < cursor_read_at,
                (ReadingProgress.read_at == cursor_read_at)
                & (ReadingProgress.chapter_id > cursor_chapter_id),
            )
        )
