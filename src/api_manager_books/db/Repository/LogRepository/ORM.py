import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api_manager_books.db.base import Base


class LogEntry(Base):
    """ORM-модель записи лога."""

    __tablename__ = "db_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    # Пользователь, совершивший действие.
    user_id: Mapped[uuid.UUID| None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Краткое имя действия: "create", "update", "delete", "read", "login", ...
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # Имя сущности / таблицы: "users", "books", "book_chapters", ...
    entity: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    # Идентификатор записи в сущности (если применимо)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        nullable=True,
        index=True,
    )

    # Произвольное текстовое описание / детали
    details: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    # Связь с пользователем
    user = relationship("User", backref="logs")

    __table_args__ = (
        Index("ix_db_logs_user_action_entity_created_at", "user_id", "action", "entity", "created_at"),
        Index("ix_db_logs_user_action_entity_entity_id", "user_id", "action", "entity", "entity_id"),
    )

