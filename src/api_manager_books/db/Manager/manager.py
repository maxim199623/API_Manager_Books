from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event, select, text
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
                """Настроить SQLite для FK и ожидания блокировок."""
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=15000")
                if self._engine.url.database not in {None, "", ":memory:"}:
                    cursor.execute("PRAGMA journal_mode=WAL")
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
    def database_url(self) -> str:
        """URL подключения к БД."""
        return self._settings.get_url


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

    async def drop_schema(self) -> None:
        """
        Удалить все таблицы.
        Опасно: полностью чистит схему/БД.
        """
        async with self._engine.begin() as conn:
            await conn.run_sync(self._base.metadata.drop_all)
            await conn.execute(text("DROP TABLE IF EXISTS alembic_version"))

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
