from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio

from src.core.config import SettingsManager
from src.DB.Manager.manager import AsyncDBManager
from src.DB.base import Base
from src.DB.Repository.UserRepository.Enums import UserRole
from src.DB.Repository.UserRepository.user_repository import UserRepository, EmailAlreadyExistsError, UserNotFoundError
from src.DB.Repository.UserRepository.Shems import UserCreate

pytestmark = pytest.mark.asyncio

# ---------- Фикстура SettingsManager для обоих backend ----------

@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    return tmp_path / "config.ini"


@pytest.fixture
def settings_manager(config_path: Path, tmp_path: Path) -> SettingsManager:
    """
    SettingsManager для тестов. На старте он сам создаст config.ini с дефолтами.
    Для sqlite мы переопределим путь на временный.
    Для postgres используем те значения, что в config.ini (по умолчанию localhost/postgres).
    """
    manager = SettingsManager(config_path)

    # для sqlite — кладём БД рядом с тестами
    db_file = tmp_path / "test_user_repo.db"
    manager.set_sqlite_path(str(db_file))
    manager.set_echo(False)
    manager.postgres.user = "admin"
    manager.postgres.password = "admin"
    manager.postgres.name = "test_db"
    manager.save()

    return manager


@pytest_asyncio.fixture(params=["sqlite", "postgres"], scope="function")
async def async_db_manager(
    request: pytest.FixtureRequest,
    settings_manager: SettingsManager,
) -> AsyncIterator[AsyncDBManager]:
    """
    Создаёт AsyncDBManager для sqlite и postgres.
    Для postgres, если соединиться не удалось — скипаем тесты с этим backend.
    """
    backend = request.param

    # переключаем backend в настройках
    settings_manager.set_backend(backend)
    settings_manager.save()

    db_manager = AsyncDBManager(settings_manager.db, Base)

    # проверяем доступность БД
    ok = await db_manager.ping()
    if not ok:
        await db_manager.dispose()
        pytest.skip(f"{backend} is not available, skipping tests for this backend")

    # создаём схему (таблица users и др.)
    await db_manager.create_schema()

    try:
        yield db_manager
    finally:
        # после теста можно дропнуть схему, если хочешь всё чистить
        # можно подчистить схему после тестов
        await db_manager.drop_schema()
        await db_manager.dispose()


# ---------- Фикстура AsyncSession ----------

@pytest_asyncio.fixture
async def session(async_db_manager: AsyncDBManager):
    async with async_db_manager.session() as s:
        yield s


# ---------- Фикстура репозитория ----------

@pytest_asyncio.fixture
async def user_repo(session) -> UserRepository:
    return UserRepository(session)


# ---------- ТЕСТЫ ДЛЯ UserRepository ----------

class TestUserRepository:

    async def test_create_and_get_by_id(self, user_repo: UserRepository):
        password_hash = b"hash1"
        created = await user_repo.create_user(
            UserCreate(
                email="user1@example.com",
                password_hash=password_hash,
                role=UserRole.USER,
            )
        )

        assert created.id is not None
        assert created.email == "user1@example.com"
        assert created.password_hash == password_hash
        assert created.role == UserRole.USER

        fetched = await user_repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.email == created.email
        assert fetched.password_hash == password_hash
        assert fetched.role == UserRole.USER

    async def test_get_by_email(self, user_repo: UserRepository):
        await user_repo.create_user(
            UserCreate(
                email="user2@example.com",
                password_hash=b"hash2",
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
            UserCreate(email="u1@mail.com", password_hash=b"h1", role=UserRole.USER),
            UserCreate(email="u2@mail.com", password_hash=b"h2", role=UserRole.ADMIN),
            UserCreate(email="u3@mail.com", password_hash=b"h3", role=UserRole.USER),
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
                password_hash=b"hdel",
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
                password_hash=b"hex",
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
                password_hash=b"h1",
                role=UserRole.USER,
            )
        )

        with pytest.raises(EmailAlreadyExistsError):
            await user_repo.create_user(
                UserCreate(
                    email="dup@mail.com",
                    password_hash=b"h2",
                    role=UserRole.ADMIN,
                )
            )

    async def test_update_user_email_role_password(self, user_repo: UserRepository):
        u = await user_repo.create_user(
            UserCreate(
                email="old@mail.com",
                password_hash=b"oldhash",
                role=UserRole.USER,
            )
        )

        new_hash = b"newhash"

        updated = await user_repo.update_user(
            u.id,
            email="new@mail.com",
            password_hash=new_hash,
            role=UserRole.ADMIN,
        )

        assert updated.id == u.id
        assert updated.email == "new@mail.com"
        assert updated.password_hash == new_hash
        assert updated.role == UserRole.ADMIN

        # перепроверяем из БД
        fetched = await user_repo.get_by_id(u.id)
        assert fetched is not None
        assert fetched.email == "new@mail.com"
        assert fetched.password_hash == new_hash
        assert fetched.role == UserRole.ADMIN

    async def test_update_user_email_to_existing_should_fail(self, user_repo: UserRepository):
        u1 = await user_repo.create_user(
            UserCreate(
                email="user_a@mail.com",
                password_hash=b"ha",
                role=UserRole.USER,
            )
        )
        u2 = await user_repo.create_user(
            UserCreate(
                email="user_b@mail.com",
                password_hash=b"hb",
                role=UserRole.ADMIN,
            )
        )

        with pytest.raises(EmailAlreadyExistsError):
            await user_repo.update_user(
                u2.id,
                email="user_a@mail.com",  # уже занят u1
            )