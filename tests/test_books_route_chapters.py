from datetime import datetime
from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from src.DB.Repository.BookChapterRepository.Shems import BookChapterCreate, BookChapterUpdate
from src.DB.Repository.BookChapterRepository.book_chapter_repository import BookChapterNotFoundError
from src.DB.Repository.BookRepository.book_repository import BookNotFoundError
from src.DB.Repository.UserRepository.Enums import UserRole
from src.DB.Repository.UserRepository.Shems import UserRead
from src.api.route import book_chapters as books_route
from src.application.services.chapter_service import (
    DuplicateChapterNumbersInRequestError,
    EmptyChapterListError,
)


class FakeChapterService:
    def __init__(
        self,
        *,
        headers=None,
        count_result: tuple[uuid.UUID, int] | None = None,
        chapter=None,
        book_exists: bool = True,
        chapter_exists: bool = True,
        add_error: Exception | None = None,
        update_error: Exception | None = None,
    ):
        self.headers = headers if headers is not None else []
        self.count_result = count_result
        self.chapter = chapter
        self.book_exists = book_exists
        self.chapter_exists = chapter_exists
        self.add_error = add_error
        self.update_error = update_error
        self.header_calls: list[uuid.UUID] = []
        self.count_calls: list[uuid.UUID] = []
        self.get_calls: list[tuple[uuid.UUID, uuid.UUID, int]] = []
        self.add_calls = []
        self.update_calls = []

    async def list_chapter_headers(self, book_id: uuid.UUID):
        self.header_calls.append(book_id)
        if not self.book_exists:
            raise BookNotFoundError
        return self.headers

    async def count_chapters(self, book_id: uuid.UUID) -> tuple[uuid.UUID, int]:
        self.count_calls.append(book_id)
        if not self.book_exists:
            raise BookNotFoundError
        if self.count_result is None:
            return book_id, 0
        return self.count_result

    async def get_chapter(
        self,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
        chapter_num: int,
    ):
        self.get_calls.append((user_id, book_id, chapter_num))
        if not self.chapter_exists:
            raise BookChapterNotFoundError
        return self.chapter

    async def add_chapters(self, user_id: uuid.UUID, book_id: uuid.UUID, chapters):
        self.add_calls.append((user_id, book_id, chapters))
        if self.add_error is not None:
            raise self.add_error

    async def update_chapter(
        self,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
        chapter_num: int,
        payload,
    ):
        self.update_calls.append((user_id, book_id, chapter_num, payload))
        if self.update_error is not None:
            raise self.update_error


def make_user() -> UserRead:
    return UserRead(
        id=uuid.uuid4(),
        email="reader@example.com",
        role=UserRole.USER,
        is_active=True,
        created_at=datetime.now(),
    )


def get_route(path: str, method: str):
    return next(
        (
            route
            for route in books_route.router.routes
            if route.path == path and method in route.methods
        ),
        None,
    )


def make_chapter(book_id: uuid.UUID, chapter_num: int = 3):
    return SimpleNamespace(
        id=uuid.uuid4(),
        book_id=book_id,
        chapter=chapter_num,
        chapter_name="Finale",
        description="Text",
        file=None,
        created_at=datetime.now(),
    )


def test_chapter_collection_route_is_registered_with_light_response_model():
    route = get_route("/books/{book_id}/chapters", "GET")

    assert route is not None
    assert route.response_model.__args__[0].__name__ == "BookChapterListRead"


def test_chapter_count_route_is_registered_with_count_response_model():
    route = get_route("/books/{book_id}/chapters/count", "GET")

    assert route is not None
    assert route.response_model.__name__ == "ChaptersCountResponse"


def test_single_chapter_route_is_registered_with_full_response_model():
    route = get_route("/books/{book_id}/chapters/{chapter_num}", "GET")

    assert route is not None
    assert route.response_model.__name__ == "BookChapterRead"


@pytest.mark.asyncio
async def test_get_book_chapters_returns_light_chapter_headers():
    book_id = uuid.uuid4()
    service = FakeChapterService(
        headers=[
            SimpleNamespace(chapter=1, chapter_name="Opening"),
            SimpleNamespace(chapter=2, chapter_name=None),
            SimpleNamespace(chapter=3, chapter_name="Finale"),
        ]
    )

    result = await books_route.get_book_chapters(
        book_id=book_id,
        chapter_service=service,
        current_user=make_user(),
    )

    assert [chapter.model_dump() for chapter in result] == [
        {"chapter": 1, "chapter_name": "Opening"},
        {"chapter": 2, "chapter_name": None},
        {"chapter": 3, "chapter_name": "Finale"},
    ]
    assert service.header_calls == [book_id]


@pytest.mark.asyncio
async def test_get_book_chapters_returns_empty_list_for_existing_book_without_chapters():
    book_id = uuid.uuid4()
    service = FakeChapterService(headers=[])

    result = await books_route.get_book_chapters(
        book_id=book_id,
        chapter_service=service,
        current_user=make_user(),
    )

    assert result == []
    assert service.header_calls == [book_id]


@pytest.mark.asyncio
async def test_get_book_chapters_returns_404_when_book_is_missing():
    book_id = uuid.uuid4()
    service = FakeChapterService(
        headers=[SimpleNamespace(chapter=1, chapter_name="Hidden")],
        book_exists=False,
    )

    with pytest.raises(HTTPException) as excinfo:
        await books_route.get_book_chapters(
            book_id=book_id,
            chapter_service=service,
            current_user=make_user(),
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Book not found"
    assert service.header_calls == [book_id]


@pytest.mark.asyncio
async def test_get_book_chapters_count_returns_count_response():
    requested_book_id = uuid.uuid4()
    existing_book_id = uuid.uuid4()
    service = FakeChapterService(count_result=(existing_book_id, 6))

    result = await books_route.get_book_chapters_count(
        book_id=requested_book_id,
        chapter_service=service,
        current_user=make_user(),
    )

    assert result.model_dump() == {
        "book_id": existing_book_id,
        "chapters_count": 6,
    }
    assert service.count_calls == [requested_book_id]


@pytest.mark.asyncio
async def test_get_book_chapters_count_returns_404_when_book_is_missing():
    book_id = uuid.uuid4()
    service = FakeChapterService(book_exists=False)

    with pytest.raises(HTTPException) as excinfo:
        await books_route.get_book_chapters_count(
            book_id=book_id,
            chapter_service=service,
            current_user=make_user(),
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Book not found"
    assert service.count_calls == [book_id]


@pytest.mark.asyncio
async def test_get_book_chapter_returns_full_chapter_response():
    book_id = uuid.uuid4()
    chapter_num = 4
    user = make_user()
    chapter = make_chapter(book_id=book_id, chapter_num=chapter_num)
    service = FakeChapterService(chapter=chapter)

    result = await books_route.get_book_chapter(
        book_id=book_id,
        chapter_num=chapter_num,
        chapter_service=service,
        current_user=user,
    )

    assert result.id == chapter.id
    assert result.book_id == book_id
    assert result.chapter == chapter_num
    assert result.chapter_name == "Finale"
    assert result.description == "Text"
    assert service.get_calls == [(user.id, book_id, chapter_num)]


@pytest.mark.asyncio
async def test_get_book_chapter_returns_404_when_chapter_is_missing():
    book_id = uuid.uuid4()
    chapter_num = 5
    user = make_user()
    service = FakeChapterService(chapter_exists=False)

    with pytest.raises(HTTPException) as excinfo:
        await books_route.get_book_chapter(
            book_id=book_id,
            chapter_num=chapter_num,
            chapter_service=service,
            current_user=user,
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Chapter not found"
    assert service.get_calls == [(user.id, book_id, chapter_num)]


@pytest.mark.asyncio
async def test_add_book_chapters_calls_service():
    book_id = uuid.uuid4()
    user = make_user()
    chapters = [
        BookChapterCreate(chapter=1, chapter_name="Start", description="Text"),
    ]
    service = FakeChapterService()

    result = await books_route.add_book_chapters(
        book_id=book_id,
        chapters=chapters,
        chapter_service=service,
        current_user=user,
    )

    assert result is None
    assert service.add_calls == [(user.id, book_id, chapters)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    [
        (BookNotFoundError(), 404, "Book not found"),
        (EmptyChapterListError(), 400, "Chapter list cannot be empty"),
        (
            DuplicateChapterNumbersInRequestError(),
            409,
            "Duplicate chapter numbers in request",
        ),
        (
            IntegrityError("insert", {}, Exception("duplicate")),
            409,
            "Duplicate chapter numbers for this book",
        ),
    ],
)
async def test_add_book_chapters_maps_service_errors_to_http(error, status_code, detail):
    book_id = uuid.uuid4()
    user = make_user()
    chapters = [
        BookChapterCreate(chapter=1, chapter_name="Start", description="Text"),
    ]
    service = FakeChapterService(add_error=error)

    with pytest.raises(HTTPException) as excinfo:
        await books_route.add_book_chapters(
            book_id=book_id,
            chapters=chapters,
            chapter_service=service,
            current_user=user,
        )

    assert excinfo.value.status_code == status_code
    assert excinfo.value.detail == detail
    assert service.add_calls == [(user.id, book_id, chapters)]


@pytest.mark.asyncio
async def test_update_book_chapter_calls_service():
    book_id = uuid.uuid4()
    chapter_num = 2
    user = make_user()
    payload = BookChapterUpdate(chapter_name="Updated")
    service = FakeChapterService()

    result = await books_route.update_book_chapter(
        book_id=book_id,
        chapter_num=chapter_num,
        payload=payload,
        chapter_service=service,
        current_user=user,
    )

    assert result is None
    assert service.update_calls == [(user.id, book_id, chapter_num, payload)]


@pytest.mark.asyncio
async def test_update_book_chapter_returns_404_when_chapter_is_missing():
    book_id = uuid.uuid4()
    chapter_num = 2
    user = make_user()
    payload = BookChapterUpdate(description="Updated text")
    service = FakeChapterService(update_error=BookChapterNotFoundError())

    with pytest.raises(HTTPException) as excinfo:
        await books_route.update_book_chapter(
            book_id=book_id,
            chapter_num=chapter_num,
            payload=payload,
            chapter_service=service,
            current_user=user,
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Chapter not found"
    assert service.update_calls == [(user.id, book_id, chapter_num, payload)]
