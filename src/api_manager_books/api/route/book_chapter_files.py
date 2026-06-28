import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from api_manager_books.api.dependencies import get_chapter_file_service
from api_manager_books.api.security.utils import require_admin, require_auth
from api_manager_books.application.services.chapter_file_service import (
    ChapterFileNotFoundInServiceError,
    ChapterFileService,
)
from api_manager_books.db.Repository.BookChapterFileRepository.book_chapter_file_repository import (
    CHAPTER_FILE_CHUNK_SIZE,
)
from api_manager_books.schemas.book_chapter_files import (
    BookChapterFileCreateResponse,
    BookChapterFileListRead,
)
from api_manager_books.schemas.users import UserRead

router = APIRouter(prefix="/books", tags=["book-chapter-files"])


async def _iter_upload_chunks(upload: UploadFile):
    """Итерирует загруженный файл чанками."""
    while True:
        chunk = await upload.read(CHAPTER_FILE_CHUNK_SIZE)
        if not chunk:
            break
        yield chunk


def _content_disposition(filename: str) -> str:
    """Формирует заголовок скачивания с поддержкой Unicode."""
    ascii_name = filename.encode("ascii", "ignore").decode() or "chapter-file.bin"
    content_disposition = f'attachment; filename="{ascii_name}"'
    if filename != ascii_name:
        content_disposition += f"; filename*=UTF-8''{quote(filename, safe='')}"
    return content_disposition


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
            _iter_upload_chunks(file),
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
        headers={"Content-Disposition": _content_disposition(meta.file_name)},
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
