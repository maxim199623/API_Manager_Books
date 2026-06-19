from datetime import datetime
from types import SimpleNamespace
import uuid

import pytest

from src.DB.Repository.BookChapterRepository.book_chapter_repository import BookChapterNotFoundError
from src.DB.Repository.BookRepository.book_repository import BookNotFoundError
from src.application.services.chapter_service import ChapterService


class FakeBookRepo:
    def __init__(self, *, exists: bool = True):
        self.exists = exists
        self.calls: list[uuid.UUID] = []

    async def ensure_exists(self, book_id: uuid.UUID):
        self.calls.append(book_id)
        if not self.exists:
            raise BookNotFoundError
        return SimpleNamespace(id=book_id, title="Stored book")


class FakeChapterRepo:
    def __init__(
        self,
        *,
        headers=None,
        count: int = 0,
        chapter=None,
        chapter_exists: bool = True,
    ):
        self.headers = headers if headers is not None else []
        self.count = count
        self.chapter = chapter
        self.chapter_exists = chapter_exists
        self.header_calls: list[uuid.UUID] = []
        self.count_calls: list[uuid.UUID] = []
        self.chapter_calls: list[tuple[uuid.UUID, int]] = []

    async def list_chapter_headers(self, book_id: uuid.UUID):
        self.header_calls.append(book_id)
        return self.headers

    async def count_chapters(self, book_id: uuid.UUID) -> int:
        self.count_calls.append(book_id)
        return self.count

    async def ensure_exists_by_book_and_number(
        self,
        book_id: uuid.UUID,
        chapter_num: int,
    ):
        self.chapter_calls.append((book_id, chapter_num))
        if not self.chapter_exists:
            raise BookChapterNotFoundError
        return self.chapter


class FakeLogRepo:
    def __init__(self):
        self.entries = []

    async def log_from_dto(self, payload) -> None:
        self.entries.append(payload)


@pytest.mark.asyncio
async def test_list_chapter_headers_checks_book_and_returns_headers():
    book_id = uuid.uuid4()
    headers = [
        SimpleNamespace(chapter=1, chapter_name="Opening"),
        SimpleNamespace(chapter=2, chapter_name=None),
    ]
    book_repo = FakeBookRepo()
    chapter_repo = FakeChapterRepo(headers=headers)
    service = ChapterService(book_repo, chapter_repo, FakeLogRepo())

    result = await service.list_chapter_headers(book_id)

    assert result == headers
    assert book_repo.calls == [book_id]
    assert chapter_repo.header_calls == [book_id]


@pytest.mark.asyncio
async def test_list_chapter_headers_propagates_book_not_found_without_chapter_call():
    book_id = uuid.uuid4()
    chapter_repo = FakeChapterRepo(headers=[SimpleNamespace(chapter=1, chapter_name="Hidden")])
    service = ChapterService(FakeBookRepo(exists=False), chapter_repo, FakeLogRepo())

    with pytest.raises(BookNotFoundError):
        await service.list_chapter_headers(book_id)

    assert chapter_repo.header_calls == []


@pytest.mark.asyncio
async def test_count_chapters_checks_book_and_returns_book_id_with_count():
    book_id = uuid.uuid4()
    book_repo = FakeBookRepo()
    chapter_repo = FakeChapterRepo(count=7)
    service = ChapterService(book_repo, chapter_repo, FakeLogRepo())

    result = await service.count_chapters(book_id)

    assert result == (book_id, 7)
    assert book_repo.calls == [book_id]
    assert chapter_repo.count_calls == [book_id]


@pytest.mark.asyncio
async def test_get_chapter_returns_chapter_and_logs_reading():
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    chapter_num = 3
    chapter = SimpleNamespace(
        id=uuid.uuid4(),
        book_id=book_id,
        chapter=chapter_num,
        chapter_name="Finale",
        description="Text",
        file=None,
        created_at=datetime.now(),
    )
    chapter_repo = FakeChapterRepo(chapter=chapter)
    log_repo = FakeLogRepo()
    service = ChapterService(FakeBookRepo(), chapter_repo, log_repo)

    result = await service.get_chapter(user_id, book_id, chapter_num)

    assert result == chapter
    assert chapter_repo.chapter_calls == [(book_id, chapter_num)]
    assert len(log_repo.entries) == 1
    assert log_repo.entries[0].user_id == user_id
    assert log_repo.entries[0].action == "get_chapter"
    assert log_repo.entries[0].entity == "book_chapters"
    assert log_repo.entries[0].entity_id == chapter.id
    assert (
        log_repo.entries[0].details
        == f"Пользователь запросил главу #{chapter_num} книги {book_id}"
    )


@pytest.mark.asyncio
async def test_get_chapter_propagates_chapter_not_found_without_log():
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    chapter_repo = FakeChapterRepo(chapter_exists=False)
    log_repo = FakeLogRepo()
    service = ChapterService(FakeBookRepo(), chapter_repo, log_repo)

    with pytest.raises(BookChapterNotFoundError):
        await service.get_chapter(user_id, book_id, 5)

    assert chapter_repo.chapter_calls == [(book_id, 5)]
    assert log_repo.entries == []
