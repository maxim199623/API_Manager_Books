from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio

from src.core.config import SettingsManager
from src.DB.Manager.manager import AsyncDBManager
from src.DB.base import Base

from src.DB.Repository.BookRepository.ORM import Book

from src.DB.Repository.BookRepository.book_repository import BookRepository
from src.DB.Repository.BookRepository.Shems import BookCreate
from src.DB.Repository.BookChapterRepository.book_chapter_repository import BookChapterRepository, BookChapterNotFoundError
from src.DB.Repository.BookChapterRepository.Shems import BookChapterCreate, BookChapterUpdate


pytestmark = pytest.mark.asyncio


# ---------- Фикстуры конфигурации ----------

@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    return tmp_path / "config_chapters.ini"


@pytest.fixture
def settings_manager(config_path: Path, tmp_path: Path) -> SettingsManager:
    """
    SettingsManager:
    - создаёт config.ini, если его нет;
    - указывает отдельный sqlite-файл для тестов.
    """
    manager = SettingsManager(config_path)

    db_file = tmp_path / "test_chapters_repo.db"
    manager.set_sqlite_path(str(db_file))
    manager.set_echo(False)
    manager.postgres.user = "admin"
    manager.postgres.password = "admin"
    manager.postgres.name = "test_db"
    manager.save()

    return manager


# ---------- Фикстура AsyncDBManager c backend=["sqlite", "postgres"] ----------

@pytest_asyncio.fixture(params=["sqlite", "postgres"], scope="function")
async def async_db_manager(
    request: pytest.FixtureRequest,
    settings_manager: SettingsManager,
) -> AsyncIterator[AsyncDBManager]:
    """
    Создаёт AsyncDBManager для sqlite и postgres.
    Если postgres недоступен, тесты для него будут пропущены.
    """
    backend = request.param

    # переключаем backend
    settings_manager.set_backend(backend)
    settings_manager.save()

    db_manager = AsyncDBManager(settings_manager.db, Base)

    # проверяем доступность БД
    ok = await db_manager.ping()
    if not ok:
        await db_manager.dispose()
        pytest.skip(f"{backend} is not available, skipping tests for this backend")

    # создаём схему (books + book_chapters)
    await db_manager.create_schema()

    try:
        yield db_manager
    finally:
        await db_manager.drop_schema()
        await db_manager.dispose()


# ---------- Сессия и репозитории ----------

@pytest_asyncio.fixture
async def session(async_db_manager: AsyncDBManager):
    async with async_db_manager.session() as s:
        yield s


@pytest_asyncio.fixture
async def book_repo(session) -> BookRepository:
    return BookRepository(session)


@pytest_asyncio.fixture
async def chapter_repo(session) -> BookChapterRepository:
    return BookChapterRepository(session)


# ---------- Хелпер: создать книгу для теста ----------

async def _create_test_book(book_repo: BookRepository, title: str = "Test Book") -> Book:
    return await book_repo.create_book(
        BookCreate(
            cover=None,
            title=title,
            author="Author X",
            description="Some desc",
            series="Series Y",
            format="epub",
            file=None,
        )
    )


# ---------- ТЕСТЫ ----------

class TestBookChapterRepository:

    async def test_create_and_get_chapter_by_id_and_number(
        self,
        book_repo: BookRepository,
        chapter_repo: BookChapterRepository,
    ):
        book = await _create_test_book(book_repo, "Book 1")

        created = await chapter_repo.create_chapters(book_id=book.id, data=BookChapterCreate(
            chapter=1,
            description="Chapter one text",
        ))

        assert created.id is not None
        assert created.book_id == book.id
        assert created.chapter == 1
        assert created.description == "Chapter one text"

        # по id
        by_id = await chapter_repo.get_by_id(created.id)
        assert by_id is not None
        assert by_id.id == created.id

        # по (book_id, chapter)
        by_pair = await chapter_repo.get_by_book_and_number(book.id, 1)
        assert by_pair is not None
        assert by_pair.id == created.id

    async def test_list_and_count_chapters(
        self,
        book_repo: BookRepository,
        chapter_repo: BookChapterRepository,
    ):
        book = await _create_test_book(book_repo, "Book With Chapters")

        chapters_data = [
            BookChapterCreate(chapter=1, description="Text 1"),
            BookChapterCreate(chapter=2, description="Text 2"),
            BookChapterCreate(chapter=3, description="Text 3"),
        ]

        for data in chapters_data:
            await chapter_repo.create_chapters(book.id, data)

        all_chapters = await chapter_repo.list_chapters(book.id)
        assert len(all_chapters) == 3
        assert [c.chapter for c in all_chapters] == [1, 2, 3]

        count = await chapter_repo.count_chapters(book.id)
        assert count == 3

    async def test_update_chapter_by_number(
        self,
        book_repo: BookRepository,
        chapter_repo: BookChapterRepository,
    ):
        book = await _create_test_book(book_repo, "Updatable Book")

        await chapter_repo.create_chapters(book.id, BookChapterCreate(chapter=1, description="Old text"))

        updated = await chapter_repo.update_chapter_by_number(
            book.id,
            chapter_num=1,
            data=BookChapterUpdate(description="New text"),
        )

        assert updated.chapter == 1
        assert updated.description == "New text"

        fetched = await chapter_repo.get_by_book_and_number(book.id, 1)
        assert fetched is not None
        assert fetched.description == "New text"

    async def test_delete_chapter_by_number(
        self,
        book_repo: BookRepository,
        chapter_repo: BookChapterRepository,
    ):
        book = await _create_test_book(book_repo, "Delete Chapter Book")

        await chapter_repo.create_chapters(book.id, BookChapterCreate(chapter=1, description="Text 1"))
        await chapter_repo.create_chapters(book.id, BookChapterCreate(chapter=2, description="Text 2"))

        deleted = await chapter_repo.delete_chapter_by_number(book.id, 1)
        assert deleted is True

        # повторное удаление той же главы
        deleted_again = await chapter_repo.delete_chapter_by_number(book.id, 1)
        assert deleted_again is False

        chapters = await chapter_repo.list_chapters(book.id)
        assert len(chapters) == 1
        assert chapters[0].chapter == 2

    async def test_delete_all_for_book(
        self,
        book_repo: BookRepository,
        chapter_repo: BookChapterRepository,
    ):
        book = await _create_test_book(book_repo, "Book For Bulk Delete")

        for i in range(1, 5):
            await chapter_repo.create_chapters(book.id, BookChapterCreate(chapter=i, description=f"Chapter {i}"))

        count_before = await chapter_repo.count_chapters(book.id)
        assert count_before == 4

        deleted_count = await chapter_repo.delete_all_for_book(book.id)
        assert deleted_count == 4

        count_after = await chapter_repo.count_chapters(book.id)
        assert count_after == 0

    async def test_ensure_exists_errors(
        self,
        chapter_repo: BookChapterRepository,
    ):
        with pytest.raises(BookChapterNotFoundError):
            await chapter_repo.ensure_exists_by_id(999999)

        with pytest.raises(BookChapterNotFoundError):
            await chapter_repo.ensure_exists_by_book_and_number(123, 1)

    async def test_cascade_delete_when_book_deleted(
        self,
        session,
        book_repo: BookRepository,
        chapter_repo: BookChapterRepository,
    ):
        """
        Проверяем, что при удалении книги главы исчезают.
        Для Postgres ожидаем реальное каскадное удаление (ON DELETE CASCADE).
        Для SQLite поведение зависит от PRAGMA foreign_keys, поэтому
        жёстко не утверждаем, что главы исчезнут, но проверяем, что тест не падает.
        """
        book = await _create_test_book(book_repo, "Book To Cascade Delete")

        # создаём несколько глав
        for i in range(1, 4):
            await chapter_repo.create_chapters(book.id, BookChapterCreate(chapter=i, description=f"Ch {i}"))

        count_before = await chapter_repo.count_chapters(book.id)
        assert count_before == 3

        # удаляем книгу
        deleted = await book_repo.delete_book(book.id)
        assert deleted is True

        # пересчитываем главы
        count_after = await chapter_repo.count_chapters(book.id)

        # определяем backend через URL движка
        engine = session.bind  # AsyncEngine
        backend_name = engine.url.get_backend_name()  # 'sqlite' или 'postgresql'

        if backend_name.startswith("postgres"):
            # на Postgres с ON DELETE CASCADE главы должны исчезнуть
            assert count_after == 0
        else:
            # на SQLite foreign_keys могут быть не включены по умолчанию,
            # поэтому не делаем жёсткую проверку
            assert count_after == 0

    async def test_list_chapter_headers_returns_only_names_in_chapter_order(
        self,
        book_repo: BookRepository,
        chapter_repo: BookChapterRepository,
    ):
        book = await _create_test_book(book_repo, "Book With Header List")

        await chapter_repo.create_chapters(
            book.id,
            [
                BookChapterCreate(
                    chapter=3,
                    chapter_name="Third",
                    description="Text 3",
                    file=b"binary-3",
                ),
                BookChapterCreate(
                    chapter=1,
                    chapter_name="First",
                    description="Text 1",
                    file=b"binary-1",
                ),
                BookChapterCreate(
                    chapter=2,
                    chapter_name=None,
                    description="Text 2",
                    file=b"binary-2",
                ),
            ],
        )

        headers = await chapter_repo.list_chapter_headers(book.id)

        assert [(header.chapter, header.chapter_name) for header in headers] == [
            (1, "First"),
            (2, None),
            (3, "Third"),
        ]
        assert all(not hasattr(header, "description") for header in headers)
        assert all(not hasattr(header, "file") for header in headers)
