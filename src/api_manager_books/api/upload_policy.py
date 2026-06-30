from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import HTTPException, UploadFile, status

UploadKind = Literal["cover", "book_file", "chapter_file"]


@dataclass(frozen=True)
class UploadPolicy:
    max_bytes: int
    mime_types: frozenset[str]
    check_signature: bool = False


MIB = 1024 * 1024

IMAGE_MIME_TYPES = {
    "jpg": frozenset({"image/jpeg"}),
    "jpeg": frozenset({"image/jpeg"}),
    "png": frozenset({"image/png"}),
    "webp": frozenset({"image/webp"}),
}
TEXT_MIME_TYPES = frozenset({"text/plain", "text/markdown"})

UPLOAD_POLICIES: dict[UploadKind, dict[str, UploadPolicy]] = {
    "cover": {
        extension: UploadPolicy(
            max_bytes=10 * MIB,
            mime_types=mime_types,
            check_signature=True,
        )
        for extension, mime_types in IMAGE_MIME_TYPES.items()
    },
    "book_file": {
        "epub": UploadPolicy(300 * MIB, frozenset({"application/epub+zip"}), True),
        "pdf": UploadPolicy(300 * MIB, frozenset({"application/pdf"}), True),
        "fb2": UploadPolicy(300 * MIB, TEXT_MIME_TYPES),
        "txt": UploadPolicy(300 * MIB, TEXT_MIME_TYPES),
        "mobi": UploadPolicy(300 * MIB, frozenset({"application/octet-stream"})),
        "azw3": UploadPolicy(300 * MIB, frozenset({"application/octet-stream"})),
    },
    "chapter_file": {
        "txt": UploadPolicy(5 * MIB, TEXT_MIME_TYPES),
        "md": UploadPolicy(5 * MIB, TEXT_MIME_TYPES),
        "jpg": UploadPolicy(15 * MIB, IMAGE_MIME_TYPES["jpg"], True),
        "jpeg": UploadPolicy(15 * MIB, IMAGE_MIME_TYPES["jpeg"], True),
        "png": UploadPolicy(15 * MIB, IMAGE_MIME_TYPES["png"], True),
        "webp": UploadPolicy(15 * MIB, IMAGE_MIME_TYPES["webp"], True),
        "pdf": UploadPolicy(50 * MIB, frozenset({"application/pdf"}), True),
        "mp3": UploadPolicy(150 * MIB, frozenset({"audio/mpeg", "audio/mp3"}), True),
    },
}


def _extension(filename: str | None) -> str:
    return Path(filename or "").suffix.lower().removeprefix(".")


def _unsupported_file_type() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="Unsupported file type",
    )


def _too_large() -> HTTPException:
    return HTTPException(
        status_code=413,
        detail="Uploaded file is too large",
    )


def _policy_for(kind: UploadKind, extension: str) -> UploadPolicy:
    policy = UPLOAD_POLICIES.get(kind, {}).get(extension)
    if policy is None:
        raise _unsupported_file_type()
    return policy


def _content_type(upload: UploadFile) -> str | None:
    content_type = upload.content_type
    if not content_type:
        return None
    return content_type.split(";", 1)[0].strip().lower()


def _validate_mime(upload: UploadFile, policy: UploadPolicy) -> None:
    content_type = _content_type(upload)
    if content_type is None:
        return
    if content_type not in policy.mime_types:
        raise _unsupported_file_type()


def _validate_content_length(upload: UploadFile, policy: UploadPolicy) -> None:
    raw_value = upload.headers.get("content-length")
    if raw_value is None:
        return

    try:
        content_length = int(raw_value)
    except ValueError:
        return

    if content_length > policy.max_bytes:
        raise _too_large()


def _has_mp3_frame_sync(chunk: bytes) -> bool:
    return len(chunk) >= 2 and chunk[0] == 0xFF and chunk[1] & 0xE0 == 0xE0


def _has_valid_signature(extension: str, chunk: bytes) -> bool:
    if extension in {"jpg", "jpeg"}:
        return chunk.startswith(b"\xff\xd8\xff")
    if extension == "png":
        return chunk.startswith(b"\x89PNG\r\n\x1a\n")
    if extension == "webp":
        return len(chunk) >= 12 and chunk.startswith(b"RIFF") and chunk[8:12] == b"WEBP"
    if extension == "pdf":
        return chunk.startswith(b"%PDF-")
    if extension == "epub":
        return chunk.startswith(b"PK\x03\x04")
    if extension == "mp3":
        return chunk.startswith(b"ID3") or _has_mp3_frame_sync(chunk)
    return True


def _validate_signature(extension: str, policy: UploadPolicy, chunk: bytes) -> None:
    if policy.check_signature and not _has_valid_signature(extension, chunk):
        raise _unsupported_file_type()


async def iter_upload_chunks_with_policy(
    upload: UploadFile,
    kind: UploadKind,
    *,
    chunk_size: int = 1024 * 1024,
) -> AsyncIterator[bytes]:
    """Итерирует файл с проверкой типа, сигнатуры и лимита размера."""
    extension = _extension(upload.filename)
    policy = _policy_for(kind, extension)
    _validate_mime(upload, policy)
    _validate_content_length(upload, policy)

    total = 0
    signature_checked = False

    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break

        if not signature_checked:
            _validate_signature(extension, policy, chunk)
            signature_checked = True

        total += len(chunk)
        if total > policy.max_bytes:
            raise _too_large()

        yield chunk
