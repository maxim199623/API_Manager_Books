import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, LargeBinary, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api_manager_books.db.base import Base

if TYPE_CHECKING:
    # только для проверки типов, чтобы не ловить циклический импорт
    from api_manager_books.db.Repository.BookChapterRepository.ORM import BookChapter


class BookChapterFile(Base):
    """ORM-модель файла главы книги."""

    __tablename__ = "book_chapter_files"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    chapter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("book_chapters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    extension: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    content_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    chunks_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    chapter: Mapped["BookChapter"] = relationship(
        "BookChapter",
        back_populates="files",
    )

    chunks: Mapped[list["BookChapterFileChunk"]] = relationship(
        "BookChapterFileChunk",
        back_populates="file",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="BookChapterFileChunk.chunk_index",
    )

    __table_args__ = (
        Index("ix_book_chapter_files_chapter_created_id", "chapter_id", "created_at", "id"),
    )


class BookChapterFileChunk(Base):
    """ORM-модель чанка файла главы книги."""

    __tablename__ = "book_chapter_file_chunks"

    file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("book_chapter_files.id", ondelete="CASCADE"),
        primary_key=True,
    )

    chunk_index: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    data: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
    )

    file: Mapped["BookChapterFile"] = relationship(
        "BookChapterFile",
        back_populates="chunks",
    )
