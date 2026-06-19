from typing import AsyncIterator
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError

from src.core.Shems import DatabaseSettings, PostgresSettings, SQLiteSettings
from src.DB.Manager.manager import AsyncDBManager
from src.DB.base import Base
from src.DB.Repository.BookRepository.Shems import BookCreate
from src.DB.Repository.BookRepository.book_repository import BookRepository
from src.DB.Repository.FavoriteBookRepository.favorite_book_repository import FavoriteBookRepository
from src.DB.Repository.UserRepository.Enums import UserRole
from src.DB.Repository.UserRepository.Shems import UserCreate
from src.DB.Repository.UserRepository.user_repository import UserRepository

pytestmark = pytest.mark.asyncio


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
    async with async_db_manager.session() as s:
        yield s


@pytest_asyncio.fixture
async def user_repo(session) -> UserRepository:
    return UserRepository(session)


@pytest_asyncio.fixture
async def book_repo(session) -> BookRepository:
    return BookRepository(session)


@pytest_asyncio.fixture
async def favorite_repo(session) -> FavoriteBookRepository:
    return FavoriteBookRepository(session)


class TestFavoriteBookRepository:
    async def test_add_favorite_and_duplicate_returns_false(
        self,
        user_repo: UserRepository,
        book_repo: BookRepository,
        favorite_repo: FavoriteBookRepository,
    ):
        user = await user_repo.create_user(
            UserCreate(
                email="favorite-user@example.com",
                password="secret123",
                role=UserRole.USER,
            )
        )

        first_book = await book_repo.create_book(
            BookCreate(
                cover=None,
                title="Favorite Book 1",
                author="Author 1",
                description=None,
                series=None,
                genres=None,
                format="pdf",
                file=None,
            )
        )
        second_book = await book_repo.create_book(
            BookCreate(
                cover=None,
                title="Favorite Book 2",
                author="Author 2",
                description=None,
                series=None,
                genres=None,
                format="epub",
                file=None,
            )
        )
        third_book = await book_repo.create_book(
            BookCreate(
                cover=None,
                title="Favorite Book 3",
                author="Author 3",
                description=None,
                series=None,
                genres=None,
                format="mobi",
                file=None,
            )
        )

        added = await favorite_repo.add_favorite(user.id, first_book.id)
        assert added is True
        assert await favorite_repo.is_favorite(user.id, first_book.id) is True

        favorite = await favorite_repo.get_by_user_and_book(user.id, first_book.id)
        assert favorite is not None
        assert favorite.user_id == user.id
        assert favorite.book_id == first_book.id

        duplicate_added = await favorite_repo.add_favorite(user.id, first_book.id)
        assert duplicate_added is False

    async def test_add_favorite_returns_false_when_concurrent_duplicate_wins(
        self,
        monkeypatch: pytest.MonkeyPatch,
        favorite_repo: FavoriteBookRepository,
    ):
        calls = 0

        async def fake_get_by_user_and_book(user_id, book_id):
            nonlocal calls
            calls += 1
            if calls == 1:
                return None
            return object()

        async def fake_flush():
            raise IntegrityError("insert", {}, Exception("unique constraint failed"))

        def fake_add(_favorite):
            return None

        monkeypatch.setattr(
            favorite_repo,
            "get_by_user_and_book",
            fake_get_by_user_and_book,
        )
        monkeypatch.setattr(favorite_repo._session, "add", fake_add)
        monkeypatch.setattr(favorite_repo._session, "flush", fake_flush)

        added = await favorite_repo.add_favorite(uuid.uuid4(), uuid.uuid4())
        assert added is False

    async def test_add_favorite_does_not_swallow_foreign_key_errors(
        self,
        favorite_repo: FavoriteBookRepository,
        session,
    ):
        with pytest.raises(IntegrityError):
            await favorite_repo.add_favorite(uuid.uuid4(), uuid.uuid4())
        await session.rollback()

    async def test_list_favorite_book_ids_returns_subset(
        self,
        user_repo: UserRepository,
        book_repo: BookRepository,
        favorite_repo: FavoriteBookRepository,
    ):
        user = await user_repo.create_user(
            UserCreate(
                email="subset-user@example.com",
                password="secret123",
                role=UserRole.USER,
            )
        )
        first_book = await book_repo.create_book(
            BookCreate(
                cover=None,
                title="Subset Book 1",
                author="Author 1",
                description=None,
                series=None,
                genres=None,
                format="pdf",
                file=None,
            )
        )
        second_book = await book_repo.create_book(
            BookCreate(
                cover=None,
                title="Subset Book 2",
                author="Author 2",
                description=None,
                series=None,
                genres=None,
                format="epub",
                file=None,
            )
        )
        third_book = await book_repo.create_book(
            BookCreate(
                cover=None,
                title="Subset Book 3",
                author="Author 3",
                description=None,
                series=None,
                genres=None,
                format="mobi",
                file=None,
            )
        )

        await favorite_repo.add_favorite(user.id, first_book.id)
        await favorite_repo.add_favorite(user.id, second_book.id)

        favorites_subset = await favorite_repo.list_favorite_book_ids(
            user.id,
            [first_book.id, second_book.id, third_book.id],
        )
        assert favorites_subset == {first_book.id, second_book.id}

    async def test_remove_favorite_is_idempotent(
        self,
        user_repo: UserRepository,
        book_repo: BookRepository,
        favorite_repo: FavoriteBookRepository,
    ):
        user = await user_repo.create_user(
            UserCreate(
                email="remove-user@example.com",
                password="secret123",
                role=UserRole.USER,
            )
        )
        book = await book_repo.create_book(
            BookCreate(
                cover=None,
                title="Remove Book",
                author="Author 1",
                description=None,
                series=None,
                genres=None,
                format="pdf",
                file=None,
            )
        )

        await favorite_repo.add_favorite(user.id, book.id)

        removed = await favorite_repo.remove_favorite(user.id, book.id)
        assert removed is True
        assert await favorite_repo.is_favorite(user.id, book.id) is False

        removed_again = await favorite_repo.remove_favorite(user.id, book.id)
        assert removed_again is False

    async def test_favorites_are_deleted_when_book_is_deleted(
        self,
        user_repo: UserRepository,
        book_repo: BookRepository,
        favorite_repo: FavoriteBookRepository,
    ):
        user = await user_repo.create_user(
            UserCreate(
                email="cascade-book-user@example.com",
                password="secret123",
                role=UserRole.USER,
            )
        )
        book = await book_repo.create_book(
            BookCreate(
                cover=None,
                title="Cascade Book",
                author="Author 1",
                description=None,
                series=None,
                genres=None,
                format="pdf",
                file=None,
            )
        )

        await favorite_repo.add_favorite(user.id, book.id)
        assert await favorite_repo.is_favorite(user.id, book.id) is True

        await book_repo.delete_book(book.id)
        assert await favorite_repo.is_favorite(user.id, book.id) is False

    async def test_favorites_are_deleted_when_user_is_deleted(
        self,
        user_repo: UserRepository,
        book_repo: BookRepository,
        favorite_repo: FavoriteBookRepository,
    ):
        user = await user_repo.create_user(
            UserCreate(
                email="cascade-user@example.com",
                password="secret123",
                role=UserRole.USER,
            )
        )
        book = await book_repo.create_book(
            BookCreate(
                cover=None,
                title="User Cascade Book",
                author="Author 1",
                description=None,
                series=None,
                genres=None,
                format="pdf",
                file=None,
            )
        )

        await favorite_repo.add_favorite(user.id, book.id)
        assert await favorite_repo.is_favorite(user.id, book.id) is True

        await user_repo.delete_user(user.id)
        assert await favorite_repo.is_favorite(user.id, book.id) is False

    async def test_favorites_for_other_user_are_deleted_when_book_is_deleted(
        self,
        user_repo: UserRepository,
        book_repo: BookRepository,
        favorite_repo: FavoriteBookRepository,
    ):
        other_user = await user_repo.create_user(
            UserCreate(
                email="other-user@example.com",
                password="secret123",
                role=UserRole.USER,
            )
        )
        third_book = await book_repo.create_book(
            BookCreate(
                cover=None,
                title="Other User Cascade Book",
                author="Author 3",
                description=None,
                series=None,
                genres=None,
                format="mobi",
                file=None,
            )
        )
        await favorite_repo.add_favorite(other_user.id, third_book.id)
        assert await favorite_repo.is_favorite(other_user.id, third_book.id) is True

        await book_repo.delete_book(third_book.id)
        assert await favorite_repo.is_favorite(other_user.id, third_book.id) is False
