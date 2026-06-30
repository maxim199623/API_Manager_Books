import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from api_manager_books.config.config import SettingsManager
from api_manager_books.db.base import Base
from api_manager_books.db.Manager.manager import AsyncDBManager
from api_manager_books.db.migrations import run_migrations
from api_manager_books.schemas.config import DatabaseSettings, PostgresSettings, SQLiteSettings


def _repository_backends() -> tuple[str, ...]:
    raw_value = os.getenv("API_MANAGER_BOOKS_REPOSITORY_BACKENDS")
    if raw_value is None:
        return ("sqlite", "postgres")

    backends = tuple(item.strip().lower() for item in raw_value.split(",") if item.strip())
    invalid_backends = sorted(set(backends) - {"sqlite", "postgres"})

    if invalid_backends:
        raise ValueError(
            "API_MANAGER_BOOKS_REPOSITORY_BACKENDS supports only sqlite, postgres; "
            f"got: {', '.join(invalid_backends)}"
        )

    if not backends:
        raise ValueError("API_MANAGER_BOOKS_REPOSITORY_BACKENDS must not be empty")

    return backends


REPOSITORY_BACKENDS = _repository_backends()
_UNAVAILABLE_REPOSITORY_BACKENDS: set[str] = set()


def _handle_unavailable_repository_backend(backend: str) -> None:
    if os.getenv("API_MANAGER_BOOKS_REPOSITORY_BACKENDS") is not None:
        raise RuntimeError(f"{backend} is not available")

    pytest.skip(f"{backend} is not available, skipping tests for this backend")


def _repository_postgres_settings() -> PostgresSettings:
    """Готовит настройки PostgreSQL для репозиториев."""
    return PostgresSettings(
        host="localhost",
        port=5432,
        user="postgres",
        password="1408",
        name="test_db",
    )


async def _managed_repository_db(
    settings: DatabaseSettings,
    backend: str,
) -> AsyncIterator[AsyncDBManager]:
    """Создает управляемую тестовую БД репозиториев."""
    if backend in _UNAVAILABLE_REPOSITORY_BACKENDS:
        _handle_unavailable_repository_backend(backend)

    db_manager = AsyncDBManager(settings, Base)

    ok = await db_manager.ping()
    if not ok:
        await db_manager.dispose()
        _UNAVAILABLE_REPOSITORY_BACKENDS.add(backend)
        _handle_unavailable_repository_backend(backend)

    await db_manager.drop_schema()
    await run_migrations(settings.get_url)

    try:
        yield db_manager
    finally:
        await db_manager.drop_schema()
        await db_manager.dispose()


@pytest.fixture
def repository_config_path(tmp_path: Path) -> Path:
    """Возвращает путь к конфигу репозиториев."""
    return tmp_path / "repository_config.ini"


@pytest.fixture
def repository_settings_manager(
    repository_config_path: Path,
    tmp_path: Path,
) -> SettingsManager:
    """Готовит менеджер настроек репозиториев."""
    manager = SettingsManager(repository_config_path, base_dir=tmp_path)

    manager.set_sqlite_path(str(tmp_path / "var" / "repository_tests.db"))
    manager.set_echo(False)
    manager.postgres.user = "postgres"
    manager.postgres.password = "1408"
    manager.postgres.name = "test_db"
    manager.save()

    return manager


@pytest_asyncio.fixture(params=REPOSITORY_BACKENDS, scope="function")
async def repository_async_db_manager(
    request: pytest.FixtureRequest,
    repository_settings_manager: SettingsManager,
) -> AsyncIterator[AsyncDBManager]:
    """Готовит асинхронный менеджер БД репозиториев."""
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
    tmp_path: Path,
) -> AsyncIterator[AsyncDBManager]:
    """Готовит асинхронный менеджер памяти репозиториев."""
    backend = request.param
    sqlite_file = tmp_path / "var" / "repository_memory_tests.db"
    sqlite_file.parent.mkdir(parents=True, exist_ok=True)
    sqlite_path = str(sqlite_file)
    settings = DatabaseSettings(
        backend=backend,
        echo=False,
        sqlite=SQLiteSettings(path=sqlite_path),
        postgres=_repository_postgres_settings(),
    )

    async for db_manager in _managed_repository_db(settings, backend):
        yield db_manager


@pytest_asyncio.fixture
async def repository_session(repository_async_db_manager: AsyncDBManager):
    """Выдает сессию репозитория PostgreSQL."""
    async with repository_async_db_manager.session() as session:
        yield session


@pytest_asyncio.fixture
async def repository_memory_session(
    repository_memory_async_db_manager: AsyncDBManager,
):
    """Выдает сессию репозитория в памяти."""
    async with repository_memory_async_db_manager.session() as session:
        yield session
