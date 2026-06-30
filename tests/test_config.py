from configparser import ConfigParser
from pathlib import Path

import pytest

from api_manager_books.config.config import SettingsManager, normalize_sqlite_path


@pytest.fixture
def config_path(tmp_path) -> Path:
    """Путь к временному config.ini для каждого теста."""
    return tmp_path / "config.ini"


@pytest.fixture
def make_manager(config_path):
    """Фабрика для создания SettingsManager поверх одного и того же файла."""

    def _make():
        """Создает временный конфиг настроек."""
        return SettingsManager(config_path, base_dir=config_path.parent)

    return _make



class Test_load_settings:
    """Проверяет загрузку настроек."""
    def test_first_start(self,config_path,  make_manager):
        """Проверяет первый запуск настроек."""
        settings = make_manager().settings
        assert  settings.database.backend == "sqlite"
        assert  settings.database.echo is False
        assert  settings.database.sqlite.path == "var/app.db"
        # -----------
        assert  settings.database.postgres.host == "localhost"
        assert  settings.database.postgres.port == 5432
        assert  settings.database.postgres.user == "postgres"
        assert  settings.database.postgres.password == "postgres"
        assert  settings.database.postgres.name == "myapp"
        # --------
        assert  settings.database.get_url == "sqlite+aiosqlite:///var/app.db"

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

        new_path = "var/library.db"
        manager.set_sqlite_path(new_path)
        manager.save()

        manager2 = make_manager()
        assert manager2.sqlite is not None
        assert manager2.sqlite.path == new_path
        assert manager2.sqlite.path != old_path

        # одновременно проверим URL
        assert manager2.db.get_url == "sqlite+aiosqlite:///var/library.db"

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
        manager.set_sqlite_path("var/first.db")
        manager.save()

        m1 = make_manager()
        assert m1.db.backend == "sqlite"
        assert m1.db.get_url == "sqlite+aiosqlite:///var/first.db"

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


def test_normalize_sqlite_path_accepts_path_inside_var(tmp_path):
    """Проверяет допустимый путь внутри runtime-каталога."""
    assert normalize_sqlite_path("var/app.db", base_dir=tmp_path) == "var/app.db"


def test_normalize_sqlite_path_normalizes_inside_var(tmp_path):
    """Проверяет стабильный относительный путь после нормализации."""
    assert normalize_sqlite_path("var/../var/books.db", base_dir=tmp_path) == "var/books.db"


def test_normalize_sqlite_path_rejects_parent_escape(tmp_path):
    """Проверяет запрет выхода из runtime-каталога."""
    with pytest.raises(ValueError, match="inside var"):
        normalize_sqlite_path("../outside.db", base_dir=tmp_path)


def test_normalize_sqlite_path_rejects_absolute_outside_var(tmp_path):
    """Проверяет запрет абсолютного пути вне runtime-каталога."""
    outside = tmp_path.parent / "outside.db"

    with pytest.raises(ValueError, match="inside var"):
        normalize_sqlite_path(str(outside), base_dir=tmp_path)


def test_normalize_sqlite_path_rejects_absolute_inside_var(tmp_path):
    """Проверяет запрет абсолютного пути даже внутри runtime-каталога."""
    inside = tmp_path / "var" / "inside.db"

    with pytest.raises(ValueError, match="inside var"):
        normalize_sqlite_path(str(inside), base_dir=tmp_path)


@pytest.mark.parametrize(
    "sqlite_path",
    [
        r"C:\app\var\books.db",
        "C:/app/var/books.db",
        r"\\server\share\books.db",
    ],
)
def test_normalize_sqlite_path_rejects_windows_anchored_paths(tmp_path, sqlite_path: str):
    """Проверяет запрет Windows drive и UNC путей."""
    with pytest.raises(ValueError, match="inside var"):
        normalize_sqlite_path(sqlite_path, base_dir=tmp_path)


def test_normalize_sqlite_path_rejects_escape_after_var_prefix(tmp_path):
    """Проверяет запрет выхода наверх после начального var."""
    with pytest.raises(ValueError, match="inside var"):
        normalize_sqlite_path("var/../../outside.db", base_dir=tmp_path)


def test_normalize_sqlite_path_accepts_windows_separators_inside_var(tmp_path):
    """Проверяет нормализацию Windows-разделителей в безопасном пути."""
    assert normalize_sqlite_path(r"var\books.db", base_dir=tmp_path) == "var/books.db"


def test_normalize_sqlite_path_rejects_empty_string(tmp_path):
    """Проверяет запрет пустого пути."""
    with pytest.raises(ValueError, match="must not be empty"):
        normalize_sqlite_path("  ", base_dir=tmp_path)


def test_normalize_sqlite_path_allows_memory_only_when_requested(tmp_path):
    """Проверяет, что :memory: доступен только для тестовых сценариев."""
    with pytest.raises(ValueError, match="not allowed"):
        normalize_sqlite_path(":memory:", base_dir=tmp_path)

    assert normalize_sqlite_path(":memory:", base_dir=tmp_path, allow_memory=True) == ":memory:"


def write_config(path: Path, sqlite_path: str) -> None:
    path.write_text(
        "\n".join(
            [
                "[database]",
                "backend = sqlite",
                "echo = false",
                "",
                "[sqlite]",
                f"path = {sqlite_path}",
                "",
                "[postgres]",
                "host = localhost",
                "port = 5432",
                "user = postgres",
                "password = postgres",
                "name = myapp",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_load_config_rejects_sqlite_path_outside_var(tmp_path):
    """Проверяет, что config.ini не может увести SQLite БД из var."""
    config_file = tmp_path / "config.ini"
    write_config(config_file, "app.db")

    with pytest.raises(ValueError, match="inside var"):
        SettingsManager(config_file, base_dir=tmp_path)


def test_load_config_normalizes_sqlite_path_and_creates_var(tmp_path):
    """Проверяет нормализацию SQLite пути и создание runtime-каталога."""
    config_file = tmp_path / "config.ini"
    write_config(config_file, "var/../var/books.db")

    manager = SettingsManager(config_file, base_dir=tmp_path)

    assert manager.sqlite is not None
    assert manager.sqlite.path == "var/books.db"
    assert (tmp_path / "var").is_dir()


def test_set_sqlite_path_normalizes_before_saving_in_memory(make_manager):
    """Проверяет, что программное обновление не хранит сырой путь."""
    manager = make_manager()

    manager.set_sqlite_path("var/../var/books.db")

    assert manager.sqlite is not None
    assert manager.sqlite.path == "var/books.db"


def test_first_start_creates_var_directory(config_path: Path, make_manager):
    """Проверяет создание runtime-каталога при первом запуске."""
    manager = make_manager()

    assert manager.sqlite is not None
    assert manager.sqlite.path == "var/app.db"
    assert (config_path.parent / "var").is_dir()
