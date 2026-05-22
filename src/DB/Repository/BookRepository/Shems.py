import uuid
from datetime import datetime

from fastapi import UploadFile, File
from pydantic import BaseModel, ConfigDict, Field , field_validator, field_serializer
from base64 import b64decode, b64encode


class BookBase(BaseModel):
    cover: bytes | None = None      # bytea
    title: str = Field(..., max_length=255)
    author: str | None = None
    description: str | None = None
    series: str | None = None
    genres: str | None = None
    format: str | None = None
    file: bytes | None = None       # bytea

    # ---------- вход: base64 → bytes ----------

    @field_validator("cover", "file", mode="before")
    @classmethod
    def decode_base64(cls, v):
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

    model_config = ConfigDict(from_attributes=True)

    # ---------- вход: base64 → bytes ----------

    @field_validator("cover", "file", mode="before")
    @classmethod
    def decode_base64(cls, v):
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


class BookRead(BookBase):
    id: uuid.UUID
    created_at: datetime
    is_favorite: bool = False

    model_config = ConfigDict(from_attributes=True)

    # ---------- выход: bytes → base64 ----------
    @field_serializer("cover", "file")
    def encode_base64(self, v: bytes | None):
        if v is None:
            return None
        return b64encode(v).decode("ascii")
