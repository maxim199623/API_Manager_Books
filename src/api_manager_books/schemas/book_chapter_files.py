import uuid

from pydantic import BaseModel, ConfigDict


class BookChapterFileBase(BaseModel):
    """Базовые метаданные файла главы."""

    id: uuid.UUID
    chapter_id: uuid.UUID
    file_name: str
    extension: str | None = None
    content_type: str | None = None
    size: int
    chunks_count: int


class BookChapterFileListRead(BookChapterFileBase):
    """Представление файла главы в списке."""

    model_config = ConfigDict(from_attributes=True)


class BookChapterFileCreateResponse(BookChapterFileBase):
    """Ответ после загрузки файла главы."""

    model_config = ConfigDict(from_attributes=True)
