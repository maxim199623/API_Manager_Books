import importlib
import uuid
from datetime import datetime

import pytest
from fastapi import HTTPException

from api_manager_books.db.Repository.BookRepository.book_repository import BookNotFoundError
from api_manager_books.schemas.enums import UserRole
from api_manager_books.schemas.users import UserRead


class FakeReadingHistoryService:
    def __init__(self):
        self.chapters = []
        self.count = 0
        self.count_error = None
        self.list_calls = []
        self.count_calls = []
        self.clear_calls = []

    async def list_read_chapters(
        self,
        *,
        user_id,
        book_id,
        offset,
        limit,
    ):
        self.list_calls.append((user_id, book_id, offset, limit))
        return self.chapters

    async def count_read_chapters(self, *, user_id, book_id):
        self.count_calls.append((user_id, book_id))
        if self.count_error is not None:
            raise self.count_error
        return self.count

    async def clear_read_history_for_book(self, *, user_id, book_id):
        self.clear_calls.append((user_id, book_id))


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
        return importlib.import_module("api_manager_books.api.route.reading_history")
    except ModuleNotFoundError as exc:
        pytest.fail(f"Модуль reading_history не найден: {exc}")


def get_route(path: str, method: str):
    return next(
        (
            route
            for route in importlib.import_module("api_manager_books.api.route.reading_history").router.routes
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
async def test_get_read_chapters_returns_service_result(reading_history_route):
    current_user = make_user()
    service = FakeReadingHistoryService()
    service.chapters = [2, 5]

    result = await reading_history_route.get_read_chapters(
        book_id=None,
        offset=0,
        limit=100,
        current_user=current_user,
        reading_history_service=service,
    )

    assert result == [2, 5]
    assert service.list_calls == [(current_user.id, None, 0, 100)]


@pytest.mark.asyncio
async def test_get_read_chapters_passes_book_filter_to_service(reading_history_route):
    current_user = make_user()
    book_id = uuid.uuid4()
    service = FakeReadingHistoryService()

    result = await reading_history_route.get_read_chapters(
        book_id=book_id,
        offset=5,
        limit=10,
        current_user=current_user,
        reading_history_service=service,
    )

    assert result == []
    assert service.list_calls == [(current_user.id, book_id, 5, 10)]


@pytest.mark.asyncio
async def test_get_read_chapters_count_returns_service_count(reading_history_route):
    current_user = make_user()
    book_id = uuid.uuid4()
    service = FakeReadingHistoryService()
    service.count = 7

    result = await reading_history_route.get_read_chapters_count(
        book_id=book_id,
        current_user=current_user,
        reading_history_service=service,
    )

    assert result == {"book_id": book_id, "read_chapters": 7}
    assert service.count_calls == [(current_user.id, book_id)]


@pytest.mark.asyncio
async def test_get_read_chapters_count_returns_404_when_book_is_missing(reading_history_route):
    current_user = make_user()
    book_id = uuid.uuid4()
    service = FakeReadingHistoryService()
    service.count_error = BookNotFoundError

    with pytest.raises(HTTPException) as excinfo:
        await reading_history_route.get_read_chapters_count(
            book_id=book_id,
            current_user=current_user,
            reading_history_service=service,
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Book not found"
    assert service.count_calls == [(current_user.id, book_id)]


@pytest.mark.asyncio
async def test_clear_read_history_for_book_clears_by_user_and_book(reading_history_route):
    current_user = make_user()
    book_id = uuid.uuid4()
    service = FakeReadingHistoryService()

    result = await reading_history_route.clear_read_history_for_book(
        book_id=book_id,
        current_user=current_user,
        reading_history_service=service,
    )

    assert result is None
    assert service.clear_calls == [(current_user.id, book_id)]
