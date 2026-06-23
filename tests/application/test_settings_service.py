import pytest

from src.schemas.api import SettingsUpdate
from src.application.services.settings_service import SettingsMigrationError, SettingsService
from src.core.config import AppSettings
from src.schemas.config import DatabaseSettings, PostgresSettings, SQLiteSettings


class FakeSettingsManager:
    def __init__(self, settings: AppSettings):
        self._settings = settings
        self.saved = 0
        self.applied_settings: list[AppSettings] = []

    @property
    def settings(self) -> AppSettings:
        return self._settings

    @property
    def db(self) -> DatabaseSettings:
        return self._settings.database

    @property
    def sqlite(self) -> SQLiteSettings | None:
        return self._settings.database.sqlite

    @property
    def postgres(self) -> PostgresSettings | None:
        return self._settings.database.postgres

    def replace_settings(self, settings: AppSettings) -> None:
        self.applied_settings.append(settings)
        self._settings = settings

    def save(self) -> None:
        self.saved += 1


class FakeDBManager:
    def __init__(self, backend: str, *, migrate_error: Exception | None = None):
        self.backend = backend
        self.migrate_error = migrate_error
        self.schema_created = False
        self.migrated_to: list[FakeDBManager] = []
        self.disposed = False

    async def create_schema(self) -> None:
        self.schema_created = True

    async def migrate_to(self, new_manager: "FakeDBManager") -> None:
        self.migrated_to.append(new_manager)
        if self.migrate_error is not None:
            raise self.migrate_error

    async def dispose(self) -> None:
        self.disposed = True


class FakeDBManagerFactory:
    def __init__(self):
        self.created: list[FakeDBManager] = []

    def __call__(self, db_settings: DatabaseSettings) -> FakeDBManager:
        manager = FakeDBManager(db_settings.backend)
        self.created.append(manager)
        return manager


def make_settings(*, backend: str = "sqlite", echo: bool = False) -> AppSettings:
    return AppSettings(
        database=DatabaseSettings(
            backend=backend,
            echo=echo,
            sqlite=SQLiteSettings(path="library.db"),
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
) -> SettingsService:
    return SettingsService(
        settings_manager=settings_manager,
        db_manager_factory=factory or FakeDBManagerFactory(),
    )


def test_get_current_settings_returns_current_fields_without_password():
    settings_manager = FakeSettingsManager(make_settings())
    service = make_service(settings_manager)

    response = service.get_current_settings()

    assert response.backend == "sqlite"
    assert response.echo is False
    assert response.sqlite_path == "library.db"
    assert response.postgres_host == "localhost"
    assert response.postgres_port == 5432
    assert response.postgres_user == "postgres"
    assert response.postgres_name == "books"
    assert not hasattr(response, "postgres_password")


def test_get_current_settings_omits_sqlite_path_when_backend_is_postgres():
    settings_manager = FakeSettingsManager(make_settings(backend="postgres"))
    service = make_service(settings_manager)

    response = service.get_current_settings()

    assert response.backend == "postgres"
    assert response.sqlite_path is None


@pytest.mark.asyncio
async def test_update_without_backend_change_creates_schema_skips_migration_and_saves():
    settings_manager = FakeSettingsManager(make_settings())
    factory = FakeDBManagerFactory()
    service = make_service(settings_manager, factory)
    old_db_manager = FakeDBManager("sqlite")

    result = await service.update_settings(
        SettingsUpdate(echo=True, sqlite_path="updated.db"),
        old_db_manager,
    )

    assert len(factory.created) == 1
    new_db_manager = factory.created[0]
    assert new_db_manager.schema_created is True
    assert old_db_manager.migrated_to == []
    assert settings_manager.saved == 1
    assert settings_manager.db.backend == "sqlite"
    assert settings_manager.db.echo is True
    assert settings_manager.sqlite is not None
    assert settings_manager.sqlite.path == "updated.db"
    assert result.new_db_manager is new_db_manager
    assert result.response.backend == "sqlite"
    assert result.response.echo is True


@pytest.mark.asyncio
async def test_update_with_backend_change_migrates_old_manager_to_new_manager():
    settings_manager = FakeSettingsManager(make_settings(backend="sqlite"))
    factory = FakeDBManagerFactory()
    service = make_service(settings_manager, factory)
    old_db_manager = FakeDBManager("sqlite")

    result = await service.update_settings(
        SettingsUpdate(backend="postgres"),
        old_db_manager,
    )

    new_db_manager = factory.created[0]
    assert old_db_manager.migrated_to == [new_db_manager]
    assert settings_manager.saved == 1
    assert settings_manager.db.backend == "postgres"
    assert result.new_db_manager is new_db_manager
    assert result.response.backend == "postgres"


@pytest.mark.asyncio
async def test_update_disposes_new_manager_and_keeps_settings_atomic_when_migration_fails():
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
    assert new_db_manager.schema_created is True
    assert new_db_manager.disposed is True
    assert settings_manager.saved == 0
    assert settings_manager.applied_settings == []
    assert settings_manager.db.backend == "sqlite"
