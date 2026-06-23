from typing import AsyncIterator

import pytest
import pytest_asyncio

from src.schemas.config import DatabaseSettings, PostgresSettings, SQLiteSettings
from src.DB.Manager.manager import AsyncDBManager
from src.DB.base import Base
from src.schemas.book_chapters import BookChapterCreate
from src.DB.Repository.BookChapterRepository.book_chapter_repository import (
    BookChapterRepository,
)
from src.schemas.books import BookCreate
from src.DB.Repository.BookRepository.book_repository import BookRepository
from src.DB.Repository.UserRepository.ORM import User

pytestmark = pytest.mark.asyncio
SCHEMA_MODELS = (User,)


@pytest_asyncio.fixture(params=["sqlite", "postgres"], scope="function")
async def async_db_manager(
    request: pytest.FixtureRequest,
) -> AsyncIterator[AsyncDBManager]:
    backend = request.param
    settings = DatabaseSettings(
        backend=backend,
        echo=False,
        sqlite=SQLiteSettings(path=":memory:"),
        postgres=PostgresSettings(
            host="localhost",
            port=5432,
            user="admin",
            password="admin",
            name="test_db",
        ),
    )

    db_manager = AsyncDBManager(settings, Base)

    ok = await db_manager.ping()
    if not ok:
        await db_manager.dispose()
        pytest.skip(f"{backend} is not available, skipping tests for this backend")

    await db_manager.create_schema()

    try:
        yield db_manager
    finally:
        await db_manager.drop_schema()
        await db_manager.dispose()


@pytest_asyncio.fixture
async def session(async_db_manager: AsyncDBManager):
    async with async_db_manager.session() as db_session:
        yield db_session


@pytest_asyncio.fixture
async def book_repo(session) -> BookRepository:
    return BookRepository(session)


@pytest_asyncio.fixture
async def chapter_repo(session) -> BookChapterRepository:
    return BookChapterRepository(session)


async def test_list_chapter_headers_returns_only_names_in_chapter_order(
    book_repo: BookRepository,
    chapter_repo: BookChapterRepository,
):
    book = await book_repo.create_book(
        BookCreate(
            title="Book With Header List",
            author="Author X",
            description="Some desc",
            series="Series Y",
            format="epub",
        )
    )

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
