import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr


class AuthRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChaptersCountResponse(BaseModel):
    book_id: uuid.UUID
    chapters_count: int


class SettingsResponse(BaseModel):
    backend: Literal["sqlite", "postgres"]
    echo: bool

    sqlite_path: str | None = None

    postgres_host: str | None = None
    postgres_port: int | None = None
    postgres_user: str | None = None
    postgres_name: str | None = None


class SettingsUpdate(BaseModel):
    """
    Частичное обновление настроек. Все поля опциональны.
    """
    backend: Literal["sqlite", "postgres"] | None = None
    echo: bool | None = None

    sqlite_path: str | None = None

    postgres_host: str | None = None
    postgres_port: int | None = None
    postgres_user: str | None = None
    postgres_password: str | None = None
    postgres_name: str | None = None
