import pytest

from api_manager_books.application.services.settings_service import SettingsMigrationError, SettingsService
from api_manager_books.config.config import AppSettings
from api_manager_books.schemas.api import SettingsUpdate
from api_manager_books.schemas.config import DatabaseSettings, PostgresSettings, SQLiteSettings


class FakeSettingsManager:
    """Тестовый менеджер настроек."""
    def __init__(self, settings: AppSettings):
        """Инициализирует тестовый объект."""
        self._settings = settings
        self.saved = 0
        self.applied_settings: list[AppSettings] = []

    @property
    def settings(self) -> AppSettings:
        """Возвращает текущие тестовые настройки."""
        return self._settings

    @property
    def db(self) -> DatabaseSettings:
        """Возвращает тестовые настройки базы данных."""
        return self._settings.database

    @property
    def sqlite(self) -> SQLiteSettings | None:
        """Возвращает тестовые настройки SQLite."""
        return self._settings.database.sqlite

    @property
    def postgres(self) -> PostgresSettings | None:
        """Возвращает тестовые настройки Postgres."""
        return self._settings.database.postgres

    def replace_settings(self, settings: AppSettings) -> None:
        """Подменяет тестовые настройки приложения."""
        self.applied_settings.append(settings)
        self._settings = settings

    def save(self) -> None:
        """Имитирует сохранение настроек."""
        self.saved += 1


class FakeDBManager:
    """Тестовый менеджер базы данных."""
    def __init__(self, backend: str, *, migrate_error: Exception | None = None):
        """Инициализирует тестовый объект."""
        self.backend = backend
        self.migrate_error = migrate_error
        self.migrated_to: list[FakeDBManager] = []
        self.disposed = False

    @property
    def database_url(self) -> str:
        """Возвращает тестовый URL базы данных."""
        return f"{self.backend}://test"

    async def migrate_to(self, new_manager: "FakeDBManager") -> None:
        """Имитирует миграцию в новый менеджер базы данных."""
        self.migrated_to.append(new_manager)
        if self.migrate_error is not None:
            raise self.migrate_error

    async def dispose(self) -> None:
        """Имитирует закрытие менеджера базы данных."""
        self.disposed = True


class FakeDBManagerFactory:
    """Тестовая фабрика менеджеров базы данных."""
    def __init__(self):
        """Инициализирует тестовый объект."""
        self.created: list[FakeDBManager] = []

    def __call__(self, db_settings: DatabaseSettings) -> FakeDBManager:
        """Создает тестовый менеджер базы данных."""
        manager = FakeDBManager(db_settings.backend)
        self.created.append(manager)
        return manager


class FakeSchemaMigrator:
    """Тестовый применитель миграций."""

    def __init__(self):
        """Инициализирует тестовый объект."""
        self.urls: list[str] = []

    async def __call__(self, database_url: str) -> None:
        """Запоминает URL миграции."""
        self.urls.append(database_url)


def make_settings(*, backend: str = "sqlite", echo: bool = False) -> AppSettings:
    """Создает тестовые настройки приложения."""
    return AppSettings(
        database=DatabaseSettings(
            backend=backend,
            echo=echo,
            sqlite=SQLiteSettings(path="var/library.db"),
            postgres=PostgresSettings(
                host="localhost",
                port=5432,
                user="postgres",
                password="secret",
                name="books",
            ),
        )
    )


def make_service(
    settings_manager: FakeSettingsManager,
    factory: FakeDBManagerFactory | None = None,
    migrator: FakeSchemaMigrator | None = None,
) -> SettingsService:
    """Создает сервис с тестовыми зависимостями."""
    return SettingsService(
        settings_manager=settings_manager,
        db_manager_factory=factory or FakeDBManagerFactory(),
        schema_migrator=migrator or FakeSchemaMigrator(),
    )


def test_get_current_settings_returns_current_fields_without_password():
    """Проверяет выдачу настроек без пароля Postgres."""
    settings_manager = FakeSettingsManager(make_settings())
    service = make_service(settings_manager)

    response = service.get_current_settings()

    assert response.backend == "sqlite"
    assert response.echo is False
    assert response.sqlite_path == "var/library.db"
    assert response.postgres_host == "localhost"
    assert response.postgres_port == 5432
    assert response.postgres_user == "postgres"
    assert response.postgres_name == "books"
    assert not hasattr(response, "postgres_password")


def test_get_current_settings_omits_sqlite_path_when_backend_is_postgres():
    """Проверяет скрытие пути SQLite для Postgres."""
    settings_manager = FakeSettingsManager(make_settings(backend="postgres"))
    service = make_service(settings_manager)

    response = service.get_current_settings()

    assert response.backend == "postgres"
    assert response.sqlite_path is None


@pytest.mark.asyncio
async def test_update_without_backend_change_applies_migrations_skips_data_migration_and_saves():
    """Проверяет обновление без миграции при том же backend."""
    settings_manager = FakeSettingsManager(make_settings())
    factory = FakeDBManagerFactory()
    migrator = FakeSchemaMigrator()
    service = make_service(settings_manager, factory, migrator)
    old_db_manager = FakeDBManager("sqlite")

    result = await service.update_settings(
        SettingsUpdate(echo=True, sqlite_path="var/updated.db"),
        old_db_manager,
    )

    assert len(factory.created) == 1
    new_db_manager = factory.created[0]
    assert migrator.urls == [new_db_manager.database_url]
    assert old_db_manager.migrated_to == []
    assert settings_manager.saved == 1
    assert settings_manager.db.backend == "sqlite"
    assert settings_manager.db.echo is True
    assert settings_manager.sqlite is not None
    assert settings_manager.sqlite.path == "var/updated.db"
    assert result.new_db_manager is new_db_manager
    assert result.response.backend == "sqlite"
    assert result.response.echo is True


@pytest.mark.asyncio
async def test_update_normalizes_sqlite_path_before_creating_db_manager():
    """Проверяет нормализацию SQLite пути до создания менеджера БД."""
    settings_manager = FakeSettingsManager(make_settings())
    factory = FakeDBManagerFactory()
    service = make_service(settings_manager, factory)
    old_db_manager = FakeDBManager("sqlite")

    await service.update_settings(
        SettingsUpdate(sqlite_path="var/../var/books.db"),
        old_db_manager,
    )

    assert settings_manager.sqlite is not None
    assert settings_manager.sqlite.path == "var/books.db"


@pytest.mark.asyncio
async def test_update_rejects_unsafe_sqlite_path_before_creating_db_manager():
    """Проверяет, что небезопасный путь не доходит до фабрики БД."""
    settings_manager = FakeSettingsManager(make_settings())
    factory = FakeDBManagerFactory()
    service = make_service(settings_manager, factory)
    old_db_manager = FakeDBManager("sqlite")

    with pytest.raises(ValueError, match="inside var"):
        await service.update_settings(
            SettingsUpdate(sqlite_path="../outside.db"),
            old_db_manager,
        )

    assert factory.created == []
    assert settings_manager.saved == 0
    assert settings_manager.sqlite is not None
    assert settings_manager.sqlite.path == "var/library.db"


@pytest.mark.asyncio
async def test_update_rejects_memory_sqlite_path_for_api_settings():
    """Проверяет запрет :memory: для API-обновлений настроек."""
    settings_manager = FakeSettingsManager(make_settings())
    factory = FakeDBManagerFactory()
    service = make_service(settings_manager, factory)
    old_db_manager = FakeDBManager("sqlite")

    with pytest.raises(ValueError, match="not allowed"):
        await service.update_settings(
            SettingsUpdate(sqlite_path=":memory:"),
            old_db_manager,
        )

    assert factory.created == []


@pytest.mark.asyncio
async def test_update_with_backend_change_migrates_old_manager_to_new_manager():
    """Проверяет миграцию при смене backend."""
    settings_manager = FakeSettingsManager(make_settings(backend="sqlite"))
    factory = FakeDBManagerFactory()
    migrator = FakeSchemaMigrator()
    service = make_service(settings_manager, factory, migrator)
    old_db_manager = FakeDBManager("sqlite")

    result = await service.update_settings(
        SettingsUpdate(backend="postgres"),
        old_db_manager,
    )

    new_db_manager = factory.created[0]
    assert migrator.urls == [new_db_manager.database_url]
    assert old_db_manager.migrated_to == [new_db_manager]
    assert settings_manager.saved == 1
    assert settings_manager.db.backend == "postgres"
    assert result.new_db_manager is new_db_manager
    assert result.response.backend == "postgres"


@pytest.mark.asyncio
async def test_update_disposes_new_manager_and_keeps_settings_atomic_when_migration_fails():
    """Проверяет атомарность настроек при ошибке миграции."""
    settings_manager = FakeSettingsManager(make_settings(backend="sqlite"))
    factory = FakeDBManagerFactory()
    service = make_service(settings_manager, factory)
    old_db_manager = FakeDBManager("sqlite", migrate_error=RuntimeError("boom"))

    with pytest.raises(SettingsMigrationError, match="boom"):
        await service.update_settings(
            SettingsUpdate(backend="postgres"),
            old_db_manager,
        )

    new_db_manager = factory.created[0]
    assert new_db_manager.disposed is True
    assert settings_manager.saved == 0
    assert settings_manager.applied_settings == []
    assert settings_manager.db.backend == "sqlite"
