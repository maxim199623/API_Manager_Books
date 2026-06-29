import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from api_manager_books.api.dependencies import get_chapter_file_service
from api_manager_books.api.download_headers import content_disposition_attachment
from api_manager_books.api.security.utils import require_admin, require_auth
from api_manager_books.api.upload_policy import iter_upload_chunks_with_policy
from api_manager_books.application.services.chapter_file_service import (
    ChapterFileNotFoundInServiceError,
    ChapterFileService,
)
from api_manager_books.schemas.book_chapter_files import (
    BookChapterFileCreateResponse,
    BookChapterFileListRead,
)
from api_manager_books.schemas.users import UserRead

router = APIRouter(prefix="/books", tags=["book-chapter-files"])


@router.get(
    "/{book_id}/chapters/{chapter_num}/files",
    response_model=list[BookChapterFileListRead],
    status_code=status.HTTP_200_OK,
)
async def list_chapter_files(
    book_id: uuid.UUID,
    chapter_num: int,
    name: str | None = None,
    extension: str | None = None,
    offset: int = 0,
    limit: int = 100,
    chapter_file_service: ChapterFileService = Depends(get_chapter_file_service),
    current_user: UserRead = Depends(require_auth),
):
    """Возвращает метаданные файлов главы."""
    try:
        files = await chapter_file_service.list_files(
            book_id,
            chapter_num,
            name=name,
            extension=extension,
            offset=offset,
            limit=limit,
        )
    except ChapterFileNotFoundInServiceError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chapter file not found",
        ) from err

    return [
        BookChapterFileListRead.model_validate(file, from_attributes=True)
        for file in files
    ]


@router.post(
    "/{book_id}/chapters/{chapter_num}/files",
    response_model=BookChapterFileCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_chapter_file(
    book_id: uuid.UUID,
    chapter_num: int,
    file: UploadFile = File(...),
    chapter_file_service: ChapterFileService = Depends(get_chapter_file_service),
    current_user: UserRead = Depends(require_admin),
):
    """Загружает файл главы."""
    try:
        created = await chapter_file_service.create_file(
            current_user.id,
            book_id,
            chapter_num,
            file.filename,
            file.content_type,
            iter_upload_chunks_with_policy(file, "chapter_file"),
        )
    except ChapterFileNotFoundInServiceError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chapter file not found",
        ) from err

    return BookChapterFileCreateResponse.model_validate(created, from_attributes=True)


@router.get("/{book_id}/chapters/{chapter_num}/files/{file_id}")
async def download_chapter_file(
    book_id: uuid.UUID,
    chapter_num: int,
    file_id: uuid.UUID,
    chapter_file_service: ChapterFileService = Depends(get_chapter_file_service),
    current_user: UserRead = Depends(require_auth),
):
    """Скачивает конкретный файл главы."""
    try:
        meta = await chapter_file_service.get_file_meta(book_id, chapter_num, file_id)
    except ChapterFileNotFoundInServiceError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chapter file not found",
        ) from err

    return StreamingResponse(
        chapter_file_service.iter_file_chunks(file_id),
        media_type=meta.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": content_disposition_attachment(
                meta.file_name,
                fallback="chapter-file.bin",
            )
        },
    )


@router.delete(
    "/{book_id}/chapters/{chapter_num}/files/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_chapter_file(
    book_id: uuid.UUID,
    chapter_num: int,
    file_id: uuid.UUID,
    chapter_file_service: ChapterFileService = Depends(get_chapter_file_service),
    current_user: UserRead = Depends(require_admin),
):
    """Удаляет конкретный файл главы."""
    try:
        await chapter_file_service.delete_file(
            current_user.id,
            book_id,
            chapter_num,
            file_id,
        )
    except ChapterFileNotFoundInServiceError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chapter file not found",
        ) from err
