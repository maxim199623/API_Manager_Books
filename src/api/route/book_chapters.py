import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError

from src.DB.Repository.BookChapterRepository.Shems import (
    BookChapterCreate,
    BookChapterListRead,
    BookChapterRead,
    BookChapterUpdate,
)
from src.DB.Repository.BookChapterRepository.book_chapter_repository import BookChapterNotFoundError, BookChapterRepository
from src.DB.Repository.BookRepository.book_repository import BookNotFoundError, BookRepository
from src.DB.Repository.LogRepository.Shems import LogCreate
from src.DB.Repository.LogRepository.log_repository import LogRepository
from src.DB.Repository.UserRepository.Shems import UserRead
from src.api.Dependencices import (
    get_book_chapter_repo,
    get_book_repo,
    get_chapter_service,
    get_log_repo,
)
from src.api.Shems import ChaptersCountResponse
from src.api.security.utils import require_admin, require_auth
from src.application.services.chapter_service import ChapterService

router = APIRouter(prefix="/books", tags=["book-chapters"])


@router.post("/{book_id}/chapters",status_code=status.HTTP_201_CREATED)
async def add_book_chapters(
    book_id: uuid.UUID,
    chapters: list[BookChapterCreate],
    book_repo: BookRepository = Depends(get_book_repo),
    chapter_repo: BookChapterRepository = Depends(get_book_chapter_repo),
    log_repo: LogRepository = Depends(get_log_repo),
    current_user: UserRead = Depends(require_admin)):
    """Добавить список глав к книге."""

    #Проверяем, что книга существует
    try:
        book = await book_repo.ensure_exists(book_id)
    except BookNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )

    if not chapters:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chapter list cannot be empty",
        )

    chapter_numbers = [ch.chapter for ch in chapters]
    if len(chapter_numbers) != len(set(chapter_numbers)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate chapter numbers in request",
        )

    #Создаём главы
    try:
        created_count = await chapter_repo.create_chapters(book_id=book.id, data=chapters)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate chapter numbers for this book",
        )

    #Логируем операцию целиком
    await log_repo.log_from_dto(
        LogCreate(
            user_id=current_user.id,
            action="add_book_chapters",
            entity="book_chapters",
            entity_id=book.id,
            details=f"Добавлено глав: {created_count} для книги '{book.title}' (id={book.id})",
        )
    )
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
    except BookNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )

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
    except BookNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )

    return ChaptersCountResponse(
        book_id=existing_book_id,
        chapters_count=count,
    )


@router.patch("/{book_id}/chapters/{chapter_num}",status_code=status.HTTP_200_OK)
async def update_book_chapter(
    book_id: uuid.UUID,
    chapter_num: int,
    payload: BookChapterUpdate,
    chapter_repo: BookChapterRepository = Depends(get_book_chapter_repo),
    log_repo: LogRepository = Depends(get_log_repo),
    current_user: UserRead = Depends(require_admin),
):
    """
    Частично обновить главу книги по (book_id, chapter_num).
    """
    try:
        chapter = await chapter_repo.update_chapter_by_number(
            book_id=book_id,
            chapter_num=chapter_num,
            data=payload,
        )
    except BookChapterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chapter not found",
        )

    # Логируем изменение главы
    await log_repo.log_from_dto(
        LogCreate(
            user_id=current_user.id,
            action="update_chapter",
            entity="book_chapters",
            entity_id=chapter.id,
            details=f"Обновлена глава #{chapter_num} книги #{book_id}",
        )
    )

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
    except BookChapterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chapter not found",
        )

    # явная конвертация ORM -> Pydantic

    return BookChapterRead.model_validate(chapter, from_attributes=True)
