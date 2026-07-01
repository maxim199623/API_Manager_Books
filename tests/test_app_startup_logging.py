import pytest

from api_manager_books.api import api

pytestmark = pytest.mark.asyncio


class FakeSettings:
    class DB:
        get_url = "sqlite+aiosqlite:///:memory:"

    db = DB()


class FakeDBManager:
    def __init__(self, *_args, **_kwargs):
        self.disposed = False

    async def dispose(self):
        self.disposed = True


async def test_lifespan_logs_startup_success(monkeypatch, caplog):
    async def fake_run_migrations(_database_url):
        return None

    async def fake_create_initial_admin(_db_manager):
        return None

    monkeypatch.setattr(api, "SettingsManager", lambda _path: FakeSettings())
    monkeypatch.setattr(api, "AsyncDBManager", FakeDBManager)
    monkeypatch.setattr(api, "run_migrations", fake_run_migrations)
    monkeypatch.setattr(api, "create_initial_admin", fake_create_initial_admin)

    with caplog.at_level("INFO"):
        async with api.lifespan(api.app):
            pass

    assert "Loading application settings" in caplog.text
    assert "Starting database migrations" in caplog.text
    assert "Database migrations completed" in caplog.text
    assert "Application startup completed" in caplog.text
    assert "Application shutdown completed" in caplog.text


async def test_lifespan_logs_migration_error(monkeypatch, caplog):
    async def fake_run_migrations(_database_url):
        raise RuntimeError("migration boom")

    monkeypatch.setattr(api, "SettingsManager", lambda _path: FakeSettings())
    monkeypatch.setattr(api, "AsyncDBManager", FakeDBManager)
    monkeypatch.setattr(api, "run_migrations", fake_run_migrations)

    with caplog.at_level("ERROR"):
        with pytest.raises(RuntimeError, match="migration boom"):
            async with api.lifespan(api.app):
                pass

    assert "Application startup failed" in caplog.text


async def test_lifespan_logs_initial_admin_error(monkeypatch, caplog):
    async def fake_run_migrations(_database_url):
        return None

    async def fake_create_initial_admin(_db_manager):
        raise RuntimeError("admin boom")

    monkeypatch.setattr(api, "SettingsManager", lambda _path: FakeSettings())
    monkeypatch.setattr(api, "AsyncDBManager", FakeDBManager)
    monkeypatch.setattr(api, "run_migrations", fake_run_migrations)
    monkeypatch.setattr(api, "create_initial_admin", fake_create_initial_admin)

    with caplog.at_level("ERROR"):
        with pytest.raises(RuntimeError, match="admin boom"):
            async with api.lifespan(api.app):
                pass

    assert "Application startup failed" in caplog.text
