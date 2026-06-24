import pytest
import pytest_asyncio

from api_manager_books.db.Repository.UserRepository.user_repository import (
    EmailAlreadyExistsError,
    UserNotFoundError,
    UserRepository,
)
from api_manager_books.schemas.enums import UserRole
from api_manager_books.schemas.users import UserCreate
from api_manager_books.security.passwords import verify_password

pytestmark = pytest.mark.asyncio

# ---------- Фикстура репозитория ----------

@pytest_asyncio.fixture
async def user_repo(repository_session) -> UserRepository:
    return UserRepository(repository_session)


# ---------- ТЕСТЫ ДЛЯ UserRepository ----------

class TestUserRepository:

    async def test_create_and_get_by_id(self, user_repo: UserRepository):
        password = "pass-1"
        created = await user_repo.create_user(
            UserCreate(
                email="user1@example.com",
                password=password,
                role=UserRole.USER,
            )
        )

        assert created.id is not None
        assert created.email == "user1@example.com"
        assert verify_password(password, created.password_hash)
        assert created.role == UserRole.USER

        fetched = await user_repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.email == created.email
        assert verify_password(password, fetched.password_hash)
        assert fetched.role == UserRole.USER

    async def test_get_by_email(self, user_repo: UserRepository):
        await user_repo.create_user(
            UserCreate(
                email="user2@example.com",
                password="pass-2",
                role=UserRole.ADMIN,
            )
        )

        user = await user_repo.get_by_email("user2@example.com")
        assert user is not None
        assert user.email == "user2@example.com"
        assert user.role == UserRole.ADMIN

        missing = await user_repo.get_by_email("no_such@mail.com")
        assert missing is None

    async def test_list_users(self, user_repo: UserRepository):
        # чисто для надёжности — можно подчистить таблицу (если тесты не изолированы)
        # но в норме схема пустая после drop/create
        users_data = [
            UserCreate(email="u1@mail.com", password="pass-u1", role=UserRole.USER),
            UserCreate(email="u2@mail.com", password="pass-u2", role=UserRole.ADMIN),
            UserCreate(email="u3@mail.com", password="pass-u3", role=UserRole.USER),
        ]
        for data in users_data:
            await user_repo.create_user(data)

        users = await user_repo.list_users()
        emails = {u.email for u in users}
        assert emails == {"u1@mail.com", "u2@mail.com", "u3@mail.com"}

    async def test_delete_user(self, user_repo: UserRepository):
        u = await user_repo.create_user(
            UserCreate(
                email="todelete@mail.com",
                password="pass-delete",
                role=UserRole.USER,
            )
        )
        deleted = await user_repo.delete_user(u.id)
        assert deleted is True

        again = await user_repo.delete_user(u.id)
        assert again is False  # уже нет

        user = await user_repo.get_by_id(u.id)
        assert user is None

    async def test_ensure_exists_success(self, user_repo: UserRepository):
        u = await user_repo.create_user(
            UserCreate(
                email="exists@mail.com",
                password="pass-exists",
                role=UserRole.USER,
            )
        )
        found = await user_repo.ensure_exists(u.id)
        assert found.id == u.id

    async def test_ensure_exists_not_found(self, user_repo: UserRepository):
        with pytest.raises(UserNotFoundError):
            await user_repo.ensure_exists(999999)

    async def test_unique_email_violation(self, user_repo: UserRepository):
        await user_repo.create_user(
            UserCreate(
                email="dup@mail.com",
                password="pass-dup-1",
                role=UserRole.USER,
            )
        )

        with pytest.raises(EmailAlreadyExistsError):
            await user_repo.create_user(
                UserCreate(
                    email="dup@mail.com",
                    password="pass-dup-2",
                    role=UserRole.ADMIN,
                )
            )

    async def test_update_user_email_role_password(self, user_repo: UserRepository):
        old_password = "old-password"
        u = await user_repo.create_user(
            UserCreate(
                email="old@mail.com",
                password=old_password,
                role=UserRole.USER,
            )
        )

        new_password = "new-password"

        updated = await user_repo.update_user(
            u.id,
            email="new@mail.com",
            password=new_password,
            role=UserRole.ADMIN,
        )

        assert updated.id == u.id
        assert updated.email == "new@mail.com"
        assert verify_password(new_password, updated.password_hash)
        assert updated.role == UserRole.ADMIN

        # перепроверяем из БД
        fetched = await user_repo.get_by_id(u.id)
        assert fetched is not None
        assert fetched.email == "new@mail.com"
        assert verify_password(new_password, fetched.password_hash)
        assert fetched.role == UserRole.ADMIN

    async def test_update_user_email_to_existing_should_fail(self, user_repo: UserRepository):
        u1 = await user_repo.create_user(
            UserCreate(
                email="user_a@mail.com",
                password="pass-a",
                role=UserRole.USER,
            )
        )
        u2 = await user_repo.create_user(
            UserCreate(
                email="user_b@mail.com",
                password="pass-b",
                role=UserRole.ADMIN,
            )
        )

        with pytest.raises(EmailAlreadyExistsError):
            await user_repo.update_user(
                u2.id,
                email="user_a@mail.com",  # уже занят u1
            )
