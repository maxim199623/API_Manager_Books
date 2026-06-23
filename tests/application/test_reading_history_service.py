import uuid

import pytest

from src.DB.Repository.BookRepository.book_repository import BookNotFoundError
from src.application.services.reading_history_service import ReadingHistoryService


class FakeBookRepo:
    def __init__(self, *, exists: bool = True):
        self.exists = exists
        self.calls = []

    async def ensure_exists(self, book_id):
        self.calls.append(book_id)
        if not self.exists:
            raise BookNotFoundError


class FakeChapterRepo:
    def __init__(self):
        self.result = [1, 2]
        self.number_calls = []

    async def get_chapters_numbers_by_ids(self, chapter_ids):
        self.number_calls.append(chapter_ids)
        return self.result


class FakeLogRepo:
    def __init__(self):
        self.chapter_ids = []
        self.count = 0
        self.list_calls = []
        self.count_calls = []
        self.clear_calls = []

    async def list_read_chapter_ids_for_user(self, *, user_id, offset, limit):
        self.list_calls.append(
            {
                "scope": "all",
                "user_id": user_id,
                "offset": offset,
                "limit": limit,
            }
        )
        return self.chapter_ids

    async def list_read_chapter_ids_for_user_and_book(
        self,
        *,
        user_id,
        book_id,
        offset,
        limit,
    ):
        self.list_calls.append(
            {
                "scope": "book",
                "user_id": user_id,
                "book_id": book_id,
                "offset": offset,
                "limit": limit,
            }
        )
        return self.chapter_ids

    async def count_read_chapters_for_user_and_book(self, *, user_id, book_id):
        self.count_calls.append((user_id, book_id))
        return self.count

    async def clear_read_history_for_user_and_book(self, *, user_id, book_id):
        self.clear_calls.append((user_id, book_id))


@pytest.mark.asyncio
async def test_list_read_chapters_without_book_uses_user_lookup_and_skips_empty_chapter_lookup():
    user_id = uuid.uuid4()
    log_repo = FakeLogRepo()
    chapter_repo = FakeChapterRepo()
    service = ReadingHistoryService(FakeBookRepo(), chapter_repo, log_repo)

    result = await service.list_read_chapters(
        user_id=user_id,
        book_id=None,
        offset=0,
        limit=100,
    )

    assert result == []
    assert log_repo.list_calls == [
        {
            "scope": "all",
            "user_id": user_id,
            "offset": 0,
            "limit": 100,
        }
    ]
    assert chapter_repo.number_calls == []


@pytest.mark.asyncio
async def test_list_read_chapters_with_book_uses_book_lookup_and_returns_chapter_numbers():
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    chapter_ids = [uuid.uuid4(), uuid.uuid4()]
    log_repo = FakeLogRepo()
    log_repo.chapter_ids = chapter_ids
    chapter_repo = FakeChapterRepo()
    chapter_repo.result = [4, 9]
    service = ReadingHistoryService(FakeBookRepo(), chapter_repo, log_repo)

    result = await service.list_read_chapters(
        user_id=user_id,
        book_id=book_id,
        offset=5,
        limit=10,
    )

    assert result == [4, 9]
    assert log_repo.list_calls == [
        {
            "scope": "book",
            "user_id": user_id,
            "book_id": book_id,
            "offset": 5,
            "limit": 10,
        }
    ]
    assert chapter_repo.number_calls == [chapter_ids]


@pytest.mark.asyncio
async def test_count_read_chapters_checks_book_and_returns_count():
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    book_repo = FakeBookRepo()
    log_repo = FakeLogRepo()
    log_repo.count = 7
    service = ReadingHistoryService(book_repo, FakeChapterRepo(), log_repo)

    result = await service.count_read_chapters(user_id=user_id, book_id=book_id)

    assert result == 7
    assert book_repo.calls == [book_id]
    assert log_repo.count_calls == [(user_id, book_id)]


@pytest.mark.asyncio
async def test_count_read_chapters_propagates_book_not_found_without_count_lookup():
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    log_repo = FakeLogRepo()
    service = ReadingHistoryService(FakeBookRepo(exists=False), FakeChapterRepo(), log_repo)

    with pytest.raises(BookNotFoundError):
        await service.count_read_chapters(user_id=user_id, book_id=book_id)

    assert log_repo.count_calls == []


@pytest.mark.asyncio
async def test_clear_read_history_for_book_clears_by_user_and_book():
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    log_repo = FakeLogRepo()
    service = ReadingHistoryService(FakeBookRepo(), FakeChapterRepo(), log_repo)

    result = await service.clear_read_history_for_book(user_id=user_id, book_id=book_id)

    assert result is None
    assert log_repo.clear_calls == [(user_id, book_id)]
