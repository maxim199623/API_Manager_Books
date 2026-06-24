from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace
import uuid

import pytest

from api_manager_books.db.Repository.BookRepository.book_repository import BookNotFoundError
from api_manager_books.application.services.book_file_service import (
    BookFileNotFoundInServiceError,
    BookFileService,
)


@dataclass(frozen=True)
class FakeBinaryMeta:
    content_type: str | None
    file_name: str | None
    size: int


class FakeBookRepo:
    def __init__(
        self,
        *,
        cover_meta: FakeBinaryMeta | None = None,
        file_meta: FakeBinaryMeta | None = None,
        cover_chunks: list[bytes] | None = None,
        file_chunks: list[bytes] | None = None,
        updated_book=None,
        update_error: Exception | None = None,
    ):
        self.cover_meta = cover_meta
        self.file_meta = file_meta
        self.cover_chunks = cover_chunks or []
        self.file_chunks = file_chunks or []
        self.updated_book = updated_book
        self.update_error = update_error
        self.update_calls = []
        self.cover_meta_calls: list[uuid.UUID] = []
        self.file_meta_calls: list[uuid.UUID] = []
        self.cover_chunk_calls: list[uuid.UUID] = []
        self.file_chunk_calls: list[uuid.UUID] = []

    async def get_cover_meta(self, book_id: uuid.UUID):
        self.cover_meta_calls.append(book_id)
        return self.cover_meta

    async def get_file_meta(self, book_id: uuid.UUID):
        self.file_meta_calls.append(book_id)
        return self.file_meta

    async def iter_cover_chunks(self, book_id: uuid.UUID):
        self.cover_chunk_calls.append(book_id)
        for chunk in self.cover_chunks:
            yield chunk

    async def iter_file_chunks(self, book_id: uuid.UUID):
        self.file_chunk_calls.append(book_id)
        for chunk in self.file_chunks:
            yield chunk

    async def update_book(self, book_id, payload, *, cover_chunks=None, file_chunks=None):
        cover_data = [chunk async for chunk in cover_chunks] if cover_chunks is not None else None
        file_data = [chunk async for chunk in file_chunks] if file_chunks is not None else None
        self.update_calls.append(
            {
                "book_id": book_id,
                "payload": payload.model_dump(exclude_unset=True),
                "cover_chunks": cover_data,
                "file_chunks": file_data,
            }
        )
        if self.update_error is not None:
            raise self.update_error
        return self.updated_book


class FakeLogRepo:
    def __init__(self):
        self.entries = []

    async def log_from_dto(self, payload):
        self.entries.append(payload)


class FakeSessionManager:
    def __init__(self):
        self.opened = []
        self.closed = []

    @asynccontextmanager
    async def session(self):
        session = object()
        self.opened.append(session)
        try:
            yield session
        finally:
            self.closed.append(session)


class FakeBookRepoFactory:
    def __init__(self, repo: FakeBookRepo):
        self.repo = repo
        self.sessions = []

    def __call__(self, session):
        self.sessions.append(session)
        return self.repo


async def iter_chunks(chunks: list[bytes]):
    for chunk in chunks:
        yield chunk


def make_service(
    book_repo: FakeBookRepo,
    *,
    log_repo: FakeLogRepo | None = None,
    session_manager: FakeSessionManager | None = None,
    book_repo_factory: FakeBookRepoFactory | None = None,
) -> BookFileService:
    return BookFileService(
        book_repo=book_repo,
        log_repo=log_repo or FakeLogRepo(),
        session_manager=session_manager or FakeSessionManager(),
        book_repo_factory=book_repo_factory or FakeBookRepoFactory(book_repo),
    )


@pytest.mark.asyncio
async def test_update_cover_logs_and_passes_chunks():
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    updated_book = SimpleNamespace(id=book_id, title="Stored title")
    book_repo = FakeBookRepo(updated_book=updated_book)
    log_repo = FakeLogRepo()
    service = make_service(book_repo, log_repo=log_repo)

    await service.update_cover(
        user_id,
        book_id,
        "image/webp",
        iter_chunks([b"cover-", b"bytes"]),
    )

    assert book_repo.update_calls == [
        {
            "book_id": book_id,
            "payload": {"cover_mime": "image/webp"},
            "cover_chunks": [b"cover-", b"bytes"],
            "file_chunks": None,
        }
    ]
    assert log_repo.entries[0].user_id == user_id
    assert log_repo.entries[0].action == "update_book_cover"
    assert log_repo.entries[0].entity == "books"
    assert log_repo.entries[0].entity_id == book_id
    assert log_repo.entries[0].details == f"Обновлена обложка книги 'Stored title' (id={book_id})"


@pytest.mark.asyncio
async def test_update_file_logs_filename_mime_and_passes_chunks():
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    updated_book = SimpleNamespace(id=book_id, title="Stored title")
    book_repo = FakeBookRepo(updated_book=updated_book)
    log_repo = FakeLogRepo()
    service = make_service(book_repo, log_repo=log_repo)

    await service.update_file(
        user_id,
        book_id,
        "book.epub",
        "application/epub+zip",
        iter_chunks([b"file-", b"bytes"]),
    )

    assert book_repo.update_calls == [
        {
            "book_id": book_id,
            "payload": {
                "file_name": "book.epub",
                "file_mime": "application/epub+zip",
            },
            "cover_chunks": None,
            "file_chunks": [b"file-", b"bytes"],
        }
    ]
    assert log_repo.entries[0].user_id == user_id
    assert log_repo.entries[0].action == "update_book_file"
    assert log_repo.entries[0].entity_id == book_id
    assert log_repo.entries[0].details == f"Обновлен файл книги 'Stored title' (id={book_id})"


@pytest.mark.asyncio
async def test_update_missing_book_maps_to_service_error_without_log():
    book_repo = FakeBookRepo(update_error=BookNotFoundError())
    log_repo = FakeLogRepo()
    service = make_service(book_repo, log_repo=log_repo)

    with pytest.raises(BookFileNotFoundInServiceError):
        await service.update_cover(
            uuid.uuid4(),
            uuid.uuid4(),
            "image/webp",
            iter_chunks([b"cover"]),
        )

    assert log_repo.entries == []


@pytest.mark.asyncio
async def test_cover_and_file_meta_return_none_for_missing_binary():
    book_id = uuid.uuid4()
    book_repo = FakeBookRepo()
    service = make_service(book_repo)

    assert await service.get_cover_meta(book_id) is None
    assert await service.get_file_meta(book_id) is None
    assert book_repo.cover_meta_calls == [book_id]
    assert book_repo.file_meta_calls == [book_id]


@pytest.mark.asyncio
async def test_streaming_iter_opens_session_and_yields_chunks():
    book_id = uuid.uuid4()
    stream_repo = FakeBookRepo(cover_chunks=[b"ab", b"cd"])
    session_manager = FakeSessionManager()
    repo_factory = FakeBookRepoFactory(stream_repo)
    service = make_service(
        FakeBookRepo(),
        session_manager=session_manager,
        book_repo_factory=repo_factory,
    )

    chunks = [chunk async for chunk in service.iter_cover_chunks(book_id)]

    assert chunks == [b"ab", b"cd"]
    assert stream_repo.cover_chunk_calls == [book_id]
    assert repo_factory.sessions == session_manager.opened
    assert session_manager.closed == session_manager.opened
