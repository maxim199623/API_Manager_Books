from pathlib import Path

import pytest
from sqlalchemy import Integer, String, select, inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from api_manager_books.config.config import SettingsManager
from api_manager_books.db.Manager.manager import AsyncDBManager

# ---------- Локальная база и тестовая таблица ----------

class BaseTestModel(DeclarativeBase):
    """Локальный Base только для тестов."""
    pass


class BaseTestItem(BaseTestModel):
    __tablename__ = "test_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


# ---------- Фикстуры ----------

@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Путь к временной config.ini для каждого теста."""
    return tmp_path / "config.ini"


@pytest.fixture
def settings_manager(config_path: Path, tmp_path: Path) -> SettingsManager:
    """
    SettingsManager, который создаёт config.ini в tmp-дереве,
    и настраивает sqlite на временный файл.
    """
    manager = SettingsManager(config_path)

    # БД в tmp-директории, чтобы ничего не засорять
    db_file = tmp_path / "test.db"
    manager.set_backend("sqlite")
    manager.set_sqlite_path(str(db_file))
    manager.set_echo(False)
    manager.save()

    return manager


@pytest.fixture
def async_db_manager(settings_manager: SettingsManager) -> AsyncDBManager:
    """
    Экземпляр AsyncDBManager, работающий с локальным TestBase и временной БД.
    """
    return AsyncDBManager(settings_manager.db, BaseTestItem)

class TestAsyncDBManager:
    @pytest.mark.asyncio
    async def test_engine_url_and_echo(self, async_db_manager: AsyncDBManager, settings_manager: SettingsManager):
        """
        Проверяем, что engine создаётся и URL соответствует настройкам.
        """
        engine = async_db_manager.engine
        url_str = str(engine.url)

        assert "sqlite+aiosqlite" in url_str
        # файл должен совпадать с тем, что записан в настройках
        assert settings_manager.sqlite is not None
        assert settings_manager.sqlite.path in url_str

        # echo должно браться из настроек
        assert engine.echo is settings_manager.db.echo is False

    @pytest.mark.asyncio
    async def test_create_and_drop_schema(self, async_db_manager: AsyncDBManager):
        """
        create_schema создаёт таблицы, drop_schema их удаляет.
        """
        # создаём схему
        await async_db_manager.create_schema()

        async with async_db_manager.engine.begin() as conn:
            def _get_tables(sync_conn):
                inspector = inspect(sync_conn)
                return inspector.get_table_names()

            tables = await conn.run_sync(_get_tables)

        assert "test_items" in tables

        # удаляем схему
        await async_db_manager.drop_schema()

        async with async_db_manager.engine.begin() as conn:
            tables_after = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_table_names()
            )

        assert "test_items" not in tables_after

    @pytest.mark.asyncio
    async def test_session_commit(self, async_db_manager: AsyncDBManager):
        """
        Проверяем, что через контекстный менеджер сессии данные действительно коммитятся.
        """
        await async_db_manager.create_schema()

        # вставка
        async with async_db_manager.session() as session:
            session.add(BaseTestItem(name="item-1"))

        # проверка
        async with async_db_manager.session() as session:
            result = await session.execute(
                select(BaseTestItem).where(BaseTestItem.name == "item-1")
            )
            item = result.scalar_one_or_none()

        assert item is not None
        assert item.name == "item-1"

    @pytest.mark.asyncio
    async def test_session_rollback_on_exception(self, async_db_manager: AsyncDBManager):
        """
        Если из блока сессии вылетело исключение, изменения откатываются.
        """
        await async_db_manager.create_schema()

        # пробуем вставить и специально падаем
        with pytest.raises(RuntimeError):
            async with async_db_manager.session() as session:
                session.add(BaseTestItem(name="should_be_rolled_back"))
                raise RuntimeError("boom")

        # проверяем, что записи нет
        async with async_db_manager.session() as session:
            result = await session.execute(
                select(BaseTestItem).where(BaseTestItem.name == "should_be_rolled_back")
            )
            item = result.scalar_one_or_none()

        assert item is None

    @pytest.mark.asyncio
    async def test_ping(self, async_db_manager: AsyncDBManager):
        """
        ping() возвращает True, если БД доступна.
        """
        ok = await async_db_manager.ping()
        assert ok is True

    @pytest.mark.asyncio
    async def test_dispose(self, async_db_manager: AsyncDBManager):
        """
        dispose() не падает и закрывает пул соединений.
        (Жёстко не проверяем, что пул закрыт — важно, что метод отрабатывает.)
        """
        await async_db_manager.dispose()

        # Повторный dispose тоже не должен падать
        await async_db_manager.dispose()