from datetime import datetime
from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException

from src.DB.Repository.BookRepository.book_repository import BookNotFoundError
from src.DB.Repository.UserRepository.Enums import UserRole
from src.DB.Repository.UserRepository.Shems import UserRead
from src.api.route import book_chapters as books_route


class FakeBookRepo:
    def __init__(self, *, exists: bool = True):
        self.exists = exists
        self.calls: list[uuid.UUID] = []

    async def ensure_exists(self, book_id: uuid.UUID):
        self.calls.append(book_id)
        if not self.exists:
            raise BookNotFoundError
        return SimpleNamespace(id=book_id, title="Stored book")


class FakeChapterHeaderRepo:
    def __init__(self, rows):
        self.rows = rows
        self.calls: list[uuid.UUID] = []

    async def list_chapter_headers(self, book_id: uuid.UUID):
        self.calls.append(book_id)
        return self.rows


def make_user() -> UserRead:
    return UserRead(
        id=uuid.uuid4(),
        email="reader@example.com",
        role=UserRole.USER,
        is_active=True,
        created_at=datetime.now(),
    )


def get_chapter_collection_route():
    return next(
        (
            route
            for route in books_route.router.routes
            if route.path == "/books/{book_id}/chapters"
            and "GET" in route.methods
        ),
        None,
    )


def test_chapter_collection_route_is_registered_with_light_response_model():
    route = get_chapter_collection_route()

    assert route is not None
    assert route.response_model.__args__[0].__name__ == "BookChapterListRead"


@pytest.mark.asyncio
async def test_get_book_chapters_returns_light_chapter_headers():
    book_id = uuid.uuid4()
    book_repo = FakeBookRepo()
    chapter_repo = FakeChapterHeaderRepo(
        [
            SimpleNamespace(chapter=1, chapter_name="Opening"),
            SimpleNamespace(chapter=2, chapter_name=None),
            SimpleNamespace(chapter=3, chapter_name="Finale"),
        ]
    )

    result = await books_route.get_book_chapters(
        book_id=book_id,
        book_repo=book_repo,
        chapter_repo=chapter_repo,
        current_user=make_user(),
    )

    assert [chapter.model_dump() for chapter in result] == [
        {"chapter": 1, "chapter_name": "Opening"},
        {"chapter": 2, "chapter_name": None},
        {"chapter": 3, "chapter_name": "Finale"},
    ]
    assert book_repo.calls == [book_id]
    assert chapter_repo.calls == [book_id]


@pytest.mark.asyncio
async def test_get_book_chapters_returns_empty_list_for_existing_book_without_chapters():
    book_id = uuid.uuid4()
    book_repo = FakeBookRepo()
    chapter_repo = FakeChapterHeaderRepo([])

    result = await books_route.get_book_chapters(
        book_id=book_id,
        book_repo=book_repo,
        chapter_repo=chapter_repo,
        current_user=make_user(),
    )

    assert result == []
    assert book_repo.calls == [book_id]
    assert chapter_repo.calls == [book_id]


@pytest.mark.asyncio
async def test_get_book_chapters_returns_404_when_book_is_missing():
    book_id = uuid.uuid4()
    book_repo = FakeBookRepo(exists=False)
    chapter_repo = FakeChapterHeaderRepo(
        [SimpleNamespace(chapter=1, chapter_name="Hidden")]
    )

    with pytest.raises(HTTPException) as excinfo:
        await books_route.get_book_chapters(
            book_id=book_id,
            book_repo=book_repo,
            chapter_repo=chapter_repo,
            current_user=make_user(),
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Book not found"
    assert book_repo.calls == [book_id]
    assert chapter_repo.calls == []
