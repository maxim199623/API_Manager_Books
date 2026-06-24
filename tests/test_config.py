from configparser import ConfigParser
from pathlib import Path

import pytest

from api_manager_books.config.config import SettingsManager


@pytest.fixture
def config_path(tmp_path) -> Path:
    """Путь к временному config.ini для каждого теста."""
    return tmp_path / "config.ini"


@pytest.fixture
def make_manager(config_path):
    """Фабрика для создания SettingsManager поверх одного и того же файла."""

    def _make():
        """Создает временный конфиг настроек."""
        return SettingsManager(config_path)

    return _make



class Test_load_settings:
    """Проверяет загрузку настроек."""
    def test_first_start(self,config_path,  make_manager):
        """Проверяет первый запуск настроек."""
        settings = make_manager().settings
        assert  settings.database.backend == "sqlite"
        assert  settings.database.echo is False
        assert  settings.database.sqlite.path == "app.db"
        # -----------
        assert  settings.database.postgres.host == "localhost"
        assert  settings.database.postgres.port == 5432
        assert  settings.database.postgres.user == "postgres"
        assert  settings.database.postgres.password == "postgres"
        assert  settings.database.postgres.name == "myapp"
        # --------
        assert  settings.database.get_url == "sqlite+aiosqlite:///app.db"

        # ---------- файл действительно создан ----------
        assert config_path.exists()
        assert config_path.is_file()
        assert config_path.read_text().strip() != ""

    def test_change_backend_and_persist(self, make_manager, config_path: Path):
        """
        Меняем backend с sqlite на postgres, сохраняем в файл,
        пересоздаём менеджер и проверяем, что значение сохранилось.
        """
        manager = make_manager()
        assert manager.db.backend == "sqlite"

        manager.set_backend("postgres")
        manager.save()

        # новый инстанс поверх того же файла
        manager2 = make_manager()
        assert manager2.db.backend == "postgres"

        # заодно проверим, что активная секция сменилась
        assert manager2.db.active == manager2.postgres

        # и что в ini реально записано postgres
        parser = ConfigParser()
        parser.read(config_path, encoding="utf-8")
        assert parser["database"]["backend"] == "postgres"

    def test_change_echo_and_persist(self, make_manager, config_path: Path):
        """
        Меняем флаг echo, сохраняем, проверяем, что значение сохранилось.
        """
        manager = make_manager()
        # по умолчанию в наших дефолтах echo = False
        assert manager.db.echo is False

        manager.set_echo(True)
        manager.save()

        manager2 = make_manager()
        assert manager2.db.echo is True

        parser = ConfigParser()
        parser.read(config_path, encoding="utf-8")
        assert parser["database"]["echo"].lower() == "true"

    def test_change_sqlite_path_and_persist(self, make_manager, config_path: Path):
        """
        Меняем путь к sqlite-файлу, сохраняем, пересоздаём менеджер,
        проверяем, что и модель, и ini-файл обновились.
        """
        manager = make_manager()

        # дефолтное значение
        assert manager.sqlite is not None
        old_path = manager.sqlite.path

        new_path = "./library.db"
        manager.set_sqlite_path(new_path)
        manager.save()

        manager2 = make_manager()
        assert manager2.sqlite is not None
        assert manager2.sqlite.path == new_path
        assert manager2.sqlite.path != old_path

        # одновременно проверим URL
        assert manager2.db.get_url == f"sqlite+aiosqlite:///{new_path}"

        parser = ConfigParser()
        parser.read(config_path, encoding="utf-8")
        assert parser["sqlite"]["path"] == new_path

    def test_change_postgres_settings_and_persist(self, make_manager, config_path: Path):
        """
        Обновляем настройки Postgres (частично),
        сохраняем и проверяем, что они корректно применились.
        """
        manager = make_manager()

        # дефолты
        assert manager.postgres is not None
        assert manager.postgres.host == "localhost"
        assert manager.postgres.port == 5432
        assert manager.postgres.user == "postgres"
        assert manager.postgres.password == "postgres"
        assert manager.postgres.name == "myapp"

        manager.set_postgres(
            host="db",
            port=5433,
            user="app",
            password="secret",
            name="library",
        )
        manager.save()

        manager2 = make_manager()
        assert manager2.postgres is not None
        pg2 = manager2.postgres

        assert pg2.host == "db"
        assert pg2.port == 5433
        assert pg2.user == "app"
        assert pg2.password == "secret"
        assert pg2.name == "library"

        # проверяем, что ini-файл совпадает
        parser = ConfigParser()
        parser.read(config_path, encoding="utf-8")
        assert parser["postgres"]["host"] == "db"
        assert parser["postgres"]["port"] == "5433"
        assert parser["postgres"]["user"] == "app"
        assert parser["postgres"]["password"] == "secret"
        assert parser["postgres"]["name"] == "library"

    def test_urls_change_after_backend_and_sqlite_path_update(self, make_manager):
        """
        Комплексная проверка: смена backend и sqlite-path
        действительно приводит к изменению строк подключения.
        """
        manager = make_manager()

        # стартуем с sqlite
        manager.set_backend("sqlite")
        manager.set_sqlite_path("./first.db")
        manager.save()

        m1 = make_manager()
        assert m1.db.backend == "sqlite"
        assert m1.db.get_url == "sqlite+aiosqlite:///./first.db"

        # переключаемся на postgres
        m1.set_backend("postgres")
        m1.set_postgres(
            host="db",
            port=5432,
            user="user",
            password="pwd",
            name="libdb",
        )
        m1.save()

        m2 = make_manager()
        assert m2.db.backend == "postgres"
        assert m2.db.get_url == "postgresql+asyncpg://user:pwd@db:5432/libdb"