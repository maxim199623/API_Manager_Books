import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api_manager_books.db.base import Base

if TYPE_CHECKING:
    # только для проверки типов, чтобы не ловить циклический импорт
    from api_manager_books.db.Repository.BookChapterRepository.ORM import BookChapter


class Book(Base):
    """ORM-модель книги."""

    __tablename__ = "books"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
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

    genres: Mapped[str | None] = mapped_column(
        "genres",
        Text,
        nullable=True,
    )

    # FORMAT: str
    format: Mapped[str | None] = mapped_column(
        "format",
        String(50),
        nullable=True,
    )

    cover_mime: Mapped[str | None] = mapped_column(
        "cover_mime",
        String(255),
        nullable=True,
    )

    cover_size: Mapped[int] = mapped_column(
        "cover_size",
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    file_name: Mapped[str | None] = mapped_column(
        "file_name",
        String(255),
        nullable=True,
    )

    file_mime: Mapped[str | None] = mapped_column(
        "file_mime",
        String(255),
        nullable=True,
    )

    file_size: Mapped[int] = mapped_column(
        "file_size",
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

    chapters: Mapped[list["BookChapter"]] = relationship(
        "BookChapter",
        back_populates="book",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    cover_chunks: Mapped[list["BookCoverChunk"]] = relationship(
        "BookCoverChunk",
        back_populates="book",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="BookCoverChunk.chunk_index",
    )

    file_chunks: Mapped[list["BookFileChunk"]] = relationship(
        "BookFileChunk",
        back_populates="book",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="BookFileChunk.chunk_index",
    )


class BookCoverChunk(Base):
    """ORM-модель чанка обложки книги."""

    __tablename__ = "book_cover_chunks"

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("books.id", ondelete="CASCADE"),
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

    book: Mapped["Book"] = relationship(
        "Book",
        back_populates="cover_chunks",
    )


class BookFileChunk(Base):
    """ORM-модель чанка файла книги."""

    __tablename__ = "book_file_chunks"

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("books.id", ondelete="CASCADE"),
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

    book: Mapped["Book"] = relationship(
        "Book",
        back_populates="file_chunks",
    )
