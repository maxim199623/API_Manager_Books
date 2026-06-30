from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SQLiteSettings(BaseModel):
    """Настройки подключения к SQLite."""

    path: str = Field(..., description="Путь к SQLite файлу или ':memory:'")

    @property
    def get_url(self) -> str:
        """Возвращает URL подключения SQLite."""
        if self.path == ":memory:":
            return "sqlite+aiosqlite:///:memory:"
        return f"sqlite+aiosqlite:///{self.path}"


class PostgresSettings(BaseModel):
    """Настройки подключения к PostgreSQL."""

    host: str
    port: int
    user: str
    password: str
    name: str

    @property
    def get_url(self) -> str:
        """Возвращает URL подключения PostgreSQL."""
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


class DatabaseSettings(BaseModel):
    """Настройки активной базы данных."""

    backend: Literal["sqlite", "postgres"]
    echo: bool = False

    sqlite: SQLiteSettings | None = None
    postgres: PostgresSettings | None = None

    @classmethod
    @field_validator("backend")
    def validate_backend(_cls, v: str) -> str:
        """Проверяет имя backend базы данных."""
        v = v.lower().strip()
        if v not in {"sqlite", "postgres"}:
            raise ValueError("backend must be 'sqlite' or 'postgres'")
        return v

    @property
    def active(self):
        """Возвращает активную секцию (sqlite или postgres)."""
        return self.sqlite if self.backend == "sqlite" else self.postgres

    @property
    def get_url(self) -> str:
        """Возвращает URL активной базы данных."""
        return self.active.get_url
