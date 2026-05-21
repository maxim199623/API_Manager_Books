import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Integer, Text, LargeBinary, DateTime, func, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.DB.base import Base

if TYPE_CHECKING:
    # только для проверки типов, чтобы не ловить циклический импорт
    from src.DB.Repository.BookChapterRepository.ORM import BookChapter

class Book(Base):
    __tablename__ = "books"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    # COVER: bytea
    cover: Mapped[bytes | None] = mapped_column(
        "cover",
        LargeBinary,
        nullable=True,
    )

    # TITLE: str
    title: Mapped[str] = mapped_column(
        "title",
        String(255),
        nullable=False,
        index=True,
    )

    # AUTHOR: str
    author: Mapped[str] = mapped_column(
        "author",
        String(255),
        nullable=True,
        index=True,
    )

    # DESCRIPTION: str
    description: Mapped[str | None] = mapped_column(
        "description",
        Text,
        nullable=True,
    )

    # SERIES: str
    series: Mapped[str | None] = mapped_column(
        "series",
        String(255),
        nullable=True,
        index=True,
    )

    # FORMAT: str
    format: Mapped[str | None] = mapped_column(
        "format",
        String(50),
        nullable=True,
    )

    # FILE: bytea
    file: Mapped[bytes | None] = mapped_column(
        "file",
        LargeBinary,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    chapters: Mapped[list["BookChapter"]] = relationship(
        "BookChapter",
        back_populates="book",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )