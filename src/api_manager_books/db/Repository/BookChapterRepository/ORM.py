import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api_manager_books.db.base import Base

if TYPE_CHECKING:
    # только для проверки типов, чтобы не ловить циклический импорт
    from api_manager_books.db.Repository.BookChapterFileRepository.ORM import BookChapterFile
    from api_manager_books.db.Repository.BookRepository.ORM import Book


class BookChapter(Base):
    """ORM-модель главы книги."""

    __tablename__ = "book_chapters"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    # связь с книгой
    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # номер главы (CHAPTER)
    chapter: Mapped[int] = mapped_column(
        "chapter",
        Integer,
        nullable=False,
    )
    # название главы (CHAPTER)
    chapter_name: Mapped[str|None] = mapped_column(
        "chapter_name",
        Text,
        nullable=True,
    )

    # содержимое главы (DESCRIPTION)
    description: Mapped[str] = mapped_column(
        "description",
        Text,
        nullable=False,
    )

    # бинарный файл (FILE)
    file: Mapped[bytes|None] = mapped_column(
        "file",
        LargeBinary,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # связь обратно к книге
    book: Mapped["Book"] = relationship(
        "Book",
        back_populates="chapters",
    )

    files: Mapped[list["BookChapterFile"]] = relationship(
        "BookChapterFile",
        back_populates="chapter",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # у одной книги не может быть двух глав с одинаковым номером
    __table_args__ = (
        UniqueConstraint("book_id", "chapter", name="uq_book_chapter_num"),
    )
