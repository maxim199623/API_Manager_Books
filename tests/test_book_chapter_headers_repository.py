import pytest
import pytest_asyncio

from api_manager_books.db.Repository.BookChapterRepository.book_chapter_repository import (
    BookChapterRepository,
)
from api_manager_books.db.Repository.BookRepository.book_repository import BookRepository
from api_manager_books.schemas.book_chapters import BookChapterCreate
from api_manager_books.schemas.books import BookCreate

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def book_repo(repository_memory_session) -> BookRepository:
    return BookRepository(repository_memory_session)


@pytest_asyncio.fixture
async def chapter_repo(repository_memory_session) -> BookChapterRepository:
    return BookChapterRepository(repository_memory_session)


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
