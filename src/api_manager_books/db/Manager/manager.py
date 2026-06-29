from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event, select, text
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from api_manager_books.config.config import DatabaseSettings

MIGRATION_BATCH_SIZE = 1000


class AsyncDBManager:
    """
    Асинхронный менеджер БД:
    - создаёт AsyncEngine на основе DatabaseSettings;
    - даёт async_sessionmaker;
    - выдаёт сессии через async context manager;
    """

    def __init__(self, db_settings: DatabaseSettings, base: type[DeclarativeBase]):
        """Инициализировать менеджер БД."""
        self._settings = db_settings
        self._base = base


        self._engine: AsyncEngine = create_async_engine(
            self._settings.get_url,  # строка подключения из настроек
            echo=self._settings.echo,
            future=True,
            connect_args={
                "timeout": 15,
            }
        )

        if self._engine.url.get_backend_name() == "sqlite":
            @event.listens_for(self._engine.sync_engine, "connect")
            def _set_sqlite_pragma(dbapi_conn, connection_record):
                """Включить внешние ключи для SQLite."""
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        # фабрика асинхронных сессий
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
        )


    @property
    def engine(self) -> AsyncEngine:
        """Асинхронный движок SQLAlchemy."""
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Фабрика асинхронных сессий."""
        return self._session_factory


    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """
        Контекстный менеджер для работы с сессией.

        Пример:
            async with db_manager.session() as session:
                result = await session.execute(...)
        """
        session: AsyncSession = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def create_schema(self) -> None:
        """
        Создать все таблицы, описанные в ORM-моделях (Base.metadata).
        """
        async with self._engine.begin() as conn:
            await conn.run_sync(self._base.metadata.create_all)

    async def upgrade_schema(self) -> None:
        """Добавить совместимые nullable-колонки без Alembic."""
        async with self._engine.begin() as conn:
            tables = await conn.run_sync(
                lambda sync_conn: sa_inspect(sync_conn).get_table_names()
            )
            if "users" not in tables:
                return

            columns = await conn.run_sync(
                lambda sync_conn: {
                    column["name"]
                    for column in sa_inspect(sync_conn).get_columns("users")
                }
            )
            dialect = conn.dialect.name
            column_types = {
                "refresh_token_hash": "BYTEA" if dialect == "postgresql" else "BLOB",
                "refresh_token_expires_at": (
                    "TIMESTAMP WITH TIME ZONE"
                    if dialect == "postgresql"
                    else "DATETIME"
                ),
            }

            for column_name, column_type in column_types.items():
                if column_name not in columns:
                    await conn.execute(
                        text(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")
                    )

    async def drop_schema(self) -> None:
        """
        Удалить все таблицы.
        Опасно: полностью чистит схему/БД.
        """
        async with self._engine.begin() as conn:
            await conn.run_sync(self._base.metadata.drop_all)

    async def recreate_schema(self) -> None:
        """Полностью пересоздать схему (drop + create)."""
        async with self._engine.begin() as conn:
            await conn.run_sync(self._base.metadata.drop_all)
            await conn.run_sync(self._base.metadata.create_all)

    async def ping(self) -> bool:
        """
        Проверка доступности БД.
        Возвращает True, если простой запрос SELECT 1 успешно отработал.
        """
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    async def dispose(self) -> None:
        """Закрыть пул соединений и освободить ресурсы."""
        await self._engine.dispose()

    async def migrate_to(self, target: "AsyncDBManager") -> None:
        """
        Миграция данных из этой БД в БД `target`.

        """

        if str(self._engine.url) == str(target.engine.url):
            return

        metadata = self._base.metadata

        # Одновременно держим подключение к старой и новой БД
        async with self._engine.connect() as src_conn, target.engine.begin() as dst_conn:
            # Идём по таблицам в порядке с учётом зависимостей (FK)
            for table in metadata.sorted_tables:
                result = await src_conn.stream(select(table))
                async for rows in result.mappings().partitions(MIGRATION_BATCH_SIZE):
                    payload = [dict(row) for row in rows]
                    if payload:
                        await dst_conn.execute(table.insert(), payload)
