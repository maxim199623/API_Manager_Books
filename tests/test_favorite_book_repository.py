import uuid

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError

from api_manager_books.db.Repository.BookRepository.book_repository import BookRepository
from api_manager_books.db.Repository.FavoriteBookRepository.favorite_book_repository import FavoriteBookRepository
from api_manager_books.db.Repository.UserRepository.user_repository import UserRepository
from api_manager_books.schemas.books import BookCreate
from api_manager_books.schemas.enums import UserRole
from api_manager_books.schemas.users import UserCreate

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def user_repo(repository_memory_session) -> UserRepository:
    """Готовит репозиторий пользователей."""
    return UserRepository(repository_memory_session)


@pytest_asyncio.fixture
async def book_repo(repository_memory_session) -> BookRepository:
    """Готовит репозиторий книг."""
    return BookRepository(repository_memory_session)


@pytest_asyncio.fixture
async def favorite_repo(repository_memory_session) -> FavoriteBookRepository:
    """Готовит репозиторий избранного."""
    return FavoriteBookRepository(repository_memory_session)


class TestFavoriteBookRepository:
    """Проверяет репозиторий избранных книг."""
    async def test_add_favorite_and_duplicate_returns_false(
        self,
        user_repo: UserRepository,
        book_repo: BookRepository,
        favorite_repo: FavoriteBookRepository,
    ):
        """Проверяет добавление избранного и дубликат."""
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
        await book_repo.create_book(
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
        await book_repo.create_book(
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
        """Проверяет конкурентный дубликат избранного."""
        calls = 0

        async def fake_get_by_user_and_book(user_id, book_id):
            """Имитирует поиск избранного по пользователю и книге."""
            nonlocal calls
            calls += 1
            if calls == 1:
                return None
            return object()

        async def fake_flush():
            """Имитирует сброс сессии."""
            raise IntegrityError("insert", {}, Exception("unique constraint failed"))

        def fake_add(_favorite):
            """Имитирует добавление в сессию."""
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
        repository_memory_session,
    ):
        """Проверяет сохранение ошибок внешнего ключа."""
        with pytest.raises(IntegrityError):
            await favorite_repo.add_favorite(uuid.uuid4(), uuid.uuid4())
        await repository_memory_session.rollback()

    async def test_list_favorite_book_ids_returns_subset(
        self,
        user_repo: UserRepository,
        book_repo: BookRepository,
        favorite_repo: FavoriteBookRepository,
    ):
        """Проверяет список избранное книгу ID возвращает подмножество."""
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
        """Проверяет remove избранное is идемпотентность."""
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
        """Проверяет каскадное удаление избранного при удалении книги."""
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
        """Проверяет каскадное удаление избранного при удалении пользователя."""
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
        """Проверяет каскадное удаление избранного при удалении книги."""
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
