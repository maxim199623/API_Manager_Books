import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from src.DB.Repository.BookRepository.Shems import BookCreate, BookListRead, BookMetadataUpdate, BookUpdate
from src.DB.Repository.BookRepository.book_repository import BookRepository, BookNotFoundError
from src.DB.Repository.FavoriteBookRepository.favorite_book_repository import FavoriteBookRepository
from src.DB.Repository.LogRepository.Shems import LogCreate
from src.DB.Repository.LogRepository.log_repository import LogRepository
from src.DB.Repository.UserRepository.Shems import UserRead
from src.api.Dependencices import get_log_repo, get_book_repo, get_favorite_book_repo
from src.api.route.book_favorites import favorite_book, unfavorite_book  # noqa: F401
from src.api.route.book_files import _iter_upload_chunks
from src.api.security.utils import require_admin, require_auth
from src.api.websocket import manager as ws_manager

router = APIRouter(prefix="/books", tags=["books"])

BookSortField = Literal["created_at", "progress", "title"]
SortDirection = Literal["asc", "desc"]


@router.post("/add_book", status_code=status.HTTP_201_CREATED)
async def add_book(
        title: str = Form(...),
        author: str | None = Form(None),
        description: str | None = Form(None),
        series: str | None = Form(None),
        genres: str | None = Form(None),
        format: str | None = Form(None),
        cover: UploadFile | None = File(None),
        file: UploadFile | None = File(None),
        book_repo: BookRepository = Depends(get_book_repo),
        log_repo: LogRepository = Depends(get_log_repo),
        current_user: UserRead = Depends(require_admin)):
    """Добавление новой книги"""

    payload = BookCreate(
        title=title,
        author=author,
        description=description,
        series=series,
        genres=genres,
        format=format,
        cover_mime=cover.content_type if cover else None,
        file_name=file.filename if file else None,
        file_mime=file.content_type if file else None,
    )

    # Проверка на дубликат
    existing = await book_repo.get_by_title_author(payload.title, payload.author)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Book already exists",
        )

    # Создаём книгу
    book = await book_repo.create_book(
        payload,
        cover_chunks=_iter_upload_chunks(cover) if cover else None,
        file_chunks=_iter_upload_chunks(file) if file else None,
    )

    # Логируем добавление
    await log_repo.log_from_dto(
        LogCreate(
            user_id=current_user.id,
            action="add_book",
            entity="books",
            entity_id=book.id,
            details=f"Добавлена книга '{book.title}' автора {book.author}",
            )
        )
    await ws_manager.broadcast({"type":"new_book", "title":f"Добавлена книга '{book.title}'"})

    return {"id": book.id}


@router.get("/", response_model=list[BookListRead])
async def get_books(
    author: str | None = Query(default=None, description="Фильтр по автору"),
    series: str | None = Query(default=None, description="Фильтр по серии"),
    offset: Annotated[
        int,
        Query(ge=0, description="Смещение от начала отсортированного списка"),
    ] = 0,
    limit: Annotated[
        int,
        Query(ge=1, le=1000, description="Максимальное количество книг в ответе"),
    ] = 100,
    sort_by: Annotated[
        BookSortField,
        Query(description="Поле сортировки: created_at, progress, title"),
    ] = "created_at",
    sort_dir: Annotated[
        SortDirection,
        Query(description="Направление сортировки: asc или desc"),
    ] = "desc",
    book_repo: BookRepository = Depends(get_book_repo),
    favorite_book_repo: FavoriteBookRepository = Depends(get_favorite_book_repo),
    current_user: UserRead = Depends(require_auth),
):
    """
    Получить список книг с фильтрацией и сортировкой.
    """
    books = await book_repo.list_books(
        author=author,
        series=series,
        offset=offset,
        limit=limit,
        sort_by=sort_by,
        sort_dir=sort_dir,
        user_id=current_user.id,
    )
    if not books:
        return []

    favorite_ids = await favorite_book_repo.list_favorite_book_ids(
        current_user.id,
        [book.id for book in books],
    )

    return [
        BookListRead.model_validate(book, from_attributes=True).model_copy(
            update={"is_favorite": book.id in favorite_ids}
        )
        for book in books
    ]

@router.patch("/{book_id}", status_code=status.HTTP_200_OK)
async def update_book(
    book_id: uuid.UUID,
    payload: BookMetadataUpdate,
    book_repo: BookRepository = Depends(get_book_repo),
    log_repo: LogRepository = Depends(get_log_repo),
    current_user: UserRead = Depends(require_admin),
):
    """
        Частично обновить книгу по ID.

        Обновляются только те поля, которые не равны None:
        title, author, description, series, genres, format.
        """
    try:
        book = await book_repo.update_book(
            book_id,
            BookUpdate(**payload.model_dump(exclude_unset=True)),
        )
    except BookNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )
    await log_repo.log_from_dto(
        LogCreate(
            user_id=current_user.id,
            action="update_book",
            entity="books",
            entity_id=book.id,
            details=f"Книга '{book.title}' (id={book.id}) была обновлена",
        )
    )
    return

@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_book(
    book_id: uuid.UUID,
    book_repo: BookRepository = Depends(get_book_repo),
    log_repo: LogRepository = Depends(get_log_repo),
    current_user: UserRead = Depends(require_admin),
):
    """
        Удалить книгу по ID.

        При удалении книги связанные главы (book_chapters)
        """

    deleted = await book_repo.delete_book(book_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )

        # Логируем удаление книги
    await log_repo.log_action(
            user_id=current_user.id,
            action="delete_book",
            entity="books",
            entity_id=book_id,
            details=f"Книга с id={book_id} была удалена",
        )
    await ws_manager.broadcast({"type":"del_book"})

    return
