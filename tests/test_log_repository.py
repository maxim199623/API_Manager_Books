from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio

from src.core.config import SettingsManager
from src.DB.Manager.manager import AsyncDBManager
from src.DB.base import Base

from src.DB.Repository.LogRepository.Shems import LogCreate
from src.DB.Repository.LogRepository.log_repository import LogRepository


# ----------------------------------------------------------------------

pytestmark = pytest.mark.asyncio


# ---------- ФИКСТУРЫ ДЛЯ НАСТРОЕК И МЕНЕДЖЕРА БД ----------

@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    return tmp_path / "config_logs.ini"


@pytest.fixture
def settings_manager(config_path: Path, tmp_path: Path) -> SettingsManager:
    """
    SettingsManager:
    - создаёт config.ini, если его нет;
    - указывает отдельный sqlite-файл для тестов логов.
    """
    manager = SettingsManager(config_path)

    db_file = tmp_path / "test_logs_repo.db"
    manager.set_sqlite_path(str(db_file))
    manager.set_echo(False)
    manager.postgres.user = "admin"
    manager.postgres.password = "admin"
    manager.postgres.name = "test_db"
    manager.save()

    return manager


@pytest_asyncio.fixture(params=["sqlite", "postgres"], scope="function")
async def async_db_manager(
    request: pytest.FixtureRequest,
    settings_manager: SettingsManager,
) -> AsyncIterator[AsyncDBManager]:
    """
    AsyncDBManager и для sqlite, и для postgres.
    Если postgres недоступен, тесты для него будут пропущены.
    """
    backend = request.param

    settings_manager.set_backend(backend)
    settings_manager.save()

    db_manager = AsyncDBManager(settings_manager.db, Base)

    # Проверяем доступность БД
    ok = await db_manager.ping()
    if not ok:
        await db_manager.dispose()
        pytest.skip(f"{backend} is not available, skipping tests for this backend")

    # Создаём схему (db_logs и остальные таблицы)
    await db_manager.create_schema()

    try:
        yield db_manager
    finally:
        await db_manager.drop_schema()
        await db_manager.dispose()


@pytest_asyncio.fixture
async def session(async_db_manager: AsyncDBManager):
    async with async_db_manager.session() as s:
        yield s


@pytest_asyncio.fixture
async def log_repo(session) -> LogRepository:
    return LogRepository(session)


# ---------- ТЕСТЫ ДЛЯ LogRepository ----------

class TestLogRepository:

    async def test_log_action_and_get_by_id(self, log_repo: LogRepository):
        entry = await log_repo.log_action(
            user_id=None,
            action="create",
            entity="books",
            entity_id=42,
            details="Создана книга #42",
        )

        assert entry.id is not None
        assert entry.action == "create"
        assert entry.entity == "books"
        assert entry.entity_id == 42
        assert entry.details == "Создана книга #42"
        assert entry.created_at is not None

        fetched = await log_repo.get_by_id(entry.id)
        assert fetched is not None
        assert fetched.id == entry.id
        assert fetched.action == "create"

    async def test_log_from_dto(self, log_repo: LogRepository):
        data = LogCreate(
            user_id=None,
            action="update",
            entity="users",
            entity_id=7,
            details="Изменён пользователь #7",
        )

        entry = await log_repo.log_from_dto(data)
        assert entry.id is not None
        assert entry.action == "update"
        assert entry.entity == "users"
        assert entry.entity_id == 7
        assert entry.details == "Изменён пользователь #7"

    async def test_list_logs_with_filters(self, log_repo: LogRepository):
        # создаём несколько логов разных типов
        await log_repo.log_action(
            user_id=None,
            action="create",
            entity="books",
            entity_id=1,
            details="create book 1",
        )
        await log_repo.log_action(
            user_id=None,
            action="update",
            entity="books",
            entity_id=1,
            details="update book 1",
        )
        await log_repo.log_action(
            user_id=None,
            action="delete",
            entity="books",
            entity_id=2,
            details="delete book 2",
        )
        await log_repo.log_action(
            user_id=None,
            action="create",
            entity="users",
            entity_id=5,
            details="create user 5",
        )

        # все логи
        all_logs = await log_repo.list_logs()
        assert len(all_logs) == 4

        # фильтр по action=create
        creates = await log_repo.list_logs(action="create")
        assert {l.action for l in creates} == {"create"}
        assert len(creates) == 2

        # фильтр по entity=books
        books_logs = await log_repo.list_logs(entity="books")
        assert {l.entity for l in books_logs} == {"books"}
        assert len(books_logs) == 3

        # фильтр по entity_id
        book1_logs = await log_repo.list_logs(entity="books", entity_id=1)
        assert len(book1_logs) == 2
        assert {l.action for l in book1_logs} == {"create", "update"}

    async def test_list_logs_time_range(self, log_repo: LogRepository):
        # создаём логи
        e1 = await log_repo.log_action(
            user_id=None,
            action="create",
            entity="books",
            entity_id=10,
            details="log 1",
        )
        e2 = await log_repo.log_action(
            user_id=None,
            action="update",
            entity="books",
            entity_id=10,
            details="log 2",
        )

        # берём реальные created_at из БД
        all_logs = await log_repo.list_logs(entity="books", entity_id=10)
        assert len(all_logs) >= 2

        oldest = min(l.created_at for l in all_logs)
        newest = max(l.created_at for l in all_logs)

        # окно, которое точно включает эти логи
        from datetime import timedelta
        window_start = oldest - timedelta(seconds=1)
        window_end = newest + timedelta(seconds=1)

        logs_in_range = await log_repo.list_logs(
            created_after=window_start,
            created_before=window_end,
        )
        assert len(logs_in_range) >= 2

        # окно строго после всех логов — должно быть пусто
        after_all = newest + timedelta(seconds=10)
        logs_after = await log_repo.list_logs(created_after=after_all)
        assert len(logs_after) == 0

        # окно строго до всех логов — тоже пусто
        before_all = oldest - timedelta(seconds=10)
        logs_before = await log_repo.list_logs(created_before=before_all)
        assert len(logs_before) == 0

    async def test_delete_older_than(self, log_repo: LogRepository):
        # создаём несколько логов
        for i in range(3):
            await log_repo.log_action(
                user_id=None,
                action="create",
                entity="books",
                entity_id=i,
                details=f"log {i}",
            )

        all_logs = await log_repo.list_logs()
        assert len(all_logs) >= 3

        newest = max(l.created_at for l in all_logs)

        from datetime import timedelta
        # порог в будущем относительно всех текущих логов — должны удалиться все
        threshold = newest + timedelta(seconds=10)

        deleted_all = await log_repo.delete_older_than(threshold)
        assert deleted_all >= 3

        remaining = await log_repo.list_logs()
        assert len(remaining) == 0