import uuid

import pytest

from api_manager_books.application.services.favorite_service import FavoriteService
from api_manager_books.db.Repository.BookRepository.book_repository import BookNotFoundError


class FakeBookRepo:
    """Тестовый репозиторий книг."""
    def __init__(self, *, exists: bool = True):
        """Инициализирует тестовый объект."""
        self.exists = exists
        self.calls: list[uuid.UUID] = []

    async def ensure_exists(self, book_id: uuid.UUID) -> None:
        """Имитирует проверку существования записи."""
        self.calls.append(book_id)
        if not self.exists:
            raise BookNotFoundError


class FakeFavoriteBookRepo:
    """Тестовый репозиторий избранных книг."""
    def __init__(self, *, add_result: bool = False, remove_result: bool = False):
        """Инициализирует тестовый объект."""
        self.add_result = add_result
        self.remove_result = remove_result
        self.add_calls: list[tuple[uuid.UUID, uuid.UUID]] = []
        self.remove_calls: list[tuple[uuid.UUID, uuid.UUID]] = []

    async def add_favorite(self, user_id: uuid.UUID, book_id: uuid.UUID) -> bool:
        """Имитирует добавление книги в избранное."""
        self.add_calls.append((user_id, book_id))
        return self.add_result

    async def remove_favorite(self, user_id: uuid.UUID, book_id: uuid.UUID) -> bool:
        """Имитирует удаление книги из избранного."""
        self.remove_calls.append((user_id, book_id))
        return self.remove_result


class FakeLogRepo:
    """Тестовый репозиторий логов."""
    def __init__(self):
        """Инициализирует тестовый объект."""
        self.entries = []

    async def log_from_dto(self, payload) -> None:
        """Сохраняет тестовую запись лога."""
        self.entries.append(payload)


@pytest.mark.asyncio
async def test_favorite_book_logs_only_when_favorite_is_added():
    """Проверяет лог только при добавлении в избранное."""
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    book_repo = FakeBookRepo()
    favorite_book_repo = FakeFavoriteBookRepo(add_result=True)
    log_repo = FakeLogRepo()
    service = FavoriteService(book_repo, favorite_book_repo, log_repo)

    result = await service.favorite_book(user_id, book_id)

    assert result is None
    assert book_repo.calls == [book_id]
    assert favorite_book_repo.add_calls == [(user_id, book_id)]
    assert log_repo.entries[0].user_id == user_id
    assert log_repo.entries[0].action == "favorite_book"
    assert log_repo.entries[0].entity == "books"
    assert log_repo.entries[0].entity_id == book_id
    assert log_repo.entries[0].details == f"Книга с id={book_id} добавлена в избранное"


@pytest.mark.asyncio
async def test_favorite_book_does_not_log_when_favorite_already_exists():
    """Проверяет отсутствие лога для уже избранной книги."""
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    log_repo = FakeLogRepo()
    service = FavoriteService(
        FakeBookRepo(),
        FakeFavoriteBookRepo(add_result=False),
        log_repo,
    )

    result = await service.favorite_book(user_id, book_id)

    assert result is None
    assert log_repo.entries == []


@pytest.mark.asyncio
async def test_unfavorite_book_logs_only_when_favorite_is_removed():
    """Проверяет лог только при удалении из избранного."""
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    book_repo = FakeBookRepo()
    favorite_book_repo = FakeFavoriteBookRepo(remove_result=True)
    log_repo = FakeLogRepo()
    service = FavoriteService(book_repo, favorite_book_repo, log_repo)

    result = await service.unfavorite_book(user_id, book_id)

    assert result is None
    assert book_repo.calls == [book_id]
    assert favorite_book_repo.remove_calls == [(user_id, book_id)]
    assert log_repo.entries[0].user_id == user_id
    assert log_repo.entries[0].action == "unfavorite_book"
    assert log_repo.entries[0].entity == "books"
    assert log_repo.entries[0].entity_id == book_id
    assert log_repo.entries[0].details == f"Книга с id={book_id} удалена из избранного"


@pytest.mark.asyncio
async def test_unfavorite_book_does_not_log_when_favorite_does_not_exist():
    """Проверяет отсутствие лога для отсутствующего избранного."""
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    log_repo = FakeLogRepo()
    favorite_book_repo = FakeFavoriteBookRepo(remove_result=False)
    service = FavoriteService(FakeBookRepo(), favorite_book_repo, log_repo)

    result = await service.unfavorite_book(user_id, book_id)

    assert result is None
    assert favorite_book_repo.remove_calls == [(user_id, book_id)]
    assert log_repo.entries == []


@pytest.mark.asyncio
async def test_book_not_found_error_is_propagated_without_favorite_or_log_calls():
    """Проверяет проброс ошибки книги без избранного и лога."""
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    favorite_book_repo = FakeFavoriteBookRepo(add_result=True)
    log_repo = FakeLogRepo()
    service = FavoriteService(
        FakeBookRepo(exists=False),
        favorite_book_repo,
        log_repo,
    )

    with pytest.raises(BookNotFoundError):
        await service.favorite_book(user_id, book_id)

    assert favorite_book_repo.add_calls == []
    assert favorite_book_repo.remove_calls == []
    assert log_repo.entries == []
