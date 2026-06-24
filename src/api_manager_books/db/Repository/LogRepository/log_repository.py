import uuid
from datetime import datetime
from typing import Sequence, Any

from sqlalchemy import select, delete, join, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect as sa_inspect

from api_manager_books.db.Repository import BookChapter
from api_manager_books.db.Repository.LogRepository.ORM import LogEntry
from api_manager_books.schemas.logs import LogCreate

from api_manager_books.db.Repository.utils import patch_model_from_schema, build_model_from_schema


def _validate_uuid_or_none(value: uuid.UUID | None, field_name: str) -> None:
    if value is not None and not isinstance(value, uuid.UUID):
        raise TypeError(f"{field_name} должен быть UUID или None")


class LogRepository:
    """
    Репозиторий для работы с логами БД (db_logs).
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def log_action(
        self,
        *,
        user_id: uuid.UUID | None,
        action: str,
        entity: str | None = None,
        entity_id: uuid.UUID | None = None,
        details: str | None = None,
        **extra_fields: Any,
    ) -> LogEntry:
        """
        Записать действие в лог.

        Репозиторий не завязан на конкретный набор полей:
        берём только те ключи, которые реально существуют в LogEntry.
        Дополнительные поля можно передавать через **extra_fields.

        Пример использования:
            await log_repo.log_action(
                user_id=user.id,
                action="create",
                entity="books",
                entity_id=book.id,
                details="Создана новая книга",
            )
        """
        _validate_uuid_or_none(user_id, "user_id")
        _validate_uuid_or_none(entity_id, "entity_id")

        payload: dict[str, Any] = {
            "user_id": user_id,
            "action": action,
            "entity": entity,
            "entity_id": entity_id,
            "details": details,
            **extra_fields,
        }

        mapper = sa_inspect(LogEntry)
        allowed_keys = {attr.key for attr in mapper.attrs}

        filtered = {k: v for k, v in payload.items() if k in allowed_keys}

        entry = LogEntry(**filtered)
        self._session.add(entry)
        await self._session.flush()
        await self._session.refresh(entry)
        return entry

    async def log_from_dto(self, data: LogCreate) -> LogEntry:
        """
        Записать действие в лог из Pydantic-схемы LogCreate.

        При добавлении/удалении полей в LogEntry / LogCreate
        этот метод переписывать не нужно — берётся пересечение
        полей схемы и ORM-модели.
        """
        entry = build_model_from_schema(LogEntry, data)
        self._session.add(entry)
        await self._session.flush()
        await self._session.refresh(entry)
        return entry

    async def get_by_id(self, log_id: uuid.UUID) -> LogEntry | None:
        """Получение лога по ID"""
        stmt = select(LogEntry).where(LogEntry.id == log_id)
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_logs(
        self,
        *,
        user_id: uuid.UUID | None = None,
        action: str | None = None,
        entity: str | None = None,
        entity_id: uuid.UUID | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[LogEntry]:
        """
        Получить список логов с фильтрами.
        """
        stmt = select(LogEntry)

        if user_id is not None:
            stmt = stmt.where(LogEntry.user_id == user_id)

        if action is not None:
            stmt = stmt.where(LogEntry.action == action)

        if entity is not None:
            stmt = stmt.where(LogEntry.entity == entity)

        if entity_id is not None:
            stmt = stmt.where(LogEntry.entity_id == entity_id)

        if created_after is not None:
            stmt = stmt.where(LogEntry.created_at >= created_after)

        if created_before is not None:
            stmt = stmt.where(LogEntry.created_at <= created_before)

        stmt = stmt.order_by(LogEntry.created_at.desc()).offset(offset).limit(limit)

        res = await self._session.execute(stmt)
        return res.scalars().all()

    async def delete_older_than(self, before: datetime) -> int:
        """
        Удалить все логи, старше указанного момента.
        Возвращает количество удалённых записей.
        """
        stmt = (
            delete(LogEntry)
            .where(LogEntry.created_at < before)
            .returning(LogEntry.id)
        )
        res = await self._session.execute(stmt)
        deleted_ids = res.scalars().all()
        return len(deleted_ids)

    async def list_read_chapter_ids_for_user(
        self,
        user_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[uuid.UUID]:
        """
        Список ID глав, которые пользователь запрашивал (прочитал)
        через действие `get_chapter` по entity='book_chapters'.

        Возвращает уникальные entity_id (id главы),
        в порядке от самых свежих к более старым.
        """
        logs: Sequence[LogEntry] = await self.list_logs(
            user_id=user_id,
            action="get_chapter",
            entity="book_chapters",
            offset=offset,
            limit=limit,
        )

        ids_in_order: list[uuid.UUID] = [
            log.entity_id
            for log in logs
            if log.entity_id is not None
        ]

        seen: set[uuid.UUID] = set()
        unique_ids: list[uuid.UUID] = []
        for cid in ids_in_order:
            if cid not in seen:
                seen.add(cid)
                unique_ids.append(cid)

        return unique_ids

    async def list_read_chapter_ids_for_user_and_book(
        self,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[uuid.UUID]:
        """
        ID прочитанных глав пользователя, но только для указанной книги.
        """
        stmt = (
            select(LogEntry.entity_id, LogEntry.created_at)
            .select_from(
                join(
                    LogEntry,
                    BookChapter,
                    LogEntry.entity_id == BookChapter.id,
                )
            )
            .where(
                LogEntry.user_id == user_id,
                LogEntry.action == "get_chapter",
                LogEntry.entity == "book_chapters",
                BookChapter.book_id == book_id,
            )
            .order_by(LogEntry.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        res = await self._session.execute(stmt)
        rows = res.all()

        ids_in_order = [row[0] for row in rows if row[0] is not None]

        seen: set[uuid.UUID] = set()
        uniq: list[uuid.UUID] = []
        for cid in ids_in_order:
            if cid not in seen:
                seen.add(cid)
                uniq.append(cid)

        return uniq

    async def count_read_chapters_for_user_and_book(
        self,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
    ) -> int:
        """
        Количество уникальных прочитанных глав книги.
        Основывается на логах get_chapter + JOIN book_chapters.
        """
        stmt = (
            select(func.count(func.distinct(LogEntry.entity_id)))
            .select_from(
                join(
                    LogEntry,
                    BookChapter,
                    LogEntry.entity_id == BookChapter.id,
                )
            )
            .where(
                LogEntry.user_id == user_id,
                LogEntry.action == "get_chapter",
                LogEntry.entity == "book_chapters",
                BookChapter.book_id == book_id,
            )
        )

        res = await self._session.execute(stmt)
        return res.scalar_one() or 0

    async def clear_read_history_for_user_and_book(
            self,
            user_id: uuid.UUID,
            book_id: uuid.UUID,
    ):
        """
            Удаляет историю чтения (логи get_chapter) пользователя
            для конкретной книги.
            """
        stmt = (
            delete(LogEntry).where(LogEntry.id.in_(select(LogEntry.id).select_from(
                join(
                            LogEntry,
                            BookChapter,
                            LogEntry.entity_id == BookChapter.id,
                        )
                    ).where(
                        LogEntry.user_id == user_id,
                        LogEntry.action == "get_chapter",
                        LogEntry.entity == "book_chapters",
                        BookChapter.book_id == book_id,
                    )
                )
            )
            .returning(LogEntry.id)
        )

        res = await self._session.execute(stmt)
        deleted_ids = res.scalars().all()
        deleted_count = len(deleted_ids)

        await self.log_action(
            user_id=user_id,
            action="clear_read_history",
            entity="books",
            entity_id=book_id,
            details=f"Пользователь #{user_id} очистил историю чтения книги #{book_id} (удалено {deleted_count} записей)",
        )
