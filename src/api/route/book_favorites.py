import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from src.DB.Repository.BookRepository.book_repository import BookNotFoundError
from src.DB.Repository.UserRepository.Shems import UserRead
from src.api.dependencies import get_favorite_service
from src.api.security.utils import require_auth
from src.application.services.favorite_service import FavoriteService

router = APIRouter(prefix="/books", tags=["book-favorites"])


@router.post("/{book_id}/favorite", status_code=status.HTTP_204_NO_CONTENT)
async def favorite_book(
    book_id: uuid.UUID,
    favorite_service: FavoriteService = Depends(get_favorite_service),
    current_user: UserRead = Depends(require_auth),
):
    try:
        await favorite_service.favorite_book(current_user.id, book_id)
    except BookNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )
    return


@router.delete("/{book_id}/favorite", status_code=status.HTTP_204_NO_CONTENT)
async def unfavorite_book(
    book_id: uuid.UUID,
    favorite_service: FavoriteService = Depends(get_favorite_service),
    current_user: UserRead = Depends(require_auth),
):
    try:
        await favorite_service.unfavorite_book(current_user.id, book_id)
    except BookNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )
    return
