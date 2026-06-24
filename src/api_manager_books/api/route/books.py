import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from api_manager_books.schemas.books import (
    BookCreate,
    BookListRead,
    BookMetadataUpdate,
)
from api_manager_books.schemas.users import UserRead
from api_manager_books.api.dependencies import get_book_service
from api_manager_books.api.route.book_favorites import favorite_book, unfavorite_book  # noqa: F401
from api_manager_books.api.route.book_files import _iter_upload_chunks
from api_manager_books.api.security.utils import require_admin, require_auth
from api_manager_books.application.services.book_service import (
    BookAlreadyExistsError,
    BookNotFoundInServiceError,
    BookService,
)

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
        book_service: BookService = Depends(get_book_service),
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

    try:
        book_id = await book_service.add_book(
            current_user.id,
            payload,
            cover_chunks=_iter_upload_chunks(cover) if cover else None,
            file_chunks=_iter_upload_chunks(file) if file else None,
        )
    except BookAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Book already exists",
        )

    return {"id": book_id}


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
    book_service: BookService = Depends(get_book_service),
    current_user: UserRead = Depends(require_auth),
):
    """
    Получить список книг с фильтрацией и сортировкой.
    """
    return await book_service.list_books(
        user_id=current_user.id,
        author=author,
        series=series,
        offset=offset,
        limit=limit,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )

@router.patch("/{book_id}", status_code=status.HTTP_200_OK)
async def update_book(
    book_id: uuid.UUID,
    payload: BookMetadataUpdate,
    book_service: BookService = Depends(get_book_service),
    current_user: UserRead = Depends(require_admin),
):
    """
        Частично обновить книгу по ID.

        Обновляются только те поля, которые не равны None:
        title, author, description, series, genres, format.
        """
    try:
        await book_service.update_metadata(
            current_user.id,
            book_id,
            payload,
        )
    except BookNotFoundInServiceError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )
    return

@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_book(
    book_id: uuid.UUID,
    book_service: BookService = Depends(get_book_service),
    current_user: UserRead = Depends(require_admin),
):
    """
        Удалить книгу по ID.

        При удалении книги связанные главы (book_chapters)
        """

    try:
        await book_service.delete_book(current_user.id, book_id)
    except BookNotFoundInServiceError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )

    return
