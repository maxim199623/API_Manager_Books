import uuid

import pytest

from api_manager_books.application.services.reading_history_service import ReadingHistoryService
from api_manager_books.db.Repository.BookRepository.book_repository import BookNotFoundError


class FakeBookRepo:
    """Тестовый репозиторий книг."""
    def __init__(self, *, exists: bool = True):
        """Инициализирует тестовый объект."""
        self.exists = exists
        self.calls = []

    async def ensure_exists(self, book_id):
        """Имитирует проверку существования записи."""
        self.calls.append(book_id)
        if not self.exists:
            raise BookNotFoundError


class FakeChapterRepo:
    """Тестовый репозиторий глав."""
    def __init__(self):
        """Инициализирует тестовый объект."""
        self.result = [1, 2]
        self.number_calls = []

    async def get_chapters_numbers_by_ids(self, chapter_ids):
        """Имитирует получение номеров глав по идентификаторам."""
        self.number_calls.append(chapter_ids)
        return self.result


class FakeProgressRepo:
    """Тестовый репозиторий прогресса."""
    def __init__(self):
        """Инициализирует тестовый объект."""
        self.chapter_ids = []
        self.count = 0
        self.list_calls = []
        self.count_calls = []
        self.clear_calls = []

    async def list_read_chapter_ids_for_user(self, *, user_id, offset, limit):
        """Имитирует историю чтения пользователя."""
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
        """Имитирует историю чтения пользователя по книге."""
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
        """Имитирует подсчет прочитанных глав книги."""
        self.count_calls.append((user_id, book_id))
        return self.count

    async def clear_read_history_for_user_and_book(self, *, user_id, book_id):
        """Имитирует очистку истории чтения книги."""
        self.clear_calls.append((user_id, book_id))
        return self.count


class FakeLogRepo:
    """Тестовый репозиторий логов."""

    def __init__(self):
        """Инициализирует тестовый объект."""
        self.entries = []

    async def log_from_dto(self, payload):
        """Имитирует запись аудита."""
        self.entries.append(payload)


@pytest.mark.asyncio
async def test_list_read_chapters_without_book_uses_user_lookup_and_skips_empty_chapter_lookup():
    """Проверяет историю пользователя без лишнего поиска глав."""
    user_id = uuid.uuid4()
    progress_repo = FakeProgressRepo()
    chapter_repo = FakeChapterRepo()
    service = ReadingHistoryService(FakeBookRepo(), chapter_repo, progress_repo, FakeLogRepo())

    result = await service.list_read_chapters(
        user_id=user_id,
        book_id=None,
        offset=0,
        limit=100,
    )

    assert result == []
    assert progress_repo.list_calls == [
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
    """Проверяет историю книги с возвратом номеров глав."""
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    chapter_ids = [uuid.uuid4(), uuid.uuid4()]
    progress_repo = FakeProgressRepo()
    progress_repo.chapter_ids = chapter_ids
    chapter_repo = FakeChapterRepo()
    chapter_repo.result = [4, 9]
    service = ReadingHistoryService(FakeBookRepo(), chapter_repo, progress_repo, FakeLogRepo())

    result = await service.list_read_chapters(
        user_id=user_id,
        book_id=book_id,
        offset=5,
        limit=10,
    )

    assert result == [4, 9]
    assert progress_repo.list_calls == [
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
    """Проверяет подсчет прочитанных глав после проверки книги."""
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    book_repo = FakeBookRepo()
    progress_repo = FakeProgressRepo()
    progress_repo.count = 7
    service = ReadingHistoryService(book_repo, FakeChapterRepo(), progress_repo, FakeLogRepo())

    result = await service.count_read_chapters(user_id=user_id, book_id=book_id)

    assert result == 7
    assert book_repo.calls == [book_id]
    assert progress_repo.count_calls == [(user_id, book_id)]


@pytest.mark.asyncio
async def test_count_read_chapters_propagates_book_not_found_without_count_lookup():
    """Проверяет ошибку книги без подсчета истории."""
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    progress_repo = FakeProgressRepo()
    service = ReadingHistoryService(FakeBookRepo(exists=False), FakeChapterRepo(), progress_repo, FakeLogRepo())

    with pytest.raises(BookNotFoundError):
        await service.count_read_chapters(user_id=user_id, book_id=book_id)

    assert progress_repo.count_calls == []


@pytest.mark.asyncio
async def test_clear_read_history_for_book_clears_by_user_and_book():
    """Проверяет очистку истории чтения по пользователю и книге."""
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    progress_repo = FakeProgressRepo()
    progress_repo.count = 3
    log_repo = FakeLogRepo()
    service = ReadingHistoryService(FakeBookRepo(), FakeChapterRepo(), progress_repo, log_repo)

    result = await service.clear_read_history_for_book(user_id=user_id, book_id=book_id)

    assert result is None
    assert progress_repo.clear_calls == [(user_id, book_id)]
    assert len(log_repo.entries) == 1
    assert log_repo.entries[0].action == "clear_read_history"
    assert log_repo.entries[0].entity == "books"
    assert log_repo.entries[0].entity_id == book_id
