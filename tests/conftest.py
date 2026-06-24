import sys
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio

# Корень проекта: .../
ROOT_DIR = Path(__file__).resolve().parents[1]

# Добавляем корень проекта в sys.path, если его там ещё нет
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api_manager_books.config.config import SettingsManager
from api_manager_books.db.Manager.manager import AsyncDBManager
from api_manager_books.db.base import Base
from api_manager_books.schemas.config import DatabaseSettings, PostgresSettings, SQLiteSettings

REPOSITORY_BACKENDS = ("sqlite", "postgres")


def _repository_postgres_settings() -> PostgresSettings:
    return PostgresSettings(
        host="localhost",
        port=5432,
        user="admin",
        password="admin",
        name="test_db",
    )


async def _managed_repository_db(
    settings: DatabaseSettings,
    backend: str,
) -> AsyncIterator[AsyncDBManager]:
    db_manager = AsyncDBManager(settings, Base)

    ok = await db_manager.ping()
    if not ok:
        await db_manager.dispose()
        pytest.skip(f"{backend} is not available, skipping tests for this backend")

    await db_manager.create_schema()

    try:
        yield db_manager
    finally:
        await db_manager.drop_schema()
        await db_manager.dispose()


@pytest.fixture
def repository_config_path(tmp_path: Path) -> Path:
    return tmp_path / "repository_config.ini"


@pytest.fixture
def repository_settings_manager(
    repository_config_path: Path,
    tmp_path: Path,
) -> SettingsManager:
    manager = SettingsManager(repository_config_path)

    manager.set_sqlite_path(str(tmp_path / "repository_tests.db"))
    manager.set_echo(False)
    manager.postgres.user = "admin"
    manager.postgres.password = "admin"
    manager.postgres.name = "test_db"
    manager.save()

    return manager


@pytest_asyncio.fixture(params=REPOSITORY_BACKENDS, scope="function")
async def repository_async_db_manager(
    request: pytest.FixtureRequest,
    repository_settings_manager: SettingsManager,
) -> AsyncIterator[AsyncDBManager]:
    backend = request.param

    repository_settings_manager.set_backend(backend)
    repository_settings_manager.save()

    async for db_manager in _managed_repository_db(
        repository_settings_manager.db,
        backend,
    ):
        yield db_manager


@pytest_asyncio.fixture(params=REPOSITORY_BACKENDS, scope="function")
async def repository_memory_async_db_manager(
    request: pytest.FixtureRequest,
) -> AsyncIterator[AsyncDBManager]:
    backend = request.param
    settings = DatabaseSettings(
        backend=backend,
        echo=False,
        sqlite=SQLiteSettings(path=":memory:"),
        postgres=_repository_postgres_settings(),
    )

    async for db_manager in _managed_repository_db(settings, backend):
        yield db_manager


@pytest_asyncio.fixture
async def repository_session(repository_async_db_manager: AsyncDBManager):
    async with repository_async_db_manager.session() as session:
        yield session


@pytest_asyncio.fixture
async def repository_memory_session(
    repository_memory_async_db_manager: AsyncDBManager,
):
    async with repository_memory_async_db_manager.session() as session:
        yield session
