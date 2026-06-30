import uuid

from pydantic import BaseModel


class LogBase(BaseModel):
    """Базовые поля записи лога."""

    user_id: uuid.UUID | None = None
    action: str
    entity: str | None = None
    entity_id: uuid.UUID | None = None
    details: str | None = None


class LogCreate(LogBase):
    """для создания записи лога."""
    pass


