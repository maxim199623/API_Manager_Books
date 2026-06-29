import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from api_manager_books.api.dependencies import get_book_file_service
from api_manager_books.api.download_headers import content_disposition_attachment
from api_manager_books.api.security.utils import require_admin, require_auth
from api_manager_books.api.upload_policy import iter_upload_chunks_with_policy
from api_manager_books.application.services.book_file_service import (
    BookFileNotFoundInServiceError,
    BookFileService,
)
from api_manager_books.schemas.users import UserRead

router = APIRouter(prefix="/books", tags=["book-files"])


@router.get("/{book_id}/cover")
async def get_book_cover(
    book_id: uuid.UUID,
    book_file_service: BookFileService = Depends(get_book_file_service),
    current_user: UserRead = Depends(require_auth),
):
    """Возвращает обложку книги потоком."""
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
    """Возвращает файл книги потоком."""
    meta = await book_file_service.get_file_meta(book_id)

    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    return StreamingResponse(
        book_file_service.iter_file_chunks(book_id),
        media_type=meta.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": content_disposition_attachment(
                meta.file_name,
                fallback=f"{book_id}.bin",
            )
        },
    )


@router.put("/{book_id}/cover", status_code=status.HTTP_204_NO_CONTENT)
async def update_book_cover(
    book_id: uuid.UUID,
    cover: UploadFile = File(...),
    book_file_service: BookFileService = Depends(get_book_file_service),
    current_user: UserRead = Depends(require_admin),
):
    """Обновляет обложку книги."""
    try:
        await book_file_service.update_cover(
            current_user.id,
            book_id,
            cover.content_type,
            iter_upload_chunks_with_policy(cover, "cover"),
        )
    except BookFileNotFoundInServiceError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        ) from err


@router.put("/{book_id}/file", status_code=status.HTTP_204_NO_CONTENT)
async def update_book_file(
    book_id: uuid.UUID,
    file: UploadFile = File(...),
    book_file_service: BookFileService = Depends(get_book_file_service),
    current_user: UserRead = Depends(require_admin),
):
    """Обновляет файл книги."""
    try:
        await book_file_service.update_file(
            current_user.id,
            book_id,
            file.filename,
            file.content_type,
            iter_upload_chunks_with_policy(file, "book_file"),
        )
    except BookFileNotFoundInServiceError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        ) from err
