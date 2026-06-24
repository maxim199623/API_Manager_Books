import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError

from api_manager_books.api.dependencies import get_chapter_service
from api_manager_books.api.security.utils import require_admin, require_auth
from api_manager_books.application.services.chapter_service import (
    ChapterService,
    DuplicateChapterNumbersInRequestError,
    EmptyChapterListError,
)
from api_manager_books.db.Repository.BookChapterRepository.book_chapter_repository import BookChapterNotFoundError
from api_manager_books.db.Repository.BookRepository.book_repository import BookNotFoundError
from api_manager_books.schemas.api import ChaptersCountResponse
from api_manager_books.schemas.book_chapters import (
    BookChapterCreate,
    BookChapterListRead,
    BookChapterRead,
    BookChapterUpdate,
)
from api_manager_books.schemas.users import UserRead

router = APIRouter(prefix="/books", tags=["book-chapters"])


@router.post("/{book_id}/chapters",status_code=status.HTTP_201_CREATED)
async def add_book_chapters(
    book_id: uuid.UUID,
    chapters: list[BookChapterCreate],
    chapter_service: ChapterService = Depends(get_chapter_service),
    current_user: UserRead = Depends(require_admin)):
    """Добавить список глав к книге."""
    try:
        await chapter_service.add_chapters(
            user_id=current_user.id,
            book_id=book_id,
            chapters=chapters,
        )
    except BookNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        ) from err
    except EmptyChapterListError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chapter list cannot be empty",
        ) from err
    except DuplicateChapterNumbersInRequestError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate chapter numbers in request",
        ) from err
    except IntegrityError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate chapter numbers for this book",
        ) from err
    return


@router.get(
    "/{book_id}/chapters",
    response_model=list[BookChapterListRead],
    status_code=status.HTTP_200_OK,
)
async def get_book_chapters(
    book_id: uuid.UUID,
    chapter_service: ChapterService = Depends(get_chapter_service),
    current_user: UserRead = Depends(require_auth),
):
    """
    Вернуть номера и названия глав книги в порядке номеров глав.
    """
    try:
        chapters = await chapter_service.list_chapter_headers(book_id)
    except BookNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        ) from err

    return [
        BookChapterListRead.model_validate(chapter, from_attributes=True)
        for chapter in chapters
    ]


@router.get("/{book_id}/chapters/count",response_model=ChaptersCountResponse,status_code=status.HTTP_200_OK)
async def get_book_chapters_count(
    book_id: uuid.UUID,
    chapter_service: ChapterService = Depends(get_chapter_service),
    current_user: UserRead = Depends(require_auth),
):
    """
    Вернуть количество глав у книги с указанным ID.
    """
    try:
        existing_book_id, count = await chapter_service.count_chapters(book_id)
    except BookNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        ) from err

    return ChaptersCountResponse(
        book_id=existing_book_id,
        chapters_count=count,
    )


@router.patch("/{book_id}/chapters/{chapter_num}",status_code=status.HTTP_200_OK)
async def update_book_chapter(
    book_id: uuid.UUID,
    chapter_num: int,
    payload: BookChapterUpdate,
    chapter_service: ChapterService = Depends(get_chapter_service),
    current_user: UserRead = Depends(require_admin),
):
    """
    Частично обновить главу книги по (book_id, chapter_num).
    """
    try:
        await chapter_service.update_chapter(
            user_id=current_user.id,
            book_id=book_id,
            chapter_num=chapter_num,
            payload=payload,
        )
    except BookChapterNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chapter not found",
        ) from err

    return

@router.get("/{book_id}/chapters/{chapter_num}", response_model=BookChapterRead, status_code=status.HTTP_200_OK)
async def get_book_chapter(
    book_id: uuid.UUID,
    chapter_num: int,
    chapter_service: ChapterService = Depends(get_chapter_service),
    current_user: UserRead = Depends(require_auth),
):
    """
    Получить конкретную главу книги по (book_id, chapter_num).
    """
    try:
        chapter = await chapter_service.get_chapter(
            user_id=current_user.id,
            book_id=book_id,
            chapter_num=chapter_num,
        )
    except BookChapterNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chapter not found",
        ) from err

    # явная конвертация ORM -> Pydantic

    return BookChapterRead.model_validate(chapter, from_attributes=True)
