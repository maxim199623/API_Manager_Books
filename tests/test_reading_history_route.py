from datetime import datetime
import importlib
from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException

from src.DB.Repository.BookRepository.book_repository import BookNotFoundError
from src.DB.Repository.UserRepository.Enums import UserRole
from src.DB.Repository.UserRepository.Shems import UserRead


class FakeLogRepo:
    def __init__(self):
        self.chapter_ids: list[uuid.UUID] = []
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


class FakeChapterRepo:
    def __init__(self):
        self.calls = []
        self.result = [1, 2]

    async def get_chapters_numbers_by_ids(self, chapter_ids):
        self.calls.append(chapter_ids)
        return self.result


class FakeBookRepo:
    def __init__(self, *, exists: bool = True):
        self.exists = exists
        self.calls = []

    async def ensure_exists(self, book_id):
        self.calls.append(book_id)
        if not self.exists:
            raise BookNotFoundError
        return SimpleNamespace(id=book_id)


def make_user() -> UserRead:
    return UserRead(
        id=uuid.uuid4(),
        email="reader@example.com",
        role=UserRole.USER,
        is_active=True,
        created_at=datetime.now(),
    )


@pytest.fixture
def reading_history_route():
    try:
        return importlib.import_module("src.api.route.reading_history")
    except ModuleNotFoundError as exc:
        pytest.fail(f"Модуль reading_history не найден: {exc}")


def get_route(path: str, method: str):
    return next(
        (
            route
            for route in importlib.import_module("src.api.route.reading_history").router.routes
            if route.path == path and method in route.methods
        ),
        None,
    )


def test_reading_history_routes_are_registered_on_split_router(reading_history_route):
    assert get_route("/books/chapters/read", "GET") is not None
    assert get_route("/books/{book_id}/chapters/read/count", "GET") is not None
    assert get_route("/books/{book_id}/history", "DELETE") is not None
    assert hasattr(reading_history_route, "clear_read_history_for_book")


@pytest.mark.asyncio
async def test_get_read_chapters_returns_empty_list_without_chapter_lookup(reading_history_route):
    current_user = make_user()
    log_repo = FakeLogRepo()
    chapter_repo = FakeChapterRepo()

    result = await reading_history_route.get_read_chapters(
        book_id=None,
        offset=0,
        limit=100,
        current_user=current_user,
        log_repo=log_repo,
        chapter_repo=chapter_repo,
    )

    assert result == []
    assert log_repo.list_calls == [
        {
            "scope": "all",
            "user_id": current_user.id,
            "offset": 0,
            "limit": 100,
        }
    ]
    assert chapter_repo.calls == []


@pytest.mark.asyncio
async def test_get_read_chapters_returns_numbers_for_book_history(reading_history_route):
    current_user = make_user()
    book_id = uuid.uuid4()
    chapter_ids = [uuid.uuid4(), uuid.uuid4()]
    log_repo = FakeLogRepo()
    log_repo.chapter_ids = chapter_ids
    chapter_repo = FakeChapterRepo()
    chapter_repo.result = [3, 8]

    result = await reading_history_route.get_read_chapters(
        book_id=book_id,
        offset=5,
        limit=10,
        current_user=current_user,
        log_repo=log_repo,
        chapter_repo=chapter_repo,
    )

    assert result == [3, 8]
    assert log_repo.list_calls == [
        {
            "scope": "book",
            "user_id": current_user.id,
            "book_id": book_id,
            "offset": 5,
            "limit": 10,
        }
    ]
    assert chapter_repo.calls == [chapter_ids]


@pytest.mark.asyncio
async def test_get_read_chapters_count_checks_book_and_returns_count(reading_history_route):
    current_user = make_user()
    book_id = uuid.uuid4()
    book_repo = FakeBookRepo()
    log_repo = FakeLogRepo()
    log_repo.count = 7

    result = await reading_history_route.get_read_chapters_count(
        book_id=book_id,
        current_user=current_user,
        log_repo=log_repo,
        book_repo=book_repo,
    )

    assert result == {"book_id": book_id, "read_chapters": 7}
    assert book_repo.calls == [book_id]
    assert log_repo.count_calls == [(current_user.id, book_id)]


@pytest.mark.asyncio
async def test_get_read_chapters_count_returns_404_when_book_is_missing(reading_history_route):
    current_user = make_user()
    book_id = uuid.uuid4()
    book_repo = FakeBookRepo(exists=False)
    log_repo = FakeLogRepo()

    with pytest.raises(HTTPException) as excinfo:
        await reading_history_route.get_read_chapters_count(
            book_id=book_id,
            current_user=current_user,
            log_repo=log_repo,
            book_repo=book_repo,
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Book not found"
    assert book_repo.calls == [book_id]
    assert log_repo.count_calls == []


@pytest.mark.asyncio
async def test_clear_read_history_for_book_clears_by_user_and_book(reading_history_route):
    current_user = make_user()
    book_id = uuid.uuid4()
    log_repo = FakeLogRepo()

    result = await reading_history_route.clear_read_history_for_book(
        book_id=book_id,
        current_user=current_user,
        log_repo=log_repo,
    )

    assert result is None
    assert log_repo.clear_calls == [(current_user.id, book_id)]
