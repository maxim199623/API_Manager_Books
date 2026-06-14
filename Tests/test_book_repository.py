from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio

from src.core.config import SettingsManager
from src.DB.Manager.manager import AsyncDBManager
from src.DB.base import Base

from src.DB.Repository.BookRepository.book_repository import BookRepository, BookNotFoundError
from src.DB.Repository.BookRepository.Shems import BookCreate, BookUpdate

pytestmark = pytest.mark.asyncio

# ---------- Фикстуры конфигурации ----------

@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Путь к временному config.ini для этого набора тестов."""
    return tmp_path / "config.ini"


@pytest.fixture
def settings_manager(config_path: Path, tmp_path: Path) -> SettingsManager:
    """
    SettingsManager, который:
    - создаёт config.ini, если его нет;
    - выставляет sqlite на временный файл;
    """
    manager = SettingsManager(config_path)

    # отдельная sqlite-бд для тестов
    db_file = tmp_path / "test_books_repo.db"
    manager.set_sqlite_path(str(db_file))
    manager.set_echo(False)
    manager.postgres.user = "admin"
    manager.postgres.password = "admin"
    manager.postgres.name = "test_db"
    manager.save()

    return manager


# ---------- Фикстура AsyncDBManager с параметром backend ----------

@pytest_asyncio.fixture(params=["sqlite", "postgres"], scope="function")
async def async_db_manager(
    request: pytest.FixtureRequest,
    settings_manager: SettingsManager,
) -> AsyncIterator[AsyncDBManager]:
    """
    Создаёт AsyncDBManager для sqlite и postgres.
    Для postgres, если ping() не проходит — скипает тесты для этого backend.
    """
    backend = request.param

    # переключаем backend
    settings_manager.set_backend(backend)
    settings_manager.save()

    db_manager = AsyncDBManager(settings_manager.db, Base)

    # проверяем доступность
    ok = await db_manager.ping()
    if not ok:
        await db_manager.dispose()
        pytest.skip(f"{backend} is not available, skipping tests for this backend")

    # создаём схему (books и остальные модели, если есть)
    await db_manager.create_schema()

    try:
        yield db_manager
    finally:
        # можно подчистить схему после тестов
        await db_manager.drop_schema()
        await db_manager.dispose()


# ---------- Фикстура сессии ----------

@pytest_asyncio.fixture
async def session(async_db_manager: AsyncDBManager):
    async with async_db_manager.session() as s:
        yield s


# ---------- Фикстура репозитория ----------

@pytest_asyncio.fixture
async def book_repo(session) -> BookRepository:
    return BookRepository(session)


# ---------- ТЕСТЫ ДЛЯ BookRepository ----------

class TestBookRepository:

    async def test_create_and_get_by_id(self, book_repo: BookRepository):
        cover_bytes = b"\x01\x02\x03"
        file_bytes = b"FAKE_BOOK_DATA"

        created = await book_repo.create_book(
            BookCreate(
                cover=cover_bytes,
                title="Test Book",
                author="Author A",
                description="Desc",
                series="Series X",
                format="pdf",
                file=file_bytes,
            )
        )

        assert created.id is not None
        assert created.title == "Test Book"
        assert created.author == "Author A"
        assert created.description == "Desc"
        assert created.series == "Series X"
        assert created.format == "pdf"
        assert created.cover_size == len(cover_bytes)
        assert created.file_size == len(file_bytes)

        fetched = await book_repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.cover_size == len(cover_bytes)
        assert fetched.file_size == len(file_bytes)
        assert await book_repo.get_cover_bytes(created.id) == cover_bytes
        assert await book_repo.get_file_bytes(created.id) == file_bytes

    async def test_get_by_author_and_series(self, book_repo: BookRepository):
        # создаём несколько книг разных авторов и серий
        books_data = [
            BookCreate(
                cover=None,
                title="Book 1",
                author="Author A",
                description=None,
                series="Series 1",
                format="epub",
                file=None,
            ),
            BookCreate(
                cover=None,
                title="Book 2",
                author="Author A",
                description=None,
                series="Series 2",
                format="pdf",
                file=None,
            ),
            BookCreate(
                cover=None,
                title="Book 3",
                author="Author B",
                description=None,
                series="Series 1",
                format="mobi",
                file=None,
            ),
            BookCreate(
                cover=None,
                title="Тест 1",
                author="Автор 1",
                description=None,
                series="Серия 1",
                format="ebub",
                file=None,
            ),
        ]

        for data in books_data:
            await book_repo.create_book(data)

        # книги автора Author A
        by_author_a = await book_repo.get_by_author("Author A")
        titles_a = {b.title for b in by_author_a}
        assert titles_a == {"Book 1", "Book 2"}

        # книги серии Series 1
        by_series_1 = await book_repo.get_by_series("Series 1")
        titles_s1 = {b.title for b in by_series_1}
        assert titles_s1 == {"Book 1", "Book 3"}

    async def test_list_books_with_filters(self, book_repo: BookRepository):
        books_data = [
            BookCreate(
                cover=None,
                title="Book A1",
                author="Author A",
                description=None,
                series="S1",
                format="pdf",
                file=None,
            ),
            BookCreate(
                cover=None,
                title="Book A2",
                author="Author A",
                description=None,
                series="S2",
                format="epub",
                file=None,
            ),
            BookCreate(
                cover=None,
                title="Book B1",
                author="Author B",
                description=None,
                series="S1",
                format="epub",
                file=None,
            ),
        ]
        for data in books_data:
            await book_repo.create_book(data)

        # все книги
        all_books = await book_repo.list_books()
        assert len(all_books) == 3

        # фильтр по автору
        a_books = await book_repo.list_books(author="Author A")
        assert {b.title for b in a_books} == {"Book A1", "Book A2"}

        # фильтр по серии
        s1_books = await book_repo.list_books(series="S1")
        assert {b.title for b in s1_books} == {"Book A1", "Book B1"}

    async def test_list_books_sorts_by_title(self, book_repo: BookRepository):
        for title in ["Gamma", "Alpha", "Beta"]:
            await book_repo.create_book(
                BookCreate(
                    cover=None,
                    title=title,
                    author=None,
                    description=None,
                    series=None,
                    format="epub",
                    file=None,
                )
            )

        asc_books = await book_repo.list_books(sort_by="title", sort_dir="asc")
        desc_books = await book_repo.list_books(sort_by="title", sort_dir="desc")

        assert [book.title for book in asc_books] == ["Alpha", "Beta", "Gamma"]
        assert [book.title for book in desc_books] == ["Gamma", "Beta", "Alpha"]

    async def test_list_books_sorts_by_created_at(
        self,
        book_repo: BookRepository,
        session,
    ):
        older = await book_repo.create_book(
            BookCreate(
                cover=None,
                title="Older",
                author=None,
                description=None,
                series=None,
                format="epub",
                file=None,
            )
        )
        newer = await book_repo.create_book(
            BookCreate(
                cover=None,
                title="Newer",
                author=None,
                description=None,
                series=None,
                format="epub",
                file=None,
            )
        )

        from datetime import datetime, timedelta, timezone

        base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        older.created_at = base_time
        newer.created_at = base_time + timedelta(days=1)
        await session.flush()

        asc_books = await book_repo.list_books(sort_by="created_at", sort_dir="asc")
        desc_books = await book_repo.list_books(sort_by="created_at", sort_dir="desc")

        assert [book.title for book in asc_books] == ["Older", "Newer"]
        assert [book.title for book in desc_books] == ["Newer", "Older"]

    async def test_delete_book(self, book_repo: BookRepository):
        book = await book_repo.create_book(
            BookCreate(
                cover=None,
                title="To Delete",
                author="X",
                description=None,
                series=None,
                format=None,
                file=None,
            )
        )

        deleted = await book_repo.delete_book(book.id)
        assert deleted is True

        # повторное удаление — уже False
        deleted_again = await book_repo.delete_book(book.id)
        assert deleted_again is False

        # и в БД её больше нет
        assert await book_repo.get_by_id(book.id) is None

    async def test_ensure_exists_success(self, book_repo: BookRepository):
        book = await book_repo.create_book(
            BookCreate(
                cover=None,
                title="Exists",
                author="Y",
                description=None,
                series=None,
                format=None,
                file=None,
            )
        )
        found = await book_repo.ensure_exists(book.id)
        assert found.id == book.id

    async def test_ensure_exists_not_found(self, book_repo: BookRepository):
        with pytest.raises(BookNotFoundError):
            await book_repo.ensure_exists(999999)

    async def test_update_book_partial(self, book_repo: BookRepository):
        cover_bytes = b"\x10\x20"
        file_bytes = b"DATA1"

        book = await book_repo.create_book(
            BookCreate(
                cover=cover_bytes,
                title="Old Title",
                author="Old Author",
                description="Old Desc",
                series="Old Series",
                format="oldfmt",
                file=file_bytes,
            )
        )

        # обновляем только часть полей
        new_cover = b"\xAA\xBB\xCC"
        new_file = b"DATA2"

        updated = await book_repo.update_book(
            book.id,
            BookUpdate(
                title="New Title",
                description="New Desc",
                cover=new_cover,
                file=new_file,
            ),
        )

        assert updated.id == book.id
        assert updated.title == "New Title"
        assert updated.description == "New Desc"
        assert updated.cover_size == len(new_cover)
        assert updated.file_size == len(new_file)
        # не трогаемые поля должны остаться прежними
        assert updated.author == "Old Author"
        assert updated.series == "Old Series"
        assert updated.format == "oldfmt"

        # перепроверяем из БД
        fetched = await book_repo.get_by_id(book.id)
        assert fetched is not None
        assert fetched.title == "New Title"
        assert fetched.description == "New Desc"
        assert fetched.cover_size == len(new_cover)
        assert fetched.file_size == len(new_file)
        assert await book_repo.get_cover_bytes(book.id) == new_cover
        assert await book_repo.get_file_bytes(book.id) == new_file
        assert fetched.author == "Old Author"
        assert fetched.series == "Old Series"
        assert fetched.format == "oldfmt"

    async def test_update_book_replaces_binary_data_from_chunk_iterables(self, book_repo: BookRepository):
        book = await book_repo.create_book(
            BookCreate(
                cover=b"old-cover",
                title="Chunk Update",
                author="Author Z",
                description=None,
                series=None,
                format="epub",
                file=b"old-file",
            )
        )

        async def iter_chunks(*chunks: bytes):
            for chunk in chunks:
                yield chunk

        updated = await book_repo.update_book(
            book.id,
            BookUpdate(
                cover_mime="image/webp",
                file_name="chunked.epub",
                file_mime="application/epub+zip",
            ),
            cover_chunks=iter_chunks(b"new-", b"cover"),
            file_chunks=iter_chunks(b"chunk", b"ed-", b"file"),
        )

        assert updated.cover_size == len(b"new-cover")
        assert updated.cover_mime == "image/webp"
        assert updated.file_size == len(b"chunked-file")
        assert updated.file_name == "chunked.epub"
        assert updated.file_mime == "application/epub+zip"
        assert await book_repo.get_cover_bytes(book.id) == b"new-cover"
        assert await book_repo.get_file_bytes(book.id) == b"chunked-file"
