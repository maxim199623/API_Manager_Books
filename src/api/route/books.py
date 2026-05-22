import uuid

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.exc import IntegrityError

from src.DB.Repository import BookChapter
from src.DB.Repository.BookChapterRepository.Shems import BookChapterRead, BookChapterCreate, BookChapterUpdate
from src.DB.Repository.BookChapterRepository.book_chapter_repository import BookChapterRepository,BookChapterNotFoundError
from src.DB.Repository.BookRepository.Shems import BookRead, BookCreate, BookUpdate
from src.DB.Repository.BookRepository.book_repository import BookRepository, BookNotFoundError
from src.DB.Repository.FavoriteBookRepository.favorite_book_repository import FavoriteBookRepository
from src.DB.Repository.LogRepository.Shems import LogCreate
from src.DB.Repository.LogRepository.log_repository import LogRepository
from src.DB.Repository.UserRepository.Shems import UserRead
from src.api.Dependencices import  get_log_repo, get_book_repo, get_book_chapter_repo, get_favorite_book_repo
from src.api.Shems import ChaptersCountResponse
from src.api.security.utils import require_admin, require_auth
from src.api.websocket import manager as ws_manager

router = APIRouter(prefix="/books", tags=["books"])

@router.post("/add_book", status_code=status.HTTP_201_CREATED)
async def add_book(payload: BookCreate,
                   book_repo: BookRepository = Depends(get_book_repo),
                   log_repo: LogRepository = Depends(get_log_repo), current_user: UserRead = Depends(require_admin)):
    """Добавление новой книги"""

    # Проверка на дубликат
    existing = await book_repo.get_by_title_author(payload.title, payload.author)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Book already exists",
        )

    # Создаём книгу
    print(type(payload.cover))
    book = await book_repo.create_book(payload)

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


@router.get("/", response_model=list[BookRead])
async def get_books(author: str | None = Query(default=None, description="Фильтр по автору"),
    series: str | None = Query(default=None, description="Фильтр по серии"),
        book_repo: BookRepository = Depends(get_book_repo),
        favorite_book_repo: FavoriteBookRepository = Depends(get_favorite_book_repo),
        current_user: UserRead = Depends(require_auth)):
    """
        Получить список книг с возможностью фильтрации по автору и серии.
        """
    books = await book_repo.list_books(
        author=author,
        series=series
    )
    if not books:
        return []

    favorite_ids = await favorite_book_repo.list_favorite_book_ids(
        current_user.id,
        [book.id for book in books],
    )

    return [
        BookRead.model_validate(book, from_attributes=True).model_copy(
            update={"is_favorite": book.id in favorite_ids}
        )
        for book in books
    ]


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

@router.patch("/{book_id}", status_code=status.HTTP_200_OK)
async def update_book(
    book_id: uuid.UUID,
    payload: BookUpdate,
    book_repo: BookRepository = Depends(get_book_repo),
    log_repo: LogRepository = Depends(get_log_repo),
    current_user: UserRead = Depends(require_admin),
):
    """
        Частично обновить книгу по ID.

        Обновляются только те поля, которые не равны None:
        cover, title, author, description, series, format, file.
        """
    try:
        book = await book_repo.update_book(book_id, payload)
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

    created: list[BookChapter] = []

    #Создаём главы по одной
    try:
        for ch in chapters:
            chapter = await chapter_repo.create_chapter(book_id=book.id, data=ch)
            created.append(chapter)
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
            details=f"Добавлено глав: {len(created)} для книги '{book.title}' (id={book.id})",
        )
    )
    return

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

@router.get("/{book_id}/chapters/count",response_model=ChaptersCountResponse,status_code=status.HTTP_200_OK)
async def get_book_chapters_count(
    book_id: uuid.UUID,
    book_repo: BookRepository = Depends(get_book_repo),
    chapter_repo: BookChapterRepository = Depends(get_book_chapter_repo),
    current_user = Depends(require_auth),   # заменяй на require_admin при желании
):
    """
    Вернуть количество глав у книги с указанным ID.
    """

    # Проверяем, что книга существует
    try:
        book = await book_repo.ensure_exists(book_id)
    except BookNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )

    count = await chapter_repo.count_chapters(book.id)

    return ChaptersCountResponse(
        book_id=book.id,
        chapters_count=count,
    )

@router.get("/{book_id}/chapters/{chapter_num}", response_model=BookChapterRead, status_code=status.HTTP_200_OK)
async def get_book_chapter(
    book_id: uuid.UUID,
    chapter_num: int,
    chapter_repo: BookChapterRepository = Depends(get_book_chapter_repo),
    log_repo: LogRepository = Depends(get_log_repo),
    current_user = Depends(require_auth),
):
    """
    Получить конкретную главу книги по (book_id, chapter_num).
    """
    try:
        chapter = await chapter_repo.ensure_exists_by_book_and_number(
            book_id=book_id,
            chapter_num=chapter_num,
        )
    except BookChapterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chapter not found",
        )

    await log_repo.log_from_dto(
        LogCreate(
            user_id=current_user.id,
            action="get_chapter",
            entity="book_chapters",
            entity_id=chapter.id,  # id записи главы
            details=f"Пользователь запросил главу #{chapter_num} книги #{book_id}",
        )
    )

    # явная конвертация ORM → Pydantic

    return BookChapterRead.model_validate(chapter, from_attributes=True)

@router.get("/chapters/read",response_model=list[int], status_code=status.HTTP_200_OK)
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

    # Загружаем главы
    chapters = await chapter_repo.get_chapters_numbers_by_ids(chapter_ids)
    print(chapter_ids)

    return chapters


@router.get("/{book_id}/chapters/read/count")
async def get_read_chapters_count(
    book_id: uuid.UUID,
    current_user = Depends(require_auth),
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
async def get_read_chapters_count(
    book_id: uuid.UUID,
    current_user = Depends(require_auth),
    log_repo: LogRepository = Depends(get_log_repo)
):
    await log_repo.clear_read_history_for_user_and_book(
        user_id=current_user.id,
        book_id=book_id, )
    return
