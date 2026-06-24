import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api_manager_books.db.Repository.BookRepository.book_repository import BookNotFoundError
from api_manager_books.schemas.users import UserRead
from api_manager_books.api.dependencies import get_reading_history_service
from api_manager_books.api.security.utils import require_auth
from api_manager_books.application.services.reading_history_service import ReadingHistoryService

router = APIRouter(prefix="/books", tags=["reading-history"])


@router.get("/chapters/read", response_model=list[int], status_code=status.HTTP_200_OK)
async def get_read_chapters(
    book_id: uuid.UUID | None = Query(None, description="Фильтр по книге"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: UserRead = Depends(require_auth),
    reading_history_service: ReadingHistoryService = Depends(get_reading_history_service),
):
    """
    Список прочитанных (запрошенных) глав:
    - всех (если book_id не указан)
    - конкретной книги (если указан book_id)
    """

    return await reading_history_service.list_read_chapters(
        user_id=current_user.id,
        book_id=book_id,
        offset=offset,
        limit=limit,
    )


@router.get("/{book_id}/chapters/read/count")
async def get_read_chapters_count(
    book_id: uuid.UUID,
    current_user: UserRead = Depends(require_auth),
    reading_history_service: ReadingHistoryService = Depends(get_reading_history_service),
):
    """
    Вернуть количество прочитанных (запрошенных) глав книги.
    """

    try:
        count = await reading_history_service.count_read_chapters(
            user_id=current_user.id,
            book_id=book_id,
        )
    except BookNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )

    return {"book_id": book_id, "read_chapters": count}


@router.delete("/{book_id}/history")
async def clear_read_history_for_book(
    book_id: uuid.UUID,
    current_user: UserRead = Depends(require_auth),
    reading_history_service: ReadingHistoryService = Depends(get_reading_history_service),
):
    await reading_history_service.clear_read_history_for_book(
        user_id=current_user.id,
        book_id=book_id,
    )
    return
