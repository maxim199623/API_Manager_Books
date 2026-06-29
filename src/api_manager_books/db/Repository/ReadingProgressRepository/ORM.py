import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api_manager_books.db.base import Base

if TYPE_CHECKING:
    from api_manager_books.db.Repository.BookChapterRepository.ORM import BookChapter
    from api_manager_books.db.Repository.BookRepository.ORM import Book
    from api_manager_books.db.Repository.UserRepository.ORM import User


class ReadingProgress(Base):
    """ORM-модель прогресса чтения главы пользователем."""

    __tablename__ = "reading_progress"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
    )
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("book_chapters.id", ondelete="CASCADE"),
        primary_key=True,
    )
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped["User"] = relationship("User")
    book: Mapped["Book"] = relationship("Book")
    chapter: Mapped["BookChapter"] = relationship("BookChapter")

    __table_args__ = (
        UniqueConstraint("user_id", "chapter_id", name="uq_reading_progress_user_chapter"),
        Index("ix_reading_progress_user_book_read_at", "user_id", "book_id", "read_at"),
        Index("ix_reading_progress_user_book_chapter", "user_id", "book_id", "chapter_id"),
    )
