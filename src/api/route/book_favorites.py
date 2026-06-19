import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from src.DB.Repository.BookRepository.book_repository import BookNotFoundError, BookRepository
from src.DB.Repository.FavoriteBookRepository.favorite_book_repository import FavoriteBookRepository
from src.DB.Repository.LogRepository.Shems import LogCreate
from src.DB.Repository.LogRepository.log_repository import LogRepository
from src.DB.Repository.UserRepository.Shems import UserRead
from src.api.Dependencices import get_book_repo, get_favorite_book_repo, get_log_repo
from src.api.security.utils import require_auth

router = APIRouter(prefix="/books", tags=["book-favorites"])


@router.post("/{book_id}/favorite", status_code=status.HTTP_204_NO_CONTENT)
async def favorite_book(
    book_id: uuid.UUID,
    book_repo: BookRepository = Depends(get_book_repo),
    favorite_book_repo: FavoriteBookRepository = Depends(get_favorite_book_repo),
    log_repo: LogRepository = Depends(get_log_repo),
    current_user: UserRead = Depends(require_auth),
):
    try:
        await book_repo.ensure_exists(book_id)
    except BookNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )

    added = await favorite_book_repo.add_favorite(current_user.id, book_id)
    if added:
        await log_repo.log_from_dto(
            LogCreate(
                user_id=current_user.id,
                action="favorite_book",
                entity="books",
                entity_id=book_id,
                details=f"Книга с id={book_id} добавлена в избранное",
            )
        )
    return


@router.delete("/{book_id}/favorite", status_code=status.HTTP_204_NO_CONTENT)
async def unfavorite_book(
    book_id: uuid.UUID,
    book_repo: BookRepository = Depends(get_book_repo),
    favorite_book_repo: FavoriteBookRepository = Depends(get_favorite_book_repo),
    log_repo: LogRepository = Depends(get_log_repo),
    current_user: UserRead = Depends(require_auth),
):
    try:
        await book_repo.ensure_exists(book_id)
    except BookNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )

    removed = await favorite_book_repo.remove_favorite(current_user.id, book_id)
    if removed:
        await log_repo.log_from_dto(
            LogCreate(
                user_id=current_user.id,
                action="unfavorite_book",
                entity="books",
                entity_id=book_id,
                details=f"Книга с id={book_id} удалена из избранного",
            )
        )
    return
