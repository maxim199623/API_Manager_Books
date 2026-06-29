import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from api_manager_books.application.services.chapter_service import (
    ChapterService,
    DuplicateChapterNumbersInRequestError,
    EmptyChapterListError,
)
from api_manager_books.db.Repository.BookChapterRepository.book_chapter_repository import BookChapterNotFoundError
from api_manager_books.db.Repository.BookRepository.book_repository import BookNotFoundError
from api_manager_books.schemas.book_chapters import BookChapterCreate, BookChapterUpdate


class FakeBookRepo:
    """Тестовый репозиторий книг."""
    def __init__(self, *, exists: bool = True):
        """Инициализирует тестовый объект."""
        self.exists = exists
        self.calls: list[uuid.UUID] = []

    async def ensure_exists(self, book_id: uuid.UUID):
        """Имитирует проверку существования записи."""
        self.calls.append(book_id)
        if not self.exists:
            raise BookNotFoundError
        return SimpleNamespace(id=book_id, title="Stored book")


class FakeChapterRepo:
    """Тестовый репозиторий глав."""
    def __init__(
        self,
        *,
        headers=None,
        count: int = 0,
        chapter=None,
        chapter_exists: bool = True,
        create_error: Exception | None = None,
        update_error: Exception | None = None,
    ):
        """Инициализирует тестовый объект."""
        self.headers = headers if headers is not None else []
        self.count = count
        self.chapter = chapter
        self.chapter_exists = chapter_exists
        self.create_error = create_error
        self.update_error = update_error
        self.header_calls: list[uuid.UUID] = []
        self.count_calls: list[uuid.UUID] = []
        self.chapter_calls: list[tuple[uuid.UUID, int]] = []
        self.create_calls = []
        self.update_calls = []

    async def list_chapter_headers(self, book_id: uuid.UUID):
        """Имитирует получение заголовков глав."""
        self.header_calls.append(book_id)
        return self.headers

    async def count_chapters(self, book_id: uuid.UUID) -> int:
        """Имитирует подсчет глав книги."""
        self.count_calls.append(book_id)
        return self.count

    async def ensure_exists_by_book_and_number(
        self,
        book_id: uuid.UUID,
        chapter_num: int,
    ):
        """Имитирует поиск главы по книге и номеру."""
        self.chapter_calls.append((book_id, chapter_num))
        if not self.chapter_exists:
            raise BookChapterNotFoundError
        return self.chapter

    async def create_chapters(self, book_id: uuid.UUID, data):
        """Имитирует создание глав книги."""
        self.create_calls.append((book_id, data))
        if self.create_error is not None:
            raise self.create_error
        return len(data)

    async def update_chapter_by_number(
        self,
        book_id: uuid.UUID,
        chapter_num: int,
        data,
    ):
        """Имитирует обновление главы по номеру."""
        self.update_calls.append((book_id, chapter_num, data))
        if self.update_error is not None:
            raise self.update_error
        return self.chapter


class FakeLogRepo:
    """Тестовый репозиторий логов."""
    def __init__(self):
        """Инициализирует тестовый объект."""
        self.entries = []

    async def log_from_dto(self, payload) -> None:
        """Сохраняет тестовую запись лога."""
        self.entries.append(payload)


class FakeReadingProgressRepo:
    """Тестовый репозиторий прогресса чтения."""

    def __init__(self):
        """Инициализирует тестовый объект."""
        self.calls = []

    async def mark_chapter_read(self, *, user_id, book_id, chapter_id):
        """Сохраняет тестовую отметку чтения."""
        self.calls.append(
            {
                "user_id": user_id,
                "book_id": book_id,
                "chapter_id": chapter_id,
            }
        )


def make_service(
    book_repo,
    chapter_repo,
    log_repo,
    progress_repo: FakeReadingProgressRepo | None = None,
) -> ChapterService:
    """Создает сервис с тестовыми зависимостями."""
    return ChapterService(
        book_repo=book_repo,
        chapter_repo=chapter_repo,
        log_repo=log_repo,
        reading_progress_repo=progress_repo or FakeReadingProgressRepo(),
    )


@pytest.mark.asyncio
async def test_list_chapter_headers_checks_book_and_returns_headers():
    """Проверяет заголовки глав после проверки книги."""
    book_id = uuid.uuid4()
    headers = [
        SimpleNamespace(chapter=1, chapter_name="Opening"),
        SimpleNamespace(chapter=2, chapter_name=None),
    ]
    book_repo = FakeBookRepo()
    chapter_repo = FakeChapterRepo(headers=headers)
    service = make_service(book_repo, chapter_repo, FakeLogRepo())

    result = await service.list_chapter_headers(book_id)

    assert result == headers
    assert book_repo.calls == [book_id]
    assert chapter_repo.header_calls == [book_id]


@pytest.mark.asyncio
async def test_list_chapter_headers_propagates_book_not_found_without_chapter_call():
    """Проверяет отсутствие вызова глав при пропавшей книге."""
    book_id = uuid.uuid4()
    chapter_repo = FakeChapterRepo(headers=[SimpleNamespace(chapter=1, chapter_name="Hidden")])
    service = make_service(FakeBookRepo(exists=False), chapter_repo, FakeLogRepo())

    with pytest.raises(BookNotFoundError):
        await service.list_chapter_headers(book_id)

    assert chapter_repo.header_calls == []


@pytest.mark.asyncio
async def test_count_chapters_checks_book_and_returns_book_id_with_count():
    """Проверяет подсчет глав после проверки книги."""
    book_id = uuid.uuid4()
    book_repo = FakeBookRepo()
    chapter_repo = FakeChapterRepo(count=7)
    service = make_service(book_repo, chapter_repo, FakeLogRepo())

    result = await service.count_chapters(book_id)

    assert result == (book_id, 7)
    assert book_repo.calls == [book_id]
    assert chapter_repo.count_calls == [book_id]


@pytest.mark.asyncio
async def test_get_chapter_returns_chapter_and_logs_reading():
    """Проверяет возврат главы и лог чтения."""
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    chapter_num = 3
    chapter = SimpleNamespace(
        id=uuid.uuid4(),
        book_id=book_id,
        chapter=chapter_num,
        chapter_name="Finale",
        description="Text",
        file=None,
        created_at=datetime.now(),
    )
    chapter_repo = FakeChapterRepo(chapter=chapter)
    log_repo = FakeLogRepo()
    progress_repo = FakeReadingProgressRepo()
    service = make_service(FakeBookRepo(), chapter_repo, log_repo, progress_repo)

    result = await service.get_chapter(user_id, book_id, chapter_num)

    assert result == chapter
    assert chapter_repo.chapter_calls == [(book_id, chapter_num)]
    assert progress_repo.calls == [
        {
            "user_id": user_id,
            "book_id": book_id,
            "chapter_id": chapter.id,
        }
    ]
    assert len(log_repo.entries) == 1
    assert log_repo.entries[0].user_id == user_id
    assert log_repo.entries[0].action == "get_chapter"
    assert log_repo.entries[0].entity == "book_chapters"
    assert log_repo.entries[0].entity_id == chapter.id
    assert (
        log_repo.entries[0].details
        == f"Пользователь запросил главу #{chapter_num} книги {book_id}"
    )


@pytest.mark.asyncio
async def test_get_chapter_propagates_chapter_not_found_without_log():
    """Проверяет отсутствие лога при пропавшей главе."""
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    chapter_repo = FakeChapterRepo(chapter_exists=False)
    log_repo = FakeLogRepo()
    progress_repo = FakeReadingProgressRepo()
    service = make_service(FakeBookRepo(), chapter_repo, log_repo, progress_repo)

    with pytest.raises(BookChapterNotFoundError):
        await service.get_chapter(user_id, book_id, 5)

    assert chapter_repo.chapter_calls == [(book_id, 5)]
    assert progress_repo.calls == []
    assert log_repo.entries == []


@pytest.mark.asyncio
async def test_add_chapters_creates_chapters_and_logs_operation():
    """Проверяет добавление глав и лог операции."""
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    chapters = [
        BookChapterCreate(chapter=1, chapter_name="Start", description="Text"),
        BookChapterCreate(chapter=2, chapter_name=None, description="More text"),
    ]
    book_repo = FakeBookRepo()
    chapter_repo = FakeChapterRepo()
    log_repo = FakeLogRepo()
    service = make_service(book_repo, chapter_repo, log_repo)

    result = await service.add_chapters(user_id, book_id, chapters)

    assert result is None
    assert book_repo.calls == [book_id]
    assert chapter_repo.create_calls == [(book_id, chapters)]
    assert len(log_repo.entries) == 1
    assert log_repo.entries[0].user_id == user_id
    assert log_repo.entries[0].action == "add_book_chapters"
    assert log_repo.entries[0].entity == "book_chapters"
    assert log_repo.entries[0].entity_id == book_id
    assert (
        log_repo.entries[0].details
        == f"Добавлено глав: 2 для книги 'Stored book' (id={book_id})"
    )


@pytest.mark.asyncio
async def test_add_chapters_rejects_empty_list_without_create_or_log():
    """Проверяет отказ от пустого списка глав."""
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    book_repo = FakeBookRepo()
    chapter_repo = FakeChapterRepo()
    log_repo = FakeLogRepo()
    service = make_service(book_repo, chapter_repo, log_repo)

    with pytest.raises(EmptyChapterListError):
        await service.add_chapters(user_id, book_id, [])

    assert book_repo.calls == [book_id]
    assert chapter_repo.create_calls == []
    assert log_repo.entries == []


@pytest.mark.asyncio
async def test_add_chapters_rejects_duplicate_chapter_numbers_without_create_or_log():
    """Проверяет отказ от дублей номеров глав."""
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    chapters = [
        BookChapterCreate(chapter=1, chapter_name="Start", description="Text"),
        BookChapterCreate(chapter=1, chapter_name="Again", description="More text"),
    ]
    book_repo = FakeBookRepo()
    chapter_repo = FakeChapterRepo()
    log_repo = FakeLogRepo()
    service = make_service(book_repo, chapter_repo, log_repo)

    with pytest.raises(DuplicateChapterNumbersInRequestError):
        await service.add_chapters(user_id, book_id, chapters)

    assert book_repo.calls == [book_id]
    assert chapter_repo.create_calls == []
    assert log_repo.entries == []


@pytest.mark.asyncio
async def test_add_chapters_propagates_book_not_found_without_create_or_log():
    """Проверяет ошибку пропавшей книги без создания глав."""
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    chapters = [
        BookChapterCreate(chapter=1, chapter_name="Start", description="Text"),
    ]
    chapter_repo = FakeChapterRepo()
    log_repo = FakeLogRepo()
    service = make_service(FakeBookRepo(exists=False), chapter_repo, log_repo)

    with pytest.raises(BookNotFoundError):
        await service.add_chapters(user_id, book_id, chapters)

    assert chapter_repo.create_calls == []
    assert log_repo.entries == []


@pytest.mark.asyncio
async def test_add_chapters_propagates_integrity_error_without_log():
    """Проверяет проброс ошибки целостности без лога."""
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    chapters = [
        BookChapterCreate(chapter=1, chapter_name="Start", description="Text"),
    ]
    error = IntegrityError("insert", {}, Exception("duplicate"))
    chapter_repo = FakeChapterRepo(create_error=error)
    log_repo = FakeLogRepo()
    service = make_service(FakeBookRepo(), chapter_repo, log_repo)

    with pytest.raises(IntegrityError):
        await service.add_chapters(user_id, book_id, chapters)

    assert chapter_repo.create_calls == [(book_id, chapters)]
    assert log_repo.entries == []


@pytest.mark.asyncio
async def test_update_chapter_updates_chapter_and_logs_operation():
    """Проверяет обновление главы и лог операции."""
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    chapter_num = 4
    payload = BookChapterUpdate(chapter_name="Updated")
    chapter = SimpleNamespace(id=uuid.uuid4())
    chapter_repo = FakeChapterRepo(chapter=chapter)
    log_repo = FakeLogRepo()
    service = make_service(FakeBookRepo(), chapter_repo, log_repo)

    result = await service.update_chapter(user_id, book_id, chapter_num, payload)

    assert result is None
    assert chapter_repo.update_calls == [(book_id, chapter_num, payload)]
    assert len(log_repo.entries) == 1
    assert log_repo.entries[0].user_id == user_id
    assert log_repo.entries[0].action == "update_chapter"
    assert log_repo.entries[0].entity == "book_chapters"
    assert log_repo.entries[0].entity_id == chapter.id
    assert (
        log_repo.entries[0].details
        == f"Обновлена глава #{chapter_num} книги #{book_id}"
    )


@pytest.mark.asyncio
async def test_update_chapter_propagates_chapter_not_found_without_log():
    """Проверяет отсутствие лога при ошибке обновления главы."""
    user_id = uuid.uuid4()
    book_id = uuid.uuid4()
    chapter_num = 4
    payload = BookChapterUpdate(description="Updated text")
    chapter_repo = FakeChapterRepo(update_error=BookChapterNotFoundError())
    log_repo = FakeLogRepo()
    service = make_service(FakeBookRepo(), chapter_repo, log_repo)

    with pytest.raises(BookChapterNotFoundError):
        await service.update_chapter(user_id, book_id, chapter_num, payload)

    assert chapter_repo.update_calls == [(book_id, chapter_num, payload)]
    assert log_repo.entries == []
