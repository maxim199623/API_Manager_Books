import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


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


class LogRead(LogBase):
    """Представление записи лога."""

    id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
