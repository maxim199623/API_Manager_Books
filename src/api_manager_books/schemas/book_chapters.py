import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BookChapterBase(BaseModel):
    """Базовые поля главы книги."""

    chapter: int
    chapter_name: str | None = None
    description: str
    file: bytes | None = None


class BookChapterCreate(BookChapterBase):
    """
    для создания главы книги.
    """
    pass


class BookChapterUpdate(BaseModel):
    """
    для частичного обновления главы.
    Пока меняем только текст.
    """
    chapter_name: str | None = None
    description: str | None = None
    file: bytes | None = None


class BookChapterListRead(BaseModel):
    """Краткое представление главы."""

    chapter: int
    chapter_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class BookChapterRead(BaseModel):
    """Полное представление главы книги."""

    id: uuid.UUID
    book_id: uuid.UUID
    chapter: int
    chapter_name: str | None = None
    description: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
