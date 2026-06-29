import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect as sa_inspect

from api_manager_books.db.Repository.LogRepository.ORM import LogEntry
from api_manager_books.db.Repository.utils import build_model_from_schema
from api_manager_books.schemas.logs import LogCreate


def _validate_uuid_or_none(value: uuid.UUID | None, field_name: str) -> None:
    """Проверить UUID или None."""
    if value is not None and not isinstance(value, uuid.UUID):
        raise TypeError(f"{field_name} должен быть UUID или None")


class LogRepository:
    """
    Репозиторий для работы с логами БД (db_logs).
    """

    def __init__(self, session: AsyncSession):
        """Инициализировать репозиторий логов."""
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
        count_stmt = (
            select(func.count())
            .select_from(LogEntry)
            .where(LogEntry.created_at < before)
        )
        count_res = await self._session.execute(count_stmt)
        deleted_count = count_res.scalar_one()

        if deleted_count == 0:
            return 0

        stmt = delete(LogEntry).where(LogEntry.created_at < before)
        await self._session.execute(stmt)
        return deleted_count

