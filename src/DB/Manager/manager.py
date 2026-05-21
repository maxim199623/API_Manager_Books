from contextlib import asynccontextmanager
from typing import AsyncIterator, Type

from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncEngine,AsyncSession,async_sessionmaker,create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event

from src.core.config import DatabaseSettings

class AsyncDBManager:
    """
    Асинхронный менеджер БД:
    - создаёт AsyncEngine на основе DatabaseSettings;
    - даёт async_sessionmaker;
    - выдаёт сессии через async context manager;
    """

    def __init__(self, db_settings: DatabaseSettings, base: Type[DeclarativeBase]):
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
                # читаем ВСЕ строки из таблицы источника
                result = await src_conn.execute(select(table))
                rows = result.mappings().all()  # list[RowMapping]

                if not rows:
                    continue

                # приводим к list[dict], чтобы точно корректно вставилось
                payload = [dict(row) for row in rows]

                await dst_conn.execute(table.insert(), payload)