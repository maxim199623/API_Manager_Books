from configparser import ConfigParser
from pathlib import Path

from pydantic import BaseModel

from api_manager_books.schemas.config import DatabaseSettings, PostgresSettings, SQLiteSettings

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def normalize_sqlite_path(
    path: str,
    *,
    base_dir: Path = PROJECT_ROOT,
    allow_memory: bool = False,
) -> str:
    """Нормализует SQLite путь и запрещает выход из runtime-каталога."""
    raw_path = path.strip()
    if not raw_path:
        raise ValueError("sqlite path must not be empty")

    if raw_path == ":memory:":
        if allow_memory:
            return raw_path
        raise ValueError(":memory: sqlite path is not allowed here")

    base = base_dir.resolve()
    var_dir = (base / "var").resolve()
    candidate = Path(raw_path)
    resolved = candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()

    if not resolved.is_relative_to(var_dir):
        raise ValueError("sqlite path must stay inside var directory")

    return resolved.relative_to(base).as_posix()


class AppSettings(BaseModel):
    """Описывает настройки приложения."""

    database: DatabaseSettings

class SettingsManager:
    """Менеджер настроек"""

    def __init__(self, path: str | Path = "config.ini"):
        """Загружает настройки из файла."""
        self.path = Path(path)
        self._parser = ConfigParser()

        if self.path.exists():
            # читаем существующий файл
            self._parser.read(self.path, encoding="utf-8")
            self._settings = self._load_from_parser()
        else:
            # создаём дефолтные настройки и сразу пишем файл
            self._settings = self._create_default_settings()
            self._write_parser_from_settings()
            self._save_to_disk()

        self._parser.read(self.path, encoding="utf-8")
        self._settings = self._load_from_parser()

    # ---------- внутреннее чтение из ConfigParser ----------

    def _load_from_parser(self) -> AppSettings:
        """Читает настройки из ConfigParser."""
        if "database" not in self._parser:
            raise KeyError("Section [database] is required in config.ini")

        db_section = self._parser["database"]
        backend = db_section.get("backend", "sqlite").strip().lower()
        echo = db_section.getboolean("echo", fallback=False)

        sqlite_settings = None
        if "sqlite" in self._parser:
            sqlite_section = self._parser["sqlite"]
            sqlite_settings = SQLiteSettings(path=sqlite_section.get("path", "var/app.db"))

        postgres_settings = None
        if "postgres" in self._parser:
            pg = self._parser["postgres"]
            postgres_settings = PostgresSettings(
                host=pg.get("host", "localhost"),
                port=pg.getint("port", fallback=5432),
                user=pg.get("user", "postgres"),
                password=pg.get("password", "postgres"),
                name=pg.get("name", "postgres"),
            )

        db_settings = DatabaseSettings(
            backend=backend, echo=echo,
            sqlite=sqlite_settings,
            postgres=postgres_settings,
        )

        return AppSettings(database=db_settings)

    # ---------- публичный доступ к настройкам ----------

    @property
    def settings(self) -> AppSettings:
        """Актуальные настройки (Pydantic-модель)."""
        return self._settings

    @property
    def db(self) -> DatabaseSettings:
        """Возвращает настройки базы данных."""
        return self._settings.database

    @property
    def sqlite(self) -> SQLiteSettings | None:
        """Возвращает настройки SQLite."""
        return self._settings.database.sqlite

    @property
    def postgres(self) -> PostgresSettings | None:
        """Возвращает настройки PostgreSQL."""
        return self._settings.database.postgres

    # ---------- методы изменения настроек ----------

    def set_backend(self, backend: str) -> None:
        """Меняет активный backend базы данных."""
        backend = backend.lower().strip()
        if backend not in ("sqlite", "postgres"):
            raise ValueError("backend must be 'sqlite' or 'postgres'")
        self._settings.database.backend = backend

    def set_echo(self, echo: bool) -> None:
        """Включить/выключить логирование SQL."""
        self._settings.database.echo = echo

    def set_sqlite_path(self, path: str) -> None:
        """Изменить путь к SQLite базе."""
        if self._settings.database.sqlite is None:
            self._settings.database.sqlite = SQLiteSettings(path=path)
        else:
            self._settings.database.sqlite.path = path

    def set_postgres(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        name: str | None = None,
    ) -> None:
        """Частично/полностью обновить настройки PostgreSQL."""
        db = self._settings.database
        if db.postgres is None:
            # создаём с дефолтами + переданными значениями
            db.postgres = PostgresSettings(
                host=host or "localhost",
                port=port or 5432,
                user=user or "postgres",
                password=password or "postgres",
                name=name or "postgres",
            )
            return

        pg = db.postgres
        if host is not None:
            pg.host = host
        if port is not None:
            pg.port = port
        if user is not None:
            pg.user = user
        if password is not None:
            pg.password = password
        if name is not None:
            pg.name = name

    def replace_settings(self, settings: AppSettings) -> None:
        """Атомарно заменить in-memory модель настроек."""
        self._settings = settings

    # ---------- сохранение обратно в ini ----------

    def save(self) -> None:
        """
        Сохраняет текущие Pydantic-настройки обратно в config.ini.
        Перезаписывает секции [database], [sqlite], [postgres].
        """

        # [database]
        if "database" not in self._parser:
            self._parser["database"] = {}
        db_section = self._parser["database"]
        db_section["backend"] = self.db.backend
        db_section["echo"] = "true" if self.db.echo else "false"

        # [sqlite]
        if self.sqlite is not None:
            self._parser["sqlite"] = {"path": self.sqlite.path}

        # [postgres]
        if self.postgres is not None:
            pg = self.postgres
            self._parser["postgres"] = {
                "host": pg.host,
                "port": str(pg.port),
                "user": pg.user,
                "password": pg.password,
                "name": pg.name,
            }

        with self.path.open("w", encoding="utf-8") as f:
            self._parser.write(f)

    def _create_default_settings(self) -> AppSettings:
        """
        Стандартные настройки, если файла нет.
        По умолчанию: sqlite var/app.db, echo = false, postgres с дефолтами.
        """
        sqlite_defaults = SQLiteSettings(path="var/app.db")
        postgres_defaults = PostgresSettings(
            host="localhost",
            port=5432,
            user="postgres",
            password="postgres",
            name="myapp",
        )

        db_settings = DatabaseSettings(
            backend="sqlite",   # активен sqlite
            echo=False,          # логирование SQL включено
            sqlite=sqlite_defaults,
            postgres=postgres_defaults,
        )

        return AppSettings(database=db_settings)

    def _write_parser_from_settings(self) -> None:
        """
        Пересобрать self._parser из текущих Pydantic-настроек.
        Полностью обновляет секции [database], [sqlite], [postgres].
        """
        self._parser = ConfigParser()

        # [database]
        self._parser["database"] = {
            "backend": self.db.backend,
            "echo": "true" if self.db.echo else "false",
        }

        # [sqlite]
        if self.sqlite is not None:
            self._parser["sqlite"] = {
                "path": self.sqlite.path,
            }

        # [postgres]
        if self.postgres is not None:
            pg = self.postgres
            self._parser["postgres"] = {
                "host": pg.host,
                "port": str(pg.port),
                "user": pg.user,
                "password": pg.password,
                "name": pg.name,
            }

    def _save_to_disk(self) -> None:
        """Записывает настройки на диск."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            self._parser.write(f)
