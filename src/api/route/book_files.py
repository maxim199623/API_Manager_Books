import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from src.DB.Repository.BookRepository.Shems import BookUpdate
from src.DB.Repository.BookRepository.book_repository import BOOK_BINARY_CHUNK_SIZE, BookNotFoundError, BookRepository
from src.DB.Repository.LogRepository.Shems import LogCreate
from src.DB.Repository.LogRepository.log_repository import LogRepository
from src.DB.Repository.UserRepository.Shems import UserRead
from src.api.dependencies import get_book_repo, get_db_manager, get_log_repo
from src.api.security.utils import require_admin, require_auth

router = APIRouter(prefix="/books", tags=["book-files"])


async def _iter_upload_chunks(upload: UploadFile):
    while True:
        chunk = await upload.read(BOOK_BINARY_CHUNK_SIZE)
        if not chunk:
            break
        yield chunk


async def _update_book_binary(
    *,
    book_id: uuid.UUID,
    payload: BookUpdate,
    book_repo: BookRepository,
    log_repo: LogRepository,
    current_user: UserRead,
    action: str,
    details: str,
    cover_chunks=None,
    file_chunks=None,
) -> None:
    try:
        book = await book_repo.update_book(
            book_id,
            payload,
            cover_chunks=cover_chunks,
            file_chunks=file_chunks,
        )
    except BookNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )

    await log_repo.log_from_dto(
        LogCreate(
            user_id=current_user.id,
            action=action,
            entity="books",
            entity_id=book.id,
            details=details.format(title=book.title, book_id=book.id),
        )
    )


@router.get("/{book_id}/cover")
async def get_book_cover(
    book_id: uuid.UUID,
    db_manager=Depends(get_db_manager),
    current_user: UserRead = Depends(require_auth),
):
    async with db_manager.session() as session:
        book_repo = BookRepository(session)
        meta = await book_repo.get_cover_meta(book_id)

    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cover not found",
        )

    async def iter_cover():
        async with db_manager.session() as session:
            book_repo = BookRepository(session)
            async for chunk in book_repo.iter_cover_chunks(book_id):
                yield chunk

    return StreamingResponse(
        iter_cover(),
        media_type=meta.content_type or "application/octet-stream",
    )


@router.get("/{book_id}/file")
async def get_book_file(
    book_id: uuid.UUID,
    db_manager=Depends(get_db_manager),
    current_user: UserRead = Depends(require_auth),
):
    async with db_manager.session() as session:
        book_repo = BookRepository(session)
        meta = await book_repo.get_file_meta(book_id)

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

    async def iter_file():
        async with db_manager.session() as session:
            book_repo = BookRepository(session)
            async for chunk in book_repo.iter_file_chunks(book_id):
                yield chunk

    return StreamingResponse(
        iter_file(),
        media_type=meta.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": content_disposition
        },
    )


@router.put("/{book_id}/cover", status_code=status.HTTP_204_NO_CONTENT)
async def update_book_cover(
    book_id: uuid.UUID,
    cover: UploadFile = File(...),
    book_repo: BookRepository = Depends(get_book_repo),
    log_repo: LogRepository = Depends(get_log_repo),
    current_user: UserRead = Depends(require_admin),
):
    await _update_book_binary(
        book_id=book_id,
        payload=BookUpdate(cover_mime=cover.content_type),
        book_repo=book_repo,
        log_repo=log_repo,
        current_user=current_user,
        action="update_book_cover",
        details="Обновлена обложка книги '{title}' (id={book_id})",
        cover_chunks=_iter_upload_chunks(cover),
    )


@router.put("/{book_id}/file", status_code=status.HTTP_204_NO_CONTENT)
async def update_book_file(
    book_id: uuid.UUID,
    file: UploadFile = File(...),
    book_repo: BookRepository = Depends(get_book_repo),
    log_repo: LogRepository = Depends(get_log_repo),
    current_user: UserRead = Depends(require_admin),
):
    await _update_book_binary(
        book_id=book_id,
        payload=BookUpdate(
            file_name=file.filename,
            file_mime=file.content_type,
        ),
        book_repo=book_repo,
        log_repo=log_repo,
        current_user=current_user,
        action="update_book_file",
        details="Обновлен файл книги '{title}' (id={book_id})",
        file_chunks=_iter_upload_chunks(file),
    )
