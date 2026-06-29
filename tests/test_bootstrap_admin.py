import pytest
import pytest_asyncio
from sqlalchemy import select

from api_manager_books.bootstrap.admin import (
    InitialAdminRequiredError,
    create_initial_admin,
)
from api_manager_books.db.base import Base
from api_manager_books.db.Manager.manager import AsyncDBManager
from api_manager_books.db.Repository.UserRepository.ORM import User
from api_manager_books.db.Repository.UserRepository.user_repository import UserRepository
from api_manager_books.schemas.config import DatabaseSettings, PostgresSettings, SQLiteSettings
from api_manager_books.schemas.enums import UserRole
from api_manager_books.schemas.users import UserCreate
from api_manager_books.security.passwords import verify_password

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def db_manager():
    settings = DatabaseSettings(
        backend="sqlite",
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
    manager = AsyncDBManager(settings, Base)
    await manager.create_schema()

    try:
        yield manager
    finally:
        await manager.dispose()


async def test_empty_users_table_requires_initial_admin_env(db_manager, monkeypatch):
    monkeypatch.delenv("INITIAL_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("INITIAL_ADMIN_PASSWORD", raising=False)

    with pytest.raises(InitialAdminRequiredError):
        await create_initial_admin(db_manager)


async def test_initial_admin_rejects_weak_default_password(db_manager, monkeypatch):
    monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "default")

    with pytest.raises(InitialAdminRequiredError):
        await create_initial_admin(db_manager)


async def test_valid_initial_admin_env_creates_exactly_one_admin(db_manager, monkeypatch):
    monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "change-this-long-password")

    await create_initial_admin(db_manager)

    async with db_manager.session() as session:
        users = (await session.execute(select(User))).scalars().all()

    assert len(users) == 1
    assert users[0].email == "admin@example.com"
    assert users[0].role == UserRole.ADMIN
    assert verify_password("change-this-long-password", users[0].password_hash)


async def test_non_empty_users_table_skips_initial_admin_env(db_manager, monkeypatch):
    async with db_manager.session() as session:
        repo = UserRepository(session)
        await repo.create_user(
            UserCreate(
                email="existing@example.com",
                password="existing-password",
                role=UserRole.USER,
            )
        )
        await session.commit()

    monkeypatch.delenv("INITIAL_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("INITIAL_ADMIN_PASSWORD", raising=False)

    await create_initial_admin(db_manager)

    async with db_manager.session() as session:
        users = (await session.execute(select(User))).scalars().all()

    assert len(users) == 1
    assert users[0].email == "existing@example.com"
