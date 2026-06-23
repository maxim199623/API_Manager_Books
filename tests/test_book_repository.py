import pytest
import pytest_asyncio

from src.DB.Repository.BookRepository.book_repository import BookRepository, BookNotFoundError
from src.schemas.books import BookCreate, BookUpdate

pytestmark = pytest.mark.asyncio

# ---------- Фикстура репозитория ----------

@pytest_asyncio.fixture
async def book_repo(repository_session) -> BookRepository:
    return BookRepository(repository_session)


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
        repository_session,
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
        await repository_session.flush()

        asc_books = await book_repo.list_books(sort_by="created_at", sort_dir="asc")
        desc_books = await book_repo.list_books(sort_by="created_at", sort_dir="desc")

        assert [book.title for book in asc_books] == ["Older", "Newer"]
        assert [book.title for book in desc_books] == ["Newer", "Older"]

    async def test_list_books_sorts_by_user_progress(
        self,
        book_repo: BookRepository,
        repository_session,
    ):
        from src.DB.Repository.BookChapterRepository.ORM import BookChapter
        from src.DB.Repository.LogRepository.ORM import LogEntry
        from src.schemas.enums import UserRole
        from src.DB.Repository.UserRepository.ORM import User

        user = User(
            email="progress-reader@example.com",
            password_hash=b"hash",
            role=UserRole.USER,
        )
        other_user = User(
            email="other-progress-reader@example.com",
            password_hash=b"hash",
            role=UserRole.USER,
        )
        repository_session.add_all([user, other_user])
        await repository_session.flush()

        books = {}
        for title in ["Low Progress", "Mid Progress", "High Progress", "No Chapters"]:
            books[title] = await book_repo.create_book(
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

        chapters_by_title = {}
        for title in ["Low Progress", "Mid Progress", "High Progress"]:
            chapters_by_title[title] = []
            for chapter_num in range(1, 5):
                chapter = BookChapter(
                    book_id=books[title].id,
                    chapter=chapter_num,
                    chapter_name=None,
                    description=f"{title} chapter {chapter_num}",
                    file=None,
                )
                repository_session.add(chapter)
                chapters_by_title[title].append(chapter)
        await repository_session.flush()

        repository_session.add_all(
            [
                LogEntry(
                    user_id=user.id,
                    action="get_chapter",
                    entity="book_chapters",
                    entity_id=chapters_by_title["Low Progress"][0].id,
                ),
                LogEntry(
                    user_id=user.id,
                    action="get_chapter",
                    entity="book_chapters",
                    entity_id=chapters_by_title["Mid Progress"][0].id,
                ),
                LogEntry(
                    user_id=user.id,
                    action="get_chapter",
                    entity="book_chapters",
                    entity_id=chapters_by_title["Mid Progress"][1].id,
                ),
                LogEntry(
                    user_id=user.id,
                    action="get_chapter",
                    entity="book_chapters",
                    entity_id=chapters_by_title["High Progress"][0].id,
                ),
                LogEntry(
                    user_id=user.id,
                    action="get_chapter",
                    entity="book_chapters",
                    entity_id=chapters_by_title["High Progress"][1].id,
                ),
                LogEntry(
                    user_id=user.id,
                    action="get_chapter",
                    entity="book_chapters",
                    entity_id=chapters_by_title["High Progress"][2].id,
                ),
                LogEntry(
                    user_id=user.id,
                    action="get_chapter",
                    entity="book_chapters",
                    entity_id=chapters_by_title["High Progress"][2].id,
                ),
                LogEntry(
                    user_id=other_user.id,
                    action="get_chapter",
                    entity="book_chapters",
                    entity_id=chapters_by_title["Low Progress"][1].id,
                ),
            ]
        )
        await repository_session.flush()

        desc_books = await book_repo.list_books(
            sort_by="progress",
            sort_dir="desc",
            user_id=user.id,
            limit=10,
        )
        asc_books = await book_repo.list_books(
            sort_by="progress",
            sort_dir="asc",
            user_id=user.id,
            limit=10,
        )

        assert [book.title for book in desc_books] == [
            "High Progress",
            "Mid Progress",
            "Low Progress",
            "No Chapters",
        ]
        assert [book.title for book in asc_books] == [
            "No Chapters",
            "Low Progress",
            "Mid Progress",
            "High Progress",
        ]

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
