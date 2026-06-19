import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.DB.Repository.BookChapterRepository.book_chapter_repository import BookChapterRepository
from src.DB.Repository.BookRepository.book_repository import BookNotFoundError, BookRepository
from src.DB.Repository.LogRepository.log_repository import LogRepository
from src.DB.Repository.UserRepository.Shems import UserRead
from src.api.Dependencices import get_book_chapter_repo, get_book_repo, get_log_repo
from src.api.security.utils import require_auth

router = APIRouter(prefix="/books", tags=["reading-history"])


@router.get("/chapters/read", response_model=list[int], status_code=status.HTTP_200_OK)
async def get_read_chapters(
    book_id: uuid.UUID | None = Query(None, description="Фильтр по книге"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: UserRead = Depends(require_auth),
    log_repo: LogRepository = Depends(get_log_repo),
    chapter_repo: BookChapterRepository = Depends(get_book_chapter_repo),
):
    """
    Список прочитанных (запрошенных) глав:
    - всех (если book_id не указан)
    - конкретной книги (если указан book_id)
    """

    if book_id is None:
        chapter_ids = await log_repo.list_read_chapter_ids_for_user(
            user_id=current_user.id,
            offset=offset,
            limit=limit,
        )
    else:
        chapter_ids = await log_repo.list_read_chapter_ids_for_user_and_book(
            user_id=current_user.id,
            book_id=book_id,
            offset=offset,
            limit=limit,
        )

    if not chapter_ids:
        return []

    return await chapter_repo.get_chapters_numbers_by_ids(chapter_ids)


@router.get("/{book_id}/chapters/read/count")
async def get_read_chapters_count(
    book_id: uuid.UUID,
    current_user: UserRead = Depends(require_auth),
    log_repo: LogRepository = Depends(get_log_repo),
    book_repo: BookRepository = Depends(get_book_repo),
):
    """
    Вернуть количество прочитанных (запрошенных) глав книги.
    """

    # Проверяем, что книга существует
    try:
        await book_repo.ensure_exists(book_id)
    except BookNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )

    count = await log_repo.count_read_chapters_for_user_and_book(
        user_id=current_user.id,
        book_id=book_id,
    )

    return {"book_id": book_id, "read_chapters": count}


@router.delete("/{book_id}/history")
async def clear_read_history_for_book(
    book_id: uuid.UUID,
    current_user: UserRead = Depends(require_auth),
    log_repo: LogRepository = Depends(get_log_repo),
):
    await log_repo.clear_read_history_for_user_and_book(
        user_id=current_user.id,
        book_id=book_id,
    )
    return
