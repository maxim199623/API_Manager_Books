import uuid
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from api_manager_books.api import main_router
from api_manager_books.api.route import book_chapter_files as route
from api_manager_books.application.services.chapter_file_service import (
    ChapterFileNotFoundInServiceError,
)
from api_manager_books.db.Repository.BookChapterFileRepository.book_chapter_file_repository import (
    CHAPTER_FILE_CHUNK_SIZE,
)
from api_manager_books.schemas.enums import UserRole
from api_manager_books.schemas.users import UserRead

MP3_BYTES = b"ID3\x04\x00\x00payload"


@dataclass(frozen=True)
class FakeChapterFileMeta:
    id: uuid.UUID
    chapter_id: uuid.UUID
    file_name: str
    extension: str | None
    content_type: str | None
    size: int
    chunks_count: int


class FakeChapterFileService:
    def __init__(
        self,
        *,
        files: list[FakeChapterFileMeta] | None = None,
        file_meta: FakeChapterFileMeta | None = None,
        chunks: list[bytes] | None = None,
        create_meta: FakeChapterFileMeta | None = None,
        error: Exception | None = None,
    ):
        self.files = files or []
        self.file_meta = file_meta
        self.chunks = chunks or []
        self.create_meta = create_meta
        self.error = error
        self.list_calls = []
        self.meta_calls = []
        self.chunk_calls = []
        self.create_calls = []
        self.delete_calls = []

    async def list_files(
        self,
        book_id: uuid.UUID,
        chapter_num: int,
        *,
        name: str | None = None,
        extension: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ):
        self.list_calls.append(
            {
                "book_id": book_id,
                "chapter_num": chapter_num,
                "name": name,
                "extension": extension,
                "offset": offset,
                "limit": limit,
            }
        )
        if self.error is not None:
            raise self.error
        return self.files

    async def get_file_meta(
        self,
        book_id: uuid.UUID,
        chapter_num: int,
        file_id: uuid.UUID,
    ):
        self.meta_calls.append((book_id, chapter_num, file_id))
        if self.error is not None:
            raise self.error
        return self.file_meta

    async def iter_file_chunks(self, file_id: uuid.UUID):
        self.chunk_calls.append(file_id)
        for chunk in self.chunks:
            yield chunk

    async def create_file(
        self,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
        chapter_num: int,
        file_name: str,
        content_type: str | None,
        chunks,
    ):
        data = [chunk async for chunk in chunks]
        self.create_calls.append(
            {
                "user_id": user_id,
                "book_id": book_id,
                "chapter_num": chapter_num,
                "file_name": file_name,
                "content_type": content_type,
                "chunks": data,
            }
        )
        if self.error is not None:
            raise self.error
        return self.create_meta

    async def delete_file(
        self,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
        chapter_num: int,
        file_id: uuid.UUID,
    ) -> None:
        self.delete_calls.append((user_id, book_id, chapter_num, file_id))
        if self.error is not None:
            raise self.error


def make_user(role: UserRole = UserRole.USER) -> UserRead:
    return UserRead(
        id=uuid.uuid4(),
        email="reader@example.com",
        role=role,
        is_active=True,
        created_at=datetime.now(),
    )


def make_upload(filename: str, content: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        filename=filename,
        file=BytesIO(content),
        headers=Headers({"content-type": content_type}),
    )


def get_route(path: str, method: str):
    return next(
        (
            candidate
            for candidate in route.router.routes
            if candidate.path == path and method in candidate.methods
        ),
        None,
    )


def test_chapter_files_router_is_registered_in_main_router():
    router_is_included = any(
        candidate.original_router is route.router
        for candidate in main_router.routes
        if hasattr(candidate, "original_router")
    )
    paths = {
        (candidate.path, frozenset(candidate.methods))
        for candidate in route.router.routes
        if hasattr(candidate, "path") and hasattr(candidate, "methods")
    }

    assert router_is_included
    assert (
        "/books/{book_id}/chapters/{chapter_num}/files",
        frozenset({"GET"}),
    ) in paths


def test_chapter_file_routes_are_registered():
    assert get_route("/books/{book_id}/chapters/{chapter_num}/files", "GET") is not None
    assert get_route("/books/{book_id}/chapters/{chapter_num}/files", "POST") is not None
    assert (
        get_route(
            "/books/{book_id}/chapters/{chapter_num}/files/{file_id}",
            "GET",
        )
        is not None
    )
    assert (
        get_route(
            "/books/{book_id}/chapters/{chapter_num}/files/{file_id}",
            "DELETE",
        )
        is not None
    )


@pytest.mark.asyncio
async def test_list_chapter_files_returns_metadata_and_passes_filters():
    book_id = uuid.uuid4()
    chapter_id = uuid.uuid4()
    meta = FakeChapterFileMeta(
        id=uuid.uuid4(),
        chapter_id=chapter_id,
        file_name="draft.pdf",
        extension="pdf",
        content_type="application/pdf",
        size=12,
        chunks_count=1,
    )
    service = FakeChapterFileService(files=[meta])

    result = await route.list_chapter_files(
        book_id=book_id,
        chapter_num=3,
        name="draft",
        extension=".pdf",
        offset=5,
        limit=10,
        chapter_file_service=service,
        current_user=make_user(),
    )

    assert [item.model_dump() for item in result] == [
        {
            "id": meta.id,
            "chapter_id": chapter_id,
            "file_name": "draft.pdf",
            "extension": "pdf",
            "content_type": "application/pdf",
            "size": 12,
            "chunks_count": 1,
        }
    ]
    assert service.list_calls == [
        {
            "book_id": book_id,
            "chapter_num": 3,
            "name": "draft",
            "extension": ".pdf",
            "offset": 5,
            "limit": 10,
        }
    ]


@pytest.mark.asyncio
async def test_download_chapter_file_streams_bytes_and_sets_content_disposition():
    book_id = uuid.uuid4()
    file_id = uuid.uuid4()
    meta = FakeChapterFileMeta(
        id=file_id,
        chapter_id=uuid.uuid4(),
        file_name="глава 1.txt",
        extension="txt",
        content_type="text/plain",
        size=8,
        chunks_count=2,
    )
    service = FakeChapterFileService(file_meta=meta, chunks=[b"ab", b"cd"])

    response = await route.download_chapter_file(
        book_id=book_id,
        chapter_num=1,
        file_id=file_id,
        chapter_file_service=service,
        current_user=make_user(),
    )
    body = b"".join([chunk async for chunk in response.body_iterator])

    assert response.media_type == "text/plain"
    assert body == b"abcd"
    assert service.meta_calls == [(book_id, 1, file_id)]
    assert service.chunk_calls == [file_id]
    assert response.headers["Content-Disposition"].startswith('attachment; filename="1.txt"')
    assert "filename*=UTF-8''" in response.headers["Content-Disposition"]


@pytest.mark.asyncio
async def test_download_chapter_file_maps_missing_file_to_404():
    service = FakeChapterFileService(error=ChapterFileNotFoundInServiceError())

    with pytest.raises(HTTPException) as excinfo:
        await route.download_chapter_file(
            book_id=uuid.uuid4(),
            chapter_num=1,
            file_id=uuid.uuid4(),
            chapter_file_service=service,
            current_user=make_user(),
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Chapter file not found"


@pytest.mark.asyncio
async def test_upload_chapter_file_passes_filename_content_type_and_chunks():
    book_id = uuid.uuid4()
    chapter_id = uuid.uuid4()
    created = FakeChapterFileMeta(
        id=uuid.uuid4(),
        chapter_id=chapter_id,
        file_name="archive.txt",
        extension="txt",
        content_type="text/plain",
        size=CHAPTER_FILE_CHUNK_SIZE + 4,
        chunks_count=2,
    )
    service = FakeChapterFileService(create_meta=created)
    user = make_user(UserRole.ADMIN)
    payload = (b"a" * CHAPTER_FILE_CHUNK_SIZE) + b"tail"

    result = await route.upload_chapter_file(
        book_id=book_id,
        chapter_num=9,
        file=make_upload("archive.txt", payload, "text/plain"),
        chapter_file_service=service,
        current_user=user,
    )

    assert result.model_dump()["id"] == created.id
    assert service.create_calls == [
        {
            "user_id": user.id,
            "book_id": book_id,
            "chapter_num": 9,
            "file_name": "archive.txt",
            "content_type": "text/plain",
            "chunks": [b"a" * CHAPTER_FILE_CHUNK_SIZE, b"tail"],
        }
    ]


@pytest.mark.asyncio
async def test_upload_chapter_file_accepts_mp3_and_passes_chunks():
    service = FakeChapterFileService(
        create_meta=FakeChapterFileMeta(
            id=uuid.uuid4(),
            chapter_id=uuid.uuid4(),
            file_name="chapter.mp3",
            extension="mp3",
            content_type="audio/mpeg",
            size=len(MP3_BYTES),
            chunks_count=1,
        )
    )
    user = make_user(UserRole.ADMIN)

    result = await route.upload_chapter_file(
        book_id=uuid.uuid4(),
        chapter_num=1,
        file=make_upload("chapter.mp3", MP3_BYTES, "audio/mpeg"),
        chapter_file_service=service,
        current_user=user,
    )

    assert result.model_dump()["id"] == service.create_meta.id
    assert service.create_calls[0]["file_name"] == "chapter.mp3"
    assert service.create_calls[0]["content_type"] == "audio/mpeg"
    assert service.create_calls[0]["chunks"] == [MP3_BYTES]


@pytest.mark.asyncio
async def test_upload_chapter_file_rejects_disallowed_extension_before_storage():
    service = FakeChapterFileService()

    with pytest.raises(HTTPException) as excinfo:
        await route.upload_chapter_file(
            book_id=uuid.uuid4(),
            chapter_num=1,
            file=make_upload("payload.exe", b"bad", "application/octet-stream"),
            chapter_file_service=service,
            current_user=make_user(UserRole.ADMIN),
        )

    assert excinfo.value.status_code == 415
    assert service.create_calls == []


@pytest.mark.asyncio
async def test_upload_chapter_file_rejects_wav_before_storage():
    service = FakeChapterFileService()

    with pytest.raises(HTTPException) as excinfo:
        await route.upload_chapter_file(
            book_id=uuid.uuid4(),
            chapter_num=1,
            file=make_upload("sound.wav", b"RIFF....WAVE", "audio/wav"),
            chapter_file_service=service,
            current_user=make_user(UserRole.ADMIN),
        )

    assert excinfo.value.status_code == 415
    assert service.create_calls == []


@pytest.mark.asyncio
async def test_upload_chapter_file_maps_missing_chapter_to_404():
    service = FakeChapterFileService(error=ChapterFileNotFoundInServiceError())

    with pytest.raises(HTTPException) as excinfo:
        await route.upload_chapter_file(
            book_id=uuid.uuid4(),
            chapter_num=1,
            file=make_upload("a.txt", b"a", "text/plain"),
            chapter_file_service=service,
            current_user=make_user(UserRole.ADMIN),
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Chapter file not found"


@pytest.mark.asyncio
async def test_delete_chapter_file_calls_service():
    service = FakeChapterFileService()
    user = make_user(UserRole.ADMIN)
    book_id = uuid.uuid4()
    file_id = uuid.uuid4()

    result = await route.delete_chapter_file(
        book_id=book_id,
        chapter_num=4,
        file_id=file_id,
        chapter_file_service=service,
        current_user=user,
    )

    assert result is None
    assert service.delete_calls == [(user.id, book_id, 4, file_id)]


@pytest.mark.asyncio
async def test_delete_chapter_file_maps_missing_file_to_404():
    service = FakeChapterFileService(error=ChapterFileNotFoundInServiceError())

    with pytest.raises(HTTPException) as excinfo:
        await route.delete_chapter_file(
            book_id=uuid.uuid4(),
            chapter_num=1,
            file_id=uuid.uuid4(),
            chapter_file_service=service,
            current_user=make_user(UserRole.ADMIN),
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Chapter file not found"
