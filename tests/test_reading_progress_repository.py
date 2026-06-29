import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from api_manager_books.db.Repository.BookChapterRepository.ORM import BookChapter
from api_manager_books.db.Repository.BookRepository.ORM import Book
from api_manager_books.db.Repository.LogRepository.log_repository import LogRepository
from api_manager_books.db.Repository.ReadingProgressRepository.ORM import ReadingProgress
from api_manager_books.db.Repository.ReadingProgressRepository.reading_progress_repository import (
    ReadingProgressRepository,
)
from api_manager_books.db.Repository.UserRepository.ORM import User
from api_manager_books.schemas.enums import UserRole

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def progress_context(repository_session):
    """Готовит пользователя, книгу и две главы."""
    user = User(
        email=f"{uuid.uuid4()}@example.com",
        password_hash=b"hash",
        role=UserRole.USER,
    )
    book = Book(title="Progress Book", author="Author")
    chapters = [
        BookChapter(book=book, chapter=1, description="One"),
        BookChapter(book=book, chapter=2, description="Two"),
    ]
    repository_session.add_all([user, book, *chapters])
    await repository_session.flush()
    return user, book, chapters


@pytest_asyncio.fixture
async def progress_repo(repository_session) -> ReadingProgressRepository:
    """Готовит репозиторий прогресса чтения."""
    return ReadingProgressRepository(repository_session)


async def test_mark_chapter_read_creates_and_updates_single_progress_row(
    repository_session,
    progress_repo: ReadingProgressRepository,
    progress_context,
):
    """Проверяет upsert прогресса одной главы."""
    user, book, chapters = progress_context
    first_read_at = datetime(2026, 1, 1, tzinfo=UTC)
    second_read_at = first_read_at + timedelta(hours=1)

    await progress_repo.mark_chapter_read(
        user_id=user.id,
        book_id=book.id,
        chapter_id=chapters[0].id,
        read_at=first_read_at,
    )
    await progress_repo.mark_chapter_read(
        user_id=user.id,
        book_id=book.id,
        chapter_id=chapters[0].id,
        read_at=second_read_at,
    )

    rows = (
        await repository_session.execute(select(ReadingProgress))
    ).scalars().all()

    assert len(rows) == 1
    assert rows[0].user_id == user.id
    assert rows[0].book_id == book.id
    assert rows[0].chapter_id == chapters[0].id
    assert rows[0].read_at.replace(tzinfo=UTC) == second_read_at


async def test_read_queries_use_progress_rows_not_logs(
    progress_repo: ReadingProgressRepository,
    progress_context,
    repository_session,
):
    """Проверяет, что бизнес-история не зависит от db_logs."""
    user, book, chapters = progress_context
    log_repo = LogRepository(repository_session)

    await log_repo.log_action(
        user_id=user.id,
        action="get_chapter",
        entity="book_chapters",
        entity_id=chapters[0].id,
        details="old audit log only",
    )
    await progress_repo.mark_chapter_read(
        user_id=user.id,
        book_id=book.id,
        chapter_id=chapters[1].id,
        read_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    assert await progress_repo.list_read_chapter_ids_for_user(
        user_id=user.id,
        offset=0,
        limit=10,
    ) == [chapters[1].id]
    assert await progress_repo.list_read_chapter_ids_for_user_and_book(
        user_id=user.id,
        book_id=book.id,
        offset=0,
        limit=10,
    ) == [chapters[1].id]
    assert await progress_repo.count_read_chapters_for_user_and_book(
        user_id=user.id,
        book_id=book.id,
    ) == 1


async def test_list_read_chapter_ids_supports_cursor(
    progress_repo: ReadingProgressRepository,
    progress_context,
):
    """Проверяет keyset-пагинацию истории чтения."""
    user, book, chapters = progress_context
    first_read_at = datetime(2026, 1, 1, tzinfo=UTC)
    second_read_at = datetime(2026, 1, 2, tzinfo=UTC)

    await progress_repo.mark_chapter_read(
        user_id=user.id,
        book_id=book.id,
        chapter_id=chapters[0].id,
        read_at=first_read_at,
    )
    await progress_repo.mark_chapter_read(
        user_id=user.id,
        book_id=book.id,
        chapter_id=chapters[1].id,
        read_at=second_read_at,
    )

    page = await progress_repo.list_read_chapter_ids_for_user_and_book(
        user_id=user.id,
        book_id=book.id,
        offset=0,
        limit=10,
        cursor_read_at=second_read_at,
        cursor_chapter_id=chapters[1].id,
    )

    assert page == [chapters[0].id]


async def test_clear_read_history_removes_progress_and_keeps_audit_logs(
    progress_repo: ReadingProgressRepository,
    progress_context,
    repository_session,
):
    """Проверяет очистку прогресса без удаления аудита."""
    user, book, chapters = progress_context
    log_repo = LogRepository(repository_session)

    await progress_repo.mark_chapter_read(
        user_id=user.id,
        book_id=book.id,
        chapter_id=chapters[0].id,
    )
    await log_repo.log_action(
        user_id=user.id,
        action="get_chapter",
        entity="book_chapters",
        entity_id=chapters[0].id,
        details="audit should stay",
    )

    deleted_count = await progress_repo.clear_read_history_for_user_and_book(
        user_id=user.id,
        book_id=book.id,
    )

    assert deleted_count == 1
    assert await progress_repo.count_read_chapters_for_user_and_book(
        user_id=user.id,
        book_id=book.id,
    ) == 0
    assert len(await log_repo.list_logs(action="get_chapter", entity="book_chapters")) == 1
