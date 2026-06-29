from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from api_manager_books.api.upload_policy import (
    UPLOAD_POLICIES,
    UploadPolicy,
    iter_upload_chunks_with_policy,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\npayload"
PDF_BYTES = b"%PDF-1.7\npayload"
EPUB_BYTES = b"PK\x03\x04payload"
MP3_BYTES = b"ID3\x04\x00\x00payload"


def make_upload(
    filename: str,
    content: bytes,
    content_type: str | None = "text/plain",
    content_length: int | str | None = None,
) -> UploadFile:
    raw_headers = {}
    if content_type is not None:
        raw_headers["content-type"] = content_type
    if content_length is not None:
        raw_headers["content-length"] = str(content_length)
    headers = Headers(raw_headers)
    return UploadFile(filename=filename, file=BytesIO(content), headers=headers)


def patch_policy_limit(monkeypatch, kind: str, extension: str, max_bytes: int) -> None:
    policy = UPLOAD_POLICIES[kind][extension]
    patched = UploadPolicy(
        max_bytes=max_bytes,
        mime_types=policy.mime_types,
        check_signature=policy.check_signature,
    )
    monkeypatch.setitem(UPLOAD_POLICIES[kind], extension, patched)


@pytest.mark.asyncio
async def test_upload_policy_returns_chunks_for_allowed_file_within_limit():
    """Проверяет разрешенный файл в пределах лимита."""
    upload = make_upload("chapter.txt", b"abcdef")

    chunks = [
        chunk
        async for chunk in iter_upload_chunks_with_policy(
            upload,
            "chapter_file",
            chunk_size=2,
        )
    ]

    assert chunks == [b"ab", b"cd", b"ef"]


@pytest.mark.asyncio
async def test_upload_policy_raises_413_when_cumulative_bytes_exceed_limit(monkeypatch):
    """Проверяет отказ при превышении суммарного размера."""
    patch_policy_limit(monkeypatch, "chapter_file", "txt", 5)
    upload = make_upload("chapter.txt", b"abcdef")

    with pytest.raises(HTTPException) as excinfo:
        [
            chunk
            async for chunk in iter_upload_chunks_with_policy(
                upload,
                "chapter_file",
                chunk_size=3,
            )
        ]

    assert excinfo.value.status_code == 413


@pytest.mark.asyncio
async def test_upload_policy_raises_415_for_disallowed_extension():
    """Проверяет отказ для запрещенного расширения."""
    upload = make_upload("chapter.exe", b"abc")

    with pytest.raises(HTTPException) as excinfo:
        [
            chunk
            async for chunk in iter_upload_chunks_with_policy(
                upload,
                "chapter_file",
            )
        ]

    assert excinfo.value.status_code == 415


@pytest.mark.asyncio
async def test_upload_policy_accepts_missing_content_type_when_extension_allowed():
    """Проверяет, что отсутствие content-type не ломает разрешенное расширение."""
    upload = make_upload("cover.png", PNG_BYTES, content_type=None)

    chunks = [
        chunk
        async for chunk in iter_upload_chunks_with_policy(
            upload,
            "cover",
            chunk_size=10,
        )
    ]

    assert b"".join(chunks) == PNG_BYTES


@pytest.mark.asyncio
async def test_upload_policy_does_not_yield_oversized_chunk(monkeypatch):
    """Проверяет, что переполняющий чанк не отдается вызывающему коду."""
    patch_policy_limit(monkeypatch, "chapter_file", "txt", 5)
    upload = make_upload("chapter.txt", b"abcdef")
    chunks = []

    with pytest.raises(HTTPException) as excinfo:
        async for chunk in iter_upload_chunks_with_policy(
            upload,
            "chapter_file",
            chunk_size=3,
        ):
            chunks.append(chunk)

    assert excinfo.value.status_code == 413
    assert chunks == [b"abc"]


@pytest.mark.asyncio
async def test_book_file_accepts_payload_up_to_extension_limit(monkeypatch):
    """Проверяет лимит файла книги по расширению."""
    patch_policy_limit(monkeypatch, "book_file", "pdf", len(PDF_BYTES))
    upload = make_upload("book.pdf", PDF_BYTES, "application/pdf")

    chunks = [
        chunk
        async for chunk in iter_upload_chunks_with_policy(
            upload,
            "book_file",
            chunk_size=8,
        )
    ]

    assert b"".join(chunks) == PDF_BYTES


@pytest.mark.asyncio
async def test_book_file_raises_413_when_extension_limit_exceeded(monkeypatch):
    """Проверяет отказ при превышении лимита расширения файла книги."""
    patch_policy_limit(monkeypatch, "book_file", "pdf", len(PDF_BYTES) - 1)
    upload = make_upload("book.pdf", PDF_BYTES, "application/pdf")

    with pytest.raises(HTTPException) as excinfo:
        [
            chunk
            async for chunk in iter_upload_chunks_with_policy(
                upload,
                "book_file",
                chunk_size=8,
            )
        ]

    assert excinfo.value.status_code == 413


@pytest.mark.asyncio
async def test_chapter_file_accepts_valid_mp3():
    """Проверяет поддержку MP3 для файлов главы."""
    upload = make_upload("chapter.mp3", MP3_BYTES, "audio/mpeg")

    chunks = [
        chunk
        async for chunk in iter_upload_chunks_with_policy(
            upload,
            "chapter_file",
            chunk_size=4,
        )
    ]

    assert b"".join(chunks) == MP3_BYTES


@pytest.mark.asyncio
async def test_chapter_file_rejects_wav_extension():
    """Проверяет отказ для WAV в файлах главы."""
    upload = make_upload("sound.wav", b"RIFF....WAVE", "audio/wav")

    with pytest.raises(HTTPException) as excinfo:
        [
            chunk
            async for chunk in iter_upload_chunks_with_policy(
                upload,
                "chapter_file",
            )
        ]

    assert excinfo.value.status_code == 415


@pytest.mark.asyncio
async def test_chapter_file_applies_separate_mp3_limit(monkeypatch):
    """Проверяет отдельный лимит MP3 для файлов главы."""
    patch_policy_limit(monkeypatch, "chapter_file", "mp3", len(MP3_BYTES) - 1)
    upload = make_upload("chapter.mp3", MP3_BYTES, "audio/mpeg")

    with pytest.raises(HTTPException) as excinfo:
        [
            chunk
            async for chunk in iter_upload_chunks_with_policy(
                upload,
                "chapter_file",
                chunk_size=4,
            )
        ]

    assert excinfo.value.status_code == 413


@pytest.mark.asyncio
async def test_cover_png_rejects_exe_like_signature():
    """Проверяет отказ для PNG с чужой бинарной сигнатурой."""
    upload = make_upload("cover.png", b"MZ\x90\x00payload", "image/png")

    with pytest.raises(HTTPException) as excinfo:
        [
            chunk
            async for chunk in iter_upload_chunks_with_policy(
                upload,
                "cover",
            )
        ]

    assert excinfo.value.status_code == 415


@pytest.mark.asyncio
async def test_pdf_rejects_wrong_mime():
    """Проверяет отказ при несовпадении MIME и расширения."""
    upload = make_upload("file.pdf", PDF_BYTES, "text/plain")

    with pytest.raises(HTTPException) as excinfo:
        [
            chunk
            async for chunk in iter_upload_chunks_with_policy(
                upload,
                "book_file",
            )
        ]

    assert excinfo.value.status_code == 415


@pytest.mark.asyncio
async def test_oversized_content_length_rejected_before_first_yield(monkeypatch):
    """Проверяет ранний отказ по Content-Length."""
    patch_policy_limit(monkeypatch, "book_file", "epub", len(EPUB_BYTES) - 1)
    upload = make_upload(
        "book.epub",
        EPUB_BYTES,
        "application/epub+zip",
        content_length=len(EPUB_BYTES),
    )
    chunks = []

    with pytest.raises(HTTPException) as excinfo:
        async for chunk in iter_upload_chunks_with_policy(
            upload,
            "book_file",
            chunk_size=4,
        ):
            chunks.append(chunk)

    assert excinfo.value.status_code == 413
    assert chunks == []
