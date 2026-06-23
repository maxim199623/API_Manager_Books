import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from src.schemas.users import UserRead
from src.api.dependencies import get_book_file_service
from src.api.security.utils import require_admin, require_auth
from src.application.services.book_file_service import (
    BOOK_BINARY_CHUNK_SIZE,
    BookFileNotFoundInServiceError,
    BookFileService,
)

router = APIRouter(prefix="/books", tags=["book-files"])


async def _iter_upload_chunks(upload: UploadFile):
    while True:
        chunk = await upload.read(BOOK_BINARY_CHUNK_SIZE)
        if not chunk:
            break
        yield chunk


@router.get("/{book_id}/cover")
async def get_book_cover(
    book_id: uuid.UUID,
    book_file_service: BookFileService = Depends(get_book_file_service),
    current_user: UserRead = Depends(require_auth),
):
    meta = await book_file_service.get_cover_meta(book_id)

    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cover not found",
        )

    return StreamingResponse(
        book_file_service.iter_cover_chunks(book_id),
        media_type=meta.content_type or "application/octet-stream",
    )


@router.get("/{book_id}/file")
async def get_book_file(
    book_id: uuid.UUID,
    book_file_service: BookFileService = Depends(get_book_file_service),
    current_user: UserRead = Depends(require_auth),
):
    meta = await book_file_service.get_file_meta(book_id)

    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    filename = meta.file_name or f"{book_id}.bin"
    ascii_name = filename.encode("ascii", "ignore").decode() or f"{book_id}.bin"

    content_disposition = f'attachment; filename="{ascii_name}"'
    if filename != ascii_name:
        content_disposition += f"; filename*=UTF-8''{quote(filename, safe='')}"

    return StreamingResponse(
        book_file_service.iter_file_chunks(book_id),
        media_type=meta.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": content_disposition
        },
    )


@router.put("/{book_id}/cover", status_code=status.HTTP_204_NO_CONTENT)
async def update_book_cover(
    book_id: uuid.UUID,
    cover: UploadFile = File(...),
    book_file_service: BookFileService = Depends(get_book_file_service),
    current_user: UserRead = Depends(require_admin),
):
    try:
        await book_file_service.update_cover(
            current_user.id,
            book_id,
            cover.content_type,
            _iter_upload_chunks(cover),
        )
    except BookFileNotFoundInServiceError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )


@router.put("/{book_id}/file", status_code=status.HTTP_204_NO_CONTENT)
async def update_book_file(
    book_id: uuid.UUID,
    file: UploadFile = File(...),
    book_file_service: BookFileService = Depends(get_book_file_service),
    current_user: UserRead = Depends(require_admin),
):
    try:
        await book_file_service.update_file(
            current_user.id,
            book_id,
            file.filename,
            file.content_type,
            _iter_upload_chunks(file),
        )
    except BookFileNotFoundInServiceError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )
