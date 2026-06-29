import inspect
import uuid

import pytest
import pytest_asyncio

from api_manager_books.db.Repository.BookChapterRepository.ORM import BookChapter
from api_manager_books.db.Repository.BookRepository.ORM import Book
from api_manager_books.db.Repository.LogRepository.log_repository import LogRepository
from api_manager_books.db.Repository.UserRepository.ORM import User
from api_manager_books.schemas.logs import LogCreate

# ----------------------------------------------------------------------

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def log_repo(repository_session) -> LogRepository:
    """Готовит репозиторий логов."""
    return LogRepository(repository_session)


# ---------- ТЕСТЫ ДЛЯ LogRepository ----------

class TestLogRepository:

    """Проверяет репозиторий логов."""
    async def test_log_action_and_get_by_id(self, log_repo: LogRepository):
        """Проверяет логирование и получение по ID."""
        entity_id = uuid.uuid4()
        entry = await log_repo.log_action(
            user_id=None,
            action="create",
            entity="books",
            entity_id=entity_id,
            details=f"Создана книга #{entity_id}",
        )

        assert entry.id is not None
        assert entry.action == "create"
        assert entry.entity == "books"
        assert entry.entity_id == entity_id
        assert entry.details == f"Создана книга #{entity_id}"
        assert entry.created_at is not None

        fetched = await log_repo.get_by_id(entry.id)
        assert fetched is not None
        assert fetched.id == entry.id
        assert fetched.action == "create"

    async def test_log_action_rejects_non_uuid_entity_id_without_breaking_session(
        self,
        log_repo: LogRepository,
    ):
        """Проверяет сохранение рабочей сессии после ошибки."""
        with pytest.raises(TypeError, match="entity_id"):
            await log_repo.log_action(
                user_id=None,
                action="create",
                entity="books",
                entity_id=42,
                details="Некорректный идентификатор сущности",
            )

        valid_entity_id = uuid.uuid4()
        entry = await log_repo.log_action(
            user_id=None,
            action="create",
            entity="books",
            entity_id=valid_entity_id,
            details="Сессия пригодна после ошибки валидации",
        )

        assert entry.entity_id == valid_entity_id

    async def test_log_from_dto(self, log_repo: LogRepository):
        """Проверяет запись лога из DTO."""
        entity_id = uuid.uuid4()
        data = LogCreate(
            user_id=None,
            action="update",
            entity="users",
            entity_id=entity_id,
            details=f"Изменён пользователь #{entity_id}",
        )

        entry = await log_repo.log_from_dto(data)
        assert entry.id is not None
        assert entry.action == "update"
        assert entry.entity == "users"
        assert entry.entity_id == entity_id
        assert entry.details == f"Изменён пользователь #{entity_id}"

    async def test_list_logs_with_filters(self, log_repo: LogRepository):
        """Проверяет список с фильтрами."""
        book_1_id = uuid.uuid4()
        book_2_id = uuid.uuid4()
        user_id = uuid.uuid4()

        # создаём несколько логов разных типов
        await log_repo.log_action(
            user_id=None,
            action="create",
            entity="books",
            entity_id=book_1_id,
            details="create book 1",
        )
        await log_repo.log_action(
            user_id=None,
            action="update",
            entity="books",
            entity_id=book_1_id,
            details="update book 1",
        )
        await log_repo.log_action(
            user_id=None,
            action="delete",
            entity="books",
            entity_id=book_2_id,
            details="delete book 2",
        )
        await log_repo.log_action(
            user_id=None,
            action="create",
            entity="users",
            entity_id=user_id,
            details="create user 5",
        )

        # все логи
        all_logs = await log_repo.list_logs()
        assert len(all_logs) == 4

        # фильтр по action=create
        creates = await log_repo.list_logs(action="create")
        assert {log_entry.action for log_entry in creates} == {"create"}
        assert len(creates) == 2

        # фильтр по entity=books
        books_logs = await log_repo.list_logs(entity="books")
        assert {log_entry.entity for log_entry in books_logs} == {"books"}
        assert len(books_logs) == 3

        # фильтр по entity_id
        book1_logs = await log_repo.list_logs(entity="books", entity_id=book_1_id)
        assert len(book1_logs) == 2
        assert {log_entry.action for log_entry in book1_logs} == {"create", "update"}

    async def test_list_logs_time_range(self, log_repo: LogRepository):
        """Проверяет фильтрацию логов по времени."""
        entity_id = uuid.uuid4()

        # создаём логи
        await log_repo.log_action(
            user_id=None,
            action="create",
            entity="books",
            entity_id=entity_id,
            details="log 1",
        )
        await log_repo.log_action(
            user_id=None,
            action="update",
            entity="books",
            entity_id=entity_id,
            details="log 2",
        )

        # берём реальные created_at из БД
        all_logs = await log_repo.list_logs(entity="books", entity_id=entity_id)
        assert len(all_logs) >= 2

        oldest = min(log_entry.created_at for log_entry in all_logs)
        newest = max(log_entry.created_at for log_entry in all_logs)

        # окно, которое точно включает эти логи
        from datetime import timedelta
        window_start = oldest - timedelta(seconds=1)
        window_end = newest + timedelta(seconds=1)

        logs_in_range = await log_repo.list_logs(
            created_after=window_start,
            created_before=window_end,
        )
        assert len(logs_in_range) >= 2

        # окно строго после всех логов — должно быть пусто
        after_all = newest + timedelta(seconds=10)
        logs_after = await log_repo.list_logs(created_after=after_all)
        assert len(logs_after) == 0

        # окно строго до всех логов — тоже пусто
        before_all = oldest - timedelta(seconds=10)
        logs_before = await log_repo.list_logs(created_before=before_all)
        assert len(logs_before) == 0

    async def test_delete_older_than(self, log_repo: LogRepository):
        # создаём несколько логов
        """Проверяет удаление старых логов."""
        for i in range(3):
            await log_repo.log_action(
                user_id=None,
                action="create",
                entity="books",
                entity_id=uuid.uuid4(),
                details=f"log {i}",
            )

        all_logs = await log_repo.list_logs()
        assert len(all_logs) >= 3

        newest = max(log_entry.created_at for log_entry in all_logs)

        from datetime import timedelta
        # порог в будущем относительно всех текущих логов — должны удалиться все
        threshold = newest + timedelta(seconds=10)

        deleted_all = await log_repo.delete_older_than(threshold)
        assert deleted_all >= 3

        remaining = await log_repo.list_logs()
        assert len(remaining) == 0

    async def test_delete_older_than_does_not_collect_deleted_ids(self):
        """Проверяет, что очистка старых логов не собирает все id в память."""
        source = inspect.getsource(LogRepository.delete_older_than)

        assert ".returning(" not in source
        assert ".scalars().all()" not in source
        assert "func.count" in source

    async def test_clear_read_history_counts_deleted_rows_without_collecting_ids(
        self,
        repository_session,
        log_repo: LogRepository,
    ):
        """Проверяет счетчик очистки истории чтения и лог операции."""
        user = User(
            email="reader-history@example.com",
            password_hash=b"hash",
            role="user",
        )
        book = Book(title="History Book", author="Author")
        chapter_1 = BookChapter(book=book, chapter=1, description="One")
        chapter_2 = BookChapter(book=book, chapter=2, description="Two")
        repository_session.add_all([user, book])
        await repository_session.flush()

        await log_repo.log_action(
            user_id=user.id,
            action="get_chapter",
            entity="book_chapters",
            entity_id=chapter_1.id,
            details="read 1",
        )
        await log_repo.log_action(
            user_id=user.id,
            action="get_chapter",
            entity="book_chapters",
            entity_id=chapter_2.id,
            details="read 2",
        )

        await log_repo.clear_read_history_for_user_and_book(
            user_id=user.id,
            book_id=book.id,
        )

        logs = await log_repo.list_logs(action="clear_read_history", entity="books")
        assert len(logs) == 1
        assert "удалено 2 записей" in logs[0].details

    async def test_clear_read_history_does_not_collect_deleted_ids(self):
        """Проверяет, что очистка истории чтения не собирает все удаленные id."""
        source = inspect.getsource(LogRepository.clear_read_history_for_user_and_book)

        assert ".returning(" not in source
        assert ".scalars().all()" not in source
        assert "func.count" in source
