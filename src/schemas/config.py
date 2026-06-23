from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SQLiteSettings(BaseModel):
    path: str = Field(..., description="Путь к SQLite файлу или ':memory:'")

    @property
    def get_url(self) -> str:
        if self.path == ":memory:":
            return "sqlite+aiosqlite:///:memory:"
        return f"sqlite+aiosqlite:///{self.path}"


class PostgresSettings(BaseModel):
    host: str
    port: int
    user: str
    password: str
    name: str

    @property
    def get_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


class DatabaseSettings(BaseModel):
    backend: Literal["sqlite", "postgres"]
    echo: bool = False

    sqlite: SQLiteSettings | None = None
    postgres: PostgresSettings | None = None

    @classmethod
    @field_validator("backend")
    def validate_backend(cls, v: str) -> str:
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
        return self.active.get_url
