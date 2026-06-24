import uuid
from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace

import pytest

from api_manager_books.application.services.book_service import (
    BookAlreadyExistsError,
    BookNotFoundInServiceError,
    BookService,
)
from api_manager_books.db.Repository.BookRepository.book_repository import BookNotFoundError
from api_manager_books.schemas.books import BookCreate, BookMetadataUpdate


@dataclass
class FakeBook:
    """Тестовая модель книги."""
    id: uuid.UUID
    title: str
    author: str | None = None
    description: str | None = None
    series: str | None = None
    genres: str | None = None
    format: str | None = "epub"
    created_at: datetime = datetime.now()


class FakeBookRepo:
    """Тестовый репозиторий книг."""
    def __init__(
        self,
        *,
        existing_book=None,
        created_book=None,
        listed_books=None,
        updated_book=None,
        update_error: Exception | None = None,
        delete_result: bool = True,
    ):
        """Инициализирует тестовый объект."""
        self.existing_book = existing_book
        self.created_book = created_book
        self.listed_books = listed_books or []
        self.updated_book = updated_book
        self.update_error = update_error
        self.delete_result = delete_result
        self.duplicate_checks: list[tuple[str, str | None]] = []
        self.create_calls = []
        self.list_calls = []
        self.update_calls = []
        self.delete_calls: list[uuid.UUID] = []

    async def get_by_title_author(self, title: str, author: str | None):
        """Имитирует поиск книги по названию и автору."""
        self.duplicate_checks.append((title, author))
        return self.existing_book

    async def create_book(self, payload, *, cover_chunks=None, file_chunks=None):
        """Имитирует создание книги."""
        cover_data = [chunk async for chunk in cover_chunks] if cover_chunks is not None else None
        file_data = [chunk async for chunk in file_chunks] if file_chunks is not None else None
        self.create_calls.append((payload, cover_data, file_data))
        return self.created_book

    async def list_books(
        self,
        *,
        author,
        series,
        offset,
        limit,
        sort_by,
        sort_dir,
        user_id,
    ):
        """Имитирует получение списка книг."""
        self.list_calls.append(
            {
                "author": author,
                "series": series,
                "offset": offset,
                "limit": limit,
                "sort_by": sort_by,
                "sort_dir": sort_dir,
                "user_id": user_id,
            }
        )
        return self.listed_books

    async def update_book(self, book_id, payload):
        """Имитирует обновление книги."""
        self.update_calls.append((book_id, payload))
        if self.update_error is not None:
            raise self.update_error
        return self.updated_book

    async def delete_book(self, book_id):
        """Имитирует удаление книги."""
        self.delete_calls.append(book_id)
        return self.delete_result


class FakeFavoriteBookRepo:
    """Тестовый репозиторий избранных книг."""
    def __init__(self, favorite_ids: set[uuid.UUID] | None = None):
        """Инициализирует тестовый объект."""
        self.favorite_ids = favorite_ids or set()
        self.calls: list[tuple[uuid.UUID, list[uuid.UUID]]] = []

    async def list_favorite_book_ids(self, user_id: uuid.UUID, book_ids: list[uuid.UUID]):
        """Имитирует получение избранных книг пользователя."""
        self.calls.append((user_id, book_ids))
        return self.favorite_ids


class FakeLogRepo:
    """Тестовый репозиторий логов."""
    def __init__(self):
        """Инициализирует тестовый объект."""
        self.entries = []
        self.actions = []

    async def log_from_dto(self, payload):
        """Сохраняет тестовую запись лога."""
        self.entries.append(payload)

    async def log_action(self, **kwargs):
        """Сохраняет тестовое действие лога."""
        self.actions.append(kwargs)


class FakeNotificationManager:
    """Тестовый менеджер уведомлений."""
    def __init__(self):
        """Инициализирует тестовый объект."""
        self.messages = []

    async def broadcast(self, message):
        """Сохраняет тестовое широковещательное уведомление."""
        self.messages.append(message)


async def iter_chunks(chunks: list[bytes]):
    """Возвращает тестовый поток чанков."""
    for chunk in chunks:
        yield chunk


def make_service(
    book_repo: FakeBookRepo,
    favorite_repo: FakeFavoriteBookRepo | None = None,
    log_repo: FakeLogRepo | None = None,
    notification_manager: FakeNotificationManager | None = None,
) -> BookService:
    """Создает сервис с тестовыми зависимостями."""
    return BookService(
        book_repo=book_repo,
        favorite_book_repo=favorite_repo or FakeFavoriteBookRepo(),
        log_repo=log_repo or FakeLogRepo(),
        notification_manager=notification_manager or FakeNotificationManager(),
    )


@pytest.mark.asyncio
async def test_add_book_rejects_duplicate_without_create_log_or_notification():
    """Проверяет отказ от дубликата без побочных действий."""
    payload = BookCreate(title="Existing", author="Author")
    book_repo = FakeBookRepo(existing_book=SimpleNamespace(id=uuid.uuid4()))
    log_repo = FakeLogRepo()
    notification_manager = FakeNotificationManager()
    service = make_service(book_repo, log_repo=log_repo, notification_manager=notification_manager)

    with pytest.raises(BookAlreadyExistsError):
        await service.add_book(uuid.uuid4(), payload)

    assert book_repo.duplicate_checks == [("Existing", "Author")]
    assert book_repo.create_calls == []
    assert log_repo.entries == []
    assert notification_manager.messages == []


@pytest.mark.asyncio
async def test_add_book_creates_book_logs_and_broadcasts_notification():
    """Проверяет создание книги, лог и уведомление."""
    user_id = uuid.uuid4()
    created_book = FakeBook(id=uuid.uuid4(), title="New Book", author="Author")
    book_repo = FakeBookRepo(created_book=created_book)
    log_repo = FakeLogRepo()
    notification_manager = FakeNotificationManager()
    service = make_service(book_repo, log_repo=log_repo, notification_manager=notification_manager)
    payload = BookCreate(title="New Book", author="Author", cover_mime="image/webp")

    result = await service.add_book(
        user_id,
        payload,
        cover_chunks=iter_chunks([b"cover"]),
        file_chunks=iter_chunks([b"file-1", b"file-2"]),
    )

    assert result == created_book.id
    created_payload, cover_chunks, file_chunks = book_repo.create_calls[0]
    assert created_payload is payload
    assert cover_chunks == [b"cover"]
    assert file_chunks == [b"file-1", b"file-2"]
    assert log_repo.entries[0].user_id == user_id
    assert log_repo.entries[0].action == "add_book"
    assert log_repo.entries[0].entity == "books"
    assert log_repo.entries[0].entity_id == created_book.id
    assert notification_manager.messages == [
        {"type": "new_book", "title": "Добавлена книга 'New Book'"}
    ]


@pytest.mark.asyncio
async def test_list_books_marks_favorites():
    """Проверяет отметку избранных книг в списке."""
    user_id = uuid.uuid4()
    favorite_book = FakeBook(id=uuid.uuid4(), title="Favorite")
    regular_book = FakeBook(id=uuid.uuid4(), title="Regular")
    book_repo = FakeBookRepo(listed_books=[favorite_book, regular_book])
    favorite_repo = FakeFavoriteBookRepo({favorite_book.id})
    service = make_service(book_repo, favorite_repo=favorite_repo)

    result = await service.list_books(
        user_id=user_id,
        author="Author",
        series="Series",
        offset=5,
        limit=10,
        sort_by="title",
        sort_dir="asc",
    )

    assert [book.id for book in result] == [favorite_book.id, regular_book.id]
    assert [book.is_favorite for book in result] == [True, False]
    assert book_repo.list_calls == [
        {
            "author": "Author",
            "series": "Series",
            "offset": 5,
            "limit": 10,
            "sort_by": "title",
            "sort_dir": "asc",
            "user_id": user_id,
        }
    ]
    assert favorite_repo.calls == [(user_id, [favorite_book.id, regular_book.id])]


@pytest.mark.asyncio
async def test_update_metadata_converts_repository_not_found_to_service_error_without_log():
    """Проверяет преобразование ошибки репозитория без лога."""
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    book_repo = FakeBookRepo(update_error=BookNotFoundError())
    log_repo = FakeLogRepo()
    service = make_service(book_repo, log_repo=log_repo)

    with pytest.raises(BookNotFoundInServiceError):
        await service.update_metadata(user_id, book_id, BookMetadataUpdate(title="Missing"))

    assert book_repo.update_calls[0][0] == book_id
    assert log_repo.entries == []


@pytest.mark.asyncio
async def test_delete_book_raises_service_not_found_without_log_or_notification_when_repository_returns_false():
    """Проверяет ошибку удаления без лога и уведомления."""
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    book_repo = FakeBookRepo(delete_result=False)
    log_repo = FakeLogRepo()
    notification_manager = FakeNotificationManager()
    service = make_service(book_repo, log_repo=log_repo, notification_manager=notification_manager)

    with pytest.raises(BookNotFoundInServiceError):
        await service.delete_book(user_id, book_id)

    assert book_repo.delete_calls == [book_id]
    assert log_repo.actions == []
    assert notification_manager.messages == []


@pytest.mark.asyncio
async def test_delete_book_logs_and_broadcasts_notification_when_deleted():
    """Проверяет лог и уведомление после удаления книги."""
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    book_repo = FakeBookRepo(delete_result=True)
    log_repo = FakeLogRepo()
    notification_manager = FakeNotificationManager()
    service = make_service(book_repo, log_repo=log_repo, notification_manager=notification_manager)

    result = await service.delete_book(user_id, book_id)

    assert result is None
    assert log_repo.actions == [
        {
            "user_id": user_id,
            "action": "delete_book",
            "entity": "books",
            "entity_id": book_id,
            "details": f"Книга с id={book_id} была удалена",
        }
    ]
    assert notification_manager.messages == [{"type": "del_book"}]
