import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from api_manager_books.application.services.chapter_file_service import (
    ChapterFileNotFoundInServiceError,
    ChapterFileService,
)
from api_manager_books.db.Repository.BookChapterFileRepository.book_chapter_file_repository import (
    BookChapterFileNotFoundError,
)
from api_manager_books.db.Repository.BookChapterRepository.book_chapter_repository import (
    BookChapterNotFoundError,
)


@dataclass(frozen=True)
class FakeChapterFileMeta:
    id: uuid.UUID
    chapter_id: uuid.UUID
    file_name: str
    extension: str | None
    content_type: str | None
    size: int
    chunks_count: int


class FakeChapterRepo:
    def __init__(self, *, chapter=None, error: Exception | None = None):
        self.chapter = chapter
        self.error = error
        self.calls: list[tuple[uuid.UUID, int]] = []

    async def ensure_exists_by_book_and_number(self, book_id: uuid.UUID, chapter_num: int):
        self.calls.append((book_id, chapter_num))
        if self.error is not None:
            raise self.error
        return self.chapter


class FakeChapterFileRepo:
    def __init__(
        self,
        *,
        created_meta: FakeChapterFileMeta | None = None,
        files: list[FakeChapterFileMeta] | None = None,
        file_meta: FakeChapterFileMeta | None = None,
        chunks: list[bytes] | None = None,
        delete_result: bool = True,
        belongs_error: Exception | None = None,
    ):
        self.created_meta = created_meta
        self.files = files or []
        self.file_meta = file_meta
        self.chunks = chunks or []
        self.delete_result = delete_result
        self.belongs_error = belongs_error
        self.create_calls = []
        self.list_calls = []
        self.meta_calls: list[uuid.UUID] = []
        self.belongs_calls: list[tuple[uuid.UUID, uuid.UUID]] = []
        self.chunk_calls: list[uuid.UUID] = []
        self.delete_calls: list[tuple[uuid.UUID, uuid.UUID]] = []

    async def create_file(self, chapter_id, *, file_name, content_type, chunks):
        data = [chunk async for chunk in chunks]
        self.create_calls.append(
            {
                "chapter_id": chapter_id,
                "file_name": file_name,
                "content_type": content_type,
                "chunks": data,
            }
        )
        return self.created_meta

    async def list_files(self, chapter_id, *, name=None, extension=None, offset=0, limit=100):
        self.list_calls.append(
            {
                "chapter_id": chapter_id,
                "name": name,
                "extension": extension,
                "offset": offset,
                "limit": limit,
            }
        )
        return self.files

    async def get_file_meta(self, file_id: uuid.UUID):
        self.meta_calls.append(file_id)
        return self.file_meta

    async def ensure_file_belongs_to_chapter(self, chapter_id: uuid.UUID, file_id: uuid.UUID):
        self.belongs_calls.append((chapter_id, file_id))
        if self.belongs_error is not None:
            raise self.belongs_error
        return SimpleNamespace(id=file_id, chapter_id=chapter_id)

    async def iter_file_chunks(self, file_id: uuid.UUID):
        self.chunk_calls.append(file_id)
        for chunk in self.chunks:
            yield chunk

    async def delete_file(self, chapter_id: uuid.UUID, file_id: uuid.UUID):
        self.delete_calls.append((chapter_id, file_id))
        return self.delete_result


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


class FakeFileRepoFactory:
    def __init__(self, repo: FakeChapterFileRepo):
        self.repo = repo
        self.sessions = []

    def __call__(self, session):
        self.sessions.append(session)
        return self.repo


async def iter_chunks(chunks: list[bytes]):
    for chunk in chunks:
        yield chunk


def make_service(
    *,
    chapter_repo: FakeChapterRepo,
    file_repo: FakeChapterFileRepo,
    log_repo: FakeLogRepo | None = None,
    session_manager: FakeSessionManager | None = None,
    file_repo_factory: FakeFileRepoFactory | None = None,
) -> ChapterFileService:
    return ChapterFileService(
        chapter_repo=chapter_repo,
        file_repo=file_repo,
        log_repo=log_repo or FakeLogRepo(),
        session_manager=session_manager or FakeSessionManager(),
        file_repo_factory=file_repo_factory or FakeFileRepoFactory(file_repo),
    )


@pytest.mark.asyncio
async def test_create_file_checks_chapter_passes_chunks_and_logs():
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    chapter_id = uuid.uuid4()
    file_id = uuid.uuid4()
    chapter = SimpleNamespace(id=chapter_id)
    meta = FakeChapterFileMeta(
        id=file_id,
        chapter_id=chapter_id,
        file_name="chapter.epub",
        extension="epub",
        content_type="application/epub+zip",
        size=9,
        chunks_count=2,
    )
    chapter_repo = FakeChapterRepo(chapter=chapter)
    file_repo = FakeChapterFileRepo(created_meta=meta)
    log_repo = FakeLogRepo()
    service = make_service(chapter_repo=chapter_repo, file_repo=file_repo, log_repo=log_repo)

    result = await service.create_file(
        user_id,
        book_id,
        7,
        "chapter.epub",
        "application/epub+zip",
        iter_chunks([b"chapter-", b"7"]),
    )

    assert result == meta
    assert chapter_repo.calls == [(book_id, 7)]
    assert file_repo.create_calls == [
        {
            "chapter_id": chapter_id,
            "file_name": "chapter.epub",
            "content_type": "application/epub+zip",
            "chunks": [b"chapter-", b"7"],
        }
    ]
    assert log_repo.entries[0].user_id == user_id
    assert log_repo.entries[0].action == "create_chapter_file"
    assert log_repo.entries[0].entity == "book_chapter_files"
    assert log_repo.entries[0].entity_id == file_id


@pytest.mark.asyncio
async def test_create_file_maps_missing_chapter_to_service_error_without_log():
    file_repo = FakeChapterFileRepo()
    log_repo = FakeLogRepo()
    service = make_service(
        chapter_repo=FakeChapterRepo(error=BookChapterNotFoundError()),
        file_repo=file_repo,
        log_repo=log_repo,
    )

    with pytest.raises(ChapterFileNotFoundInServiceError):
        await service.create_file(
            uuid.uuid4(),
            uuid.uuid4(),
            1,
            "chapter.txt",
            "text/plain",
            iter_chunks([b"text"]),
        )

    assert file_repo.create_calls == []
    assert log_repo.entries == []


@pytest.mark.asyncio
async def test_list_files_checks_chapter_and_passes_filters():
    book_id = uuid.uuid4()
    chapter_id = uuid.uuid4()
    files = [
        FakeChapterFileMeta(uuid.uuid4(), chapter_id, "a.txt", "txt", "text/plain", 1, 1)
    ]
    file_repo = FakeChapterFileRepo(files=files)
    service = make_service(
        chapter_repo=FakeChapterRepo(chapter=SimpleNamespace(id=chapter_id)),
        file_repo=file_repo,
    )

    result = await service.list_files(
        book_id,
        3,
        name="a",
        extension=".txt",
        offset=5,
        limit=10,
    )

    assert result == files
    assert file_repo.list_calls == [
        {
            "chapter_id": chapter_id,
            "name": "a",
            "extension": ".txt",
            "offset": 5,
            "limit": 10,
        }
    ]


@pytest.mark.asyncio
async def test_get_file_meta_checks_file_belongs_to_chapter():
    book_id = uuid.uuid4()
    chapter_id = uuid.uuid4()
    file_id = uuid.uuid4()
    meta = FakeChapterFileMeta(file_id, chapter_id, "a.txt", "txt", "text/plain", 1, 1)
    file_repo = FakeChapterFileRepo(file_meta=meta)
    service = make_service(
        chapter_repo=FakeChapterRepo(chapter=SimpleNamespace(id=chapter_id)),
        file_repo=file_repo,
    )

    result = await service.get_file_meta(book_id, 3, file_id)

    assert result == meta
    assert file_repo.belongs_calls == [(chapter_id, file_id)]
    assert file_repo.meta_calls == [file_id]


@pytest.mark.asyncio
async def test_get_file_meta_maps_missing_file_to_service_error():
    service = make_service(
        chapter_repo=FakeChapterRepo(chapter=SimpleNamespace(id=uuid.uuid4())),
        file_repo=FakeChapterFileRepo(belongs_error=BookChapterFileNotFoundError()),
    )

    with pytest.raises(ChapterFileNotFoundInServiceError):
        await service.get_file_meta(uuid.uuid4(), 1, uuid.uuid4())


@pytest.mark.asyncio
async def test_streaming_opens_separate_session():
    file_id = uuid.uuid4()
    stream_repo = FakeChapterFileRepo(chunks=[b"ab", b"cd"])
    session_manager = FakeSessionManager()
    repo_factory = FakeFileRepoFactory(stream_repo)
    service = make_service(
        chapter_repo=FakeChapterRepo(chapter=SimpleNamespace(id=uuid.uuid4())),
        file_repo=FakeChapterFileRepo(),
        session_manager=session_manager,
        file_repo_factory=repo_factory,
    )

    chunks = [chunk async for chunk in service.iter_file_chunks(file_id)]

    assert chunks == [b"ab", b"cd"]
    assert stream_repo.chunk_calls == [file_id]
    assert repo_factory.sessions == session_manager.opened
    assert session_manager.closed == session_manager.opened


@pytest.mark.asyncio
async def test_delete_file_checks_chapter_and_logs_deletion():
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    chapter_id = uuid.uuid4()
    file_id = uuid.uuid4()
    file_repo = FakeChapterFileRepo(delete_result=True)
    log_repo = FakeLogRepo()
    service = make_service(
        chapter_repo=FakeChapterRepo(chapter=SimpleNamespace(id=chapter_id)),
        file_repo=file_repo,
        log_repo=log_repo,
    )

    await service.delete_file(user_id, book_id, 4, file_id)

    assert file_repo.delete_calls == [(chapter_id, file_id)]
    assert log_repo.entries[0].user_id == user_id
    assert log_repo.entries[0].action == "delete_chapter_file"
    assert log_repo.entries[0].entity == "book_chapter_files"
    assert log_repo.entries[0].entity_id == file_id


@pytest.mark.asyncio
async def test_delete_file_maps_missing_file_to_service_error_without_log():
    log_repo = FakeLogRepo()
    service = make_service(
        chapter_repo=FakeChapterRepo(chapter=SimpleNamespace(id=uuid.uuid4())),
        file_repo=FakeChapterFileRepo(delete_result=False),
        log_repo=log_repo,
    )

    with pytest.raises(ChapterFileNotFoundInServiceError):
        await service.delete_file(uuid.uuid4(), uuid.uuid4(), 1, uuid.uuid4())

    assert log_repo.entries == []
