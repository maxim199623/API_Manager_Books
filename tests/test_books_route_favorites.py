import ast
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError
from starlette.datastructures import Headers

from src.api.route import book_files as book_files_route
from src.api.route import books as books_route
from src.api.route.books import get_books
from src.DB.Repository.BookRepository import Shems as book_shems
from src.DB.Repository.BookRepository.Shems import BookListRead
from src.DB.Repository.BookRepository.book_repository import (
    BOOK_BINARY_CHUNK_SIZE,
    BookNotFoundError,
)
from src.DB.Repository.UserRepository.Enums import UserRole
from src.DB.Repository.UserRepository.Shems import UserRead


def test_books_route_imports_book_dtos_from_repository_schemas() -> None:
    route_path = Path(books_route.__file__)
    tree = ast.parse(route_path.read_text(encoding="utf-8"))
    dto_names = {"BookCreate", "BookListRead", "BookMetadataUpdate"}

    service_imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "src.application.services.book_service"
        for alias in node.names
    }
    schema_imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "src.DB.Repository.BookRepository.Shems"
        for alias in node.names
    }

    assert service_imports.isdisjoint(dto_names)
    assert dto_names <= schema_imports


@dataclass
class FakeBook:
    id: uuid.UUID
    title: str
    author: str | None
    description: str | None
    series: str | None
    genres: str | None
    format: str | None
    cover: bytes | None
    file: bytes | None
    created_at: datetime


class FakeBookRepo:
    def __init__(self, books: list[FakeBook]):
        self.books = books
        self.calls: list[dict[str, object]] = []

    async def list_books(
        self,
        *,
        author: str | None,
        series: str | None,
        offset: int = 0,
        limit: int = 100,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        user_id: uuid.UUID | None = None,
    ) -> list[FakeBook]:
        self.calls.append(
            {
                "author": author,
                "series": series,
                "offset": offset,
                "limit": limit,
                "sort_by": sort_by,
                "sort_dir": sort_dir,
                "user_id": user_id,
            }
        )
        return self.books


class FakeFavoriteBookRepo:
    def __init__(self, favorite_ids: set[uuid.UUID]):
        self.favorite_ids = favorite_ids
        self.calls: list[tuple[uuid.UUID, list[uuid.UUID]]] = []

    async def list_favorite_book_ids(
        self,
        user_id: uuid.UUID,
        book_ids: list[uuid.UUID],
    ) -> set[uuid.UUID]:
        self.calls.append((user_id, book_ids))
        return self.favorite_ids


class FakeBookService:
    def __init__(self, books=None):
        self.books = books or []
        self.list_calls: list[dict[str, object]] = []

    async def list_books(
        self,
        *,
        user_id: uuid.UUID,
        author: str | None,
        series: str | None,
        offset: int,
        limit: int,
        sort_by: str,
        sort_dir: str,
    ):
        self.list_calls.append(
            {
                "user_id": user_id,
                "author": author,
                "series": series,
                "offset": offset,
                "limit": limit,
                "sort_by": sort_by,
                "sort_dir": sort_dir,
            }
        )
        return self.books


class FakeFavoriteService:
    def __init__(self, *, favorite_exists: bool = True, unfavorite_exists: bool = True):
        self.favorite_exists = favorite_exists
        self.unfavorite_exists = unfavorite_exists
        self.favorite_calls: list[tuple[uuid.UUID, uuid.UUID]] = []
        self.unfavorite_calls: list[tuple[uuid.UUID, uuid.UUID]] = []

    async def favorite_book(self, user_id: uuid.UUID, book_id: uuid.UUID) -> None:
        self.favorite_calls.append((user_id, book_id))
        if not self.favorite_exists:
            raise BookNotFoundError

    async def unfavorite_book(self, user_id: uuid.UUID, book_id: uuid.UUID) -> None:
        self.unfavorite_calls.append((user_id, book_id))
        if not self.unfavorite_exists:
            raise BookNotFoundError


class FakeLogRepo:
    def __init__(self):
        self.entries = []

    async def log_from_dto(self, payload) -> None:
        self.entries.append(payload)


class FakeBookUpdateRepo:
    def __init__(self, *, exists: bool = True):
        self.exists = exists
        self.calls = []

    async def update_book(self, book_id, payload, *, cover_chunks=None, file_chunks=None):
        cover_data = None
        if cover_chunks is not None:
            cover_data = [chunk async for chunk in cover_chunks]

        file_data = None
        if file_chunks is not None:
            file_data = [chunk async for chunk in file_chunks]

        self.calls.append(
            {
                "book_id": book_id,
                "payload": payload.model_dump(exclude_unset=True),
                "cover_chunks": cover_data,
                "file_chunks": file_data,
            }
        )

        if not self.exists:
            raise BookNotFoundError

        title = payload.title or "Stored title"
        return SimpleNamespace(id=book_id, title=title)


@dataclass(frozen=True)
class FakeBinaryMeta:
    content_type: str | None
    file_name: str | None
    size: int


class FakeBinaryRepository:
    def __init__(
        self,
        *,
        cover_meta: FakeBinaryMeta | None = None,
        file_meta: FakeBinaryMeta | None = None,
        cover_chunks: list[bytes] | None = None,
        file_chunks: list[bytes] | None = None,
    ):
        self.cover_meta = cover_meta
        self.file_meta = file_meta
        self.cover_chunks = cover_chunks or []
        self.file_chunks = file_chunks or []

    async def get_cover_meta(self, book_id: uuid.UUID) -> FakeBinaryMeta | None:
        return self.cover_meta

    async def get_file_meta(self, book_id: uuid.UUID) -> FakeBinaryMeta | None:
        return self.file_meta

    async def iter_cover_chunks(self, book_id: uuid.UUID):
        for chunk in self.cover_chunks:
            yield chunk

    async def iter_file_chunks(self, book_id: uuid.UUID):
        for chunk in self.file_chunks:
            yield chunk


class FakeBinaryRepositoryFactory:
    def __init__(self, repo: FakeBinaryRepository):
        self.repo = repo
        self.sessions = []

    def __call__(self, session):
        self.sessions.append(session)
        return self.repo


class FakeDBManager:
    @asynccontextmanager
    async def session(self):
        yield object()


def make_user() -> UserRead:
    return UserRead(
        id=uuid.uuid4(),
        email="reader@example.com",
        role=UserRole.USER,
        is_active=True,
        created_at=datetime.now(),
    )


def make_admin() -> UserRead:
    return UserRead(
        id=uuid.uuid4(),
        email="admin@example.com",
        role=UserRole.ADMIN,
        is_active=True,
        created_at=datetime.now(),
    )


def make_book(title: str, author: str | None = None, series: str | None = None) -> FakeBook:
    return FakeBook(
        id=uuid.uuid4(),
        title=title,
        author=author,
        description=None,
        series=series,
        genres=None,
        format="epub",
        cover=None,
        file=None,
        created_at=datetime.now(),
    )


def make_upload(filename: str, content: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        filename=filename,
        file=BytesIO(content),
        headers=Headers({"content-type": content_type}),
    )


@pytest.mark.asyncio
async def test_get_books_marks_favorites_in_response():
    current_user = make_user()
    favorite_book = make_book("Favorite Book", author="Author A", series="Series A")
    regular_book = make_book("Regular Book", author="Author B", series="Series B")
    books = [
        BookListRead.model_validate(favorite_book, from_attributes=True).model_copy(
            update={"is_favorite": True}
        ),
        BookListRead.model_validate(regular_book, from_attributes=True),
    ]
    book_service = FakeBookService(books)

    result = await get_books(
        author=None,
        series=None,
        book_service=book_service,
        current_user=current_user,
    )

    assert [book.is_favorite for book in result] == [True, False]
    assert [book.id for book in result] == [favorite_book.id, regular_book.id]
    assert book_service.list_calls[0]["user_id"] == current_user.id


@pytest.mark.asyncio
async def test_get_books_returns_empty_list_without_favorite_lookup():
    current_user = make_user()
    book_service = FakeBookService([])

    result = await get_books(
        author=None,
        series=None,
        book_service=book_service,
        current_user=current_user,
    )

    assert result == []
    assert len(book_service.list_calls) == 1


@pytest.mark.asyncio
async def test_get_books_passes_author_and_series_filters_to_repository():
    current_user = make_user()
    book_service = FakeBookService([])

    await get_books(
        author="Arkady Strugatsky",
        series="Noon Universe",
        book_service=book_service,
        current_user=current_user,
    )

    assert book_service.list_calls == [
        {
            "user_id": current_user.id,
            "author": "Arkady Strugatsky",
            "series": "Noon Universe",
            "offset": 0,
            "limit": 100,
            "sort_by": "created_at",
            "sort_dir": "desc",
        }
    ]


@pytest.mark.asyncio
async def test_get_books_passes_sorting_to_repository():
    current_user = make_user()
    book_service = FakeBookService([])

    await get_books(
        author=None,
        series=None,
        sort_by="progress",
        sort_dir="asc",
        book_service=book_service,
        current_user=current_user,
    )

    assert book_service.list_calls == [
        {
            "user_id": current_user.id,
            "author": None,
            "series": None,
            "offset": 0,
            "limit": 100,
            "sort_by": "progress",
            "sort_dir": "asc",
        }
    ]


@pytest.mark.asyncio
async def test_get_books_passes_pagination_to_repository():
    current_user = make_user()
    book_service = FakeBookService([])

    await get_books(
        author=None,
        series=None,
        offset=20,
        limit=10,
        book_service=book_service,
        current_user=current_user,
    )

    assert book_service.list_calls == [
        {
            "user_id": current_user.id,
            "author": None,
            "series": None,
            "offset": 20,
            "limit": 10,
            "sort_by": "created_at",
            "sort_dir": "desc",
        }
    ]


@pytest.mark.asyncio
async def test_favorite_book_route_calls_service_with_current_user_id():
    current_user = make_user()
    book_id = uuid.uuid4()
    favorite_service = FakeFavoriteService()

    result = await books_route.favorite_book(
        book_id=book_id,
        favorite_service=favorite_service,
        current_user=current_user,
    )

    assert result is None
    assert favorite_service.favorite_calls == [(current_user.id, book_id)]


@pytest.mark.asyncio
async def test_unfavorite_book_route_calls_service_with_current_user_id():
    current_user = make_user()
    book_id = uuid.uuid4()
    favorite_service = FakeFavoriteService()

    result = await books_route.unfavorite_book(
        book_id=book_id,
        favorite_service=favorite_service,
        current_user=current_user,
    )

    assert result is None
    assert favorite_service.unfavorite_calls == [(current_user.id, book_id)]


@pytest.mark.asyncio
async def test_favorite_book_returns_404_when_book_missing():
    current_user = make_user()
    book_id = uuid.uuid4()
    favorite_service = FakeFavoriteService(favorite_exists=False)

    with pytest.raises(HTTPException) as excinfo:
        await books_route.favorite_book(
            book_id=book_id,
            favorite_service=favorite_service,
            current_user=current_user,
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Book not found"
    assert favorite_service.favorite_calls == [(current_user.id, book_id)]


@pytest.mark.asyncio
async def test_unfavorite_book_returns_404_when_book_missing():
    current_user = make_user()
    book_id = uuid.uuid4()
    favorite_service = FakeFavoriteService(unfavorite_exists=False)

    with pytest.raises(HTTPException) as excinfo:
        await books_route.unfavorite_book(
            book_id=book_id,
            favorite_service=favorite_service,
            current_user=current_user,
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Book not found"
    assert favorite_service.unfavorite_calls == [(current_user.id, book_id)]


@pytest.mark.asyncio
async def test_get_book_cover_streams_chunked_bytes_with_actual_mime(monkeypatch):
    repo = FakeBinaryRepository(
        cover_meta=FakeBinaryMeta(content_type="image/webp", file_name=None, size=6),
        cover_chunks=[b"ab", b"cd", b"ef"],
    )
    factory = FakeBinaryRepositoryFactory(repo)
    monkeypatch.setattr(book_files_route, "BookRepository", factory)

    response = await book_files_route.get_book_cover(
        book_id=uuid.uuid4(),
        db_manager=FakeDBManager(),
        current_user=make_user(),
    )

    body = b"".join([chunk async for chunk in response.body_iterator])

    assert response.media_type == "image/webp"
    assert body == b"abcdef"
    assert len(factory.sessions) == 2


@pytest.mark.asyncio
async def test_get_book_file_streams_chunked_bytes_and_sets_filename(monkeypatch):
    repo = FakeBinaryRepository(
        file_meta=FakeBinaryMeta(
            content_type="application/epub+zip",
            file_name="solo-leveling.epub",
            size=8,
        ),
        file_chunks=[b"Solo", b"Leve", b"ling"],
    )
    factory = FakeBinaryRepositoryFactory(repo)
    monkeypatch.setattr(book_files_route, "BookRepository", factory)

    response = await book_files_route.get_book_file(
        book_id=uuid.uuid4(),
        db_manager=FakeDBManager(),
        current_user=make_user(),
    )

    body = b"".join([chunk async for chunk in response.body_iterator])

    assert response.media_type == "application/epub+zip"
    assert response.headers["Content-Disposition"] == 'attachment; filename="solo-leveling.epub"'
    assert body == b"SoloLeveling"
    assert len(factory.sessions) == 2


@pytest.mark.asyncio
async def test_update_book_cover_endpoint_replaces_cover_via_multipart():
    book_id = uuid.uuid4()
    book_repo = FakeBookUpdateRepo()
    log_repo = FakeLogRepo()

    result = await book_files_route.update_book_cover(
        book_id=book_id,
        cover=make_upload("cover.webp", b"cover-bytes", "image/webp"),
        book_repo=book_repo,
        log_repo=log_repo,
        current_user=make_admin(),
    )

    assert result is None
    assert book_repo.calls == [
        {
            "book_id": book_id,
            "payload": {"cover_mime": "image/webp"},
            "cover_chunks": [b"cover-bytes"],
            "file_chunks": None,
        }
    ]
    assert len(log_repo.entries) == 1
    assert log_repo.entries[0].action == "update_book_cover"
    assert log_repo.entries[0].entity_id == book_id


@pytest.mark.asyncio
async def test_update_book_file_endpoint_replaces_file_via_chunked_multipart():
    book_id = uuid.uuid4()
    book_repo = FakeBookUpdateRepo()
    log_repo = FakeLogRepo()
    payload = (b"a" * BOOK_BINARY_CHUNK_SIZE) + b"tail"

    result = await book_files_route.update_book_file(
        book_id=book_id,
        file=make_upload("solo-leveling.epub", payload, "application/epub+zip"),
        book_repo=book_repo,
        log_repo=log_repo,
        current_user=make_admin(),
    )

    assert result is None
    assert book_repo.calls == [
        {
            "book_id": book_id,
            "payload": {
                "file_name": "solo-leveling.epub",
                "file_mime": "application/epub+zip",
            },
            "cover_chunks": None,
            "file_chunks": [b"a" * BOOK_BINARY_CHUNK_SIZE, b"tail"],
        }
    ]
    assert len(log_repo.entries) == 1
    assert log_repo.entries[0].action == "update_book_file"
    assert log_repo.entries[0].entity_id == book_id


def test_book_metadata_update_rejects_binary_fields_after_split_endpoints():
    payload_cls = getattr(book_shems, "BookMetadataUpdate")

    with pytest.raises(ValidationError):
        payload_cls.model_validate({"cover": "Y292ZXI=", "title": "Ignored"})


def test_book_metadata_update_accepts_metadata_fields():
    payload_cls = getattr(book_shems, "BookMetadataUpdate")

    payload = payload_cls.model_validate({"title": "Updated title", "description": "Changed"})

    assert payload.title == "Updated title"
    assert payload.description == "Changed"
