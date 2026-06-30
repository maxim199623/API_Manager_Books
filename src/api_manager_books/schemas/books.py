import uuid
from base64 import b64decode
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BookBase(BaseModel):
    """Базовые поля книги."""

    cover: bytes | None = None      # bytea
    title: str = Field(..., max_length=255)
    author: str | None = None
    description: str | None = None
    series: str | None = None
    genres: str | None = None
    format: str | None = None
    file: bytes | None = None       # bytea
    cover_mime: str | None = None
    cover_size: int = 0
    file_name: str | None = None
    file_mime: str | None = None
    file_size: int = 0

    # ---------- вход: base64 -> bytes ----------

    @field_validator("cover", "file", mode="before")
    @classmethod
    def decode_base64(cls, v):
        """Декодирует бинарные поля из base64."""
        if v is None:
            return None
        if isinstance(v, bytes):
            return v  # уже декодировано
        if isinstance(v, str):
            try:
                return b64decode(v)
            except Exception as e:
                raise ValueError("Invalid base64 data") from e
        raise TypeError("Expected base64 string or bytes")


class BookListRead(BaseModel):
    """Краткое представление книги."""

    id: uuid.UUID
    title: str
    author: str | None = None
    description: str | None = None
    series: str | None = None
    genres: str | None = None
    format: str | None = None
    created_at: datetime
    is_favorite: bool = False
    cover_mime: str | None = None
    cover_size: int = 0
    file_name: str | None = None
    file_mime: str | None = None
    file_size: int = 0

    model_config = ConfigDict(from_attributes=True)


class BookCreate(BookBase):
    """
    для создания книги.
    """


class BookUpdate(BaseModel):
    """
    для частичного обновления книги.
    Все поля опциональны.
    """
    cover: bytes | None = None
    title: str | None = None
    author: str | None = None
    description: str | None = None
    series: str | None = None
    genres: str | None = None
    format: str | None = None
    file: bytes | None = None
    cover_mime: str | None = None
    file_name: str | None = None
    file_mime: str | None = None

    model_config = ConfigDict(from_attributes=True)

    # ---------- вход: base64 -> bytes ----------

    @field_validator("cover", "file", mode="before")
    @classmethod
    def decode_base64(cls, v):
        """Декодирует бинарные поля из base64."""
        if v is None:
            return None
        if isinstance(v, bytes):
            return v  # уже декодировано
        if isinstance(v, str):
            try:
                return b64decode(v)
            except Exception as e:
                raise ValueError("Invalid base64 data") from e
        raise TypeError("Expected base64 string or bytes")


class BookMetadataUpdate(BaseModel):
    """
    Публичный PATCH-контракт только для текстовых метаданных книги.
    Бинарные поля обновляются отдельными multipart-endpoints.
    """
    title: str | None = None
    author: str | None = None
    description: str | None = None
    series: str | None = None
    genres: str | None = None
    format: str | None = None

    model_config = ConfigDict(extra="forbid")


