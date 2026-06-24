from contextlib import asynccontextmanager

from fastapi import FastAPI

# Импорт регистрирует ORM-модели в metadata SQLAlchemy.
import api_manager_books.db.models  # noqa: F401
from api_manager_books.db.Manager.manager import AsyncDBManager
from api_manager_books.db.base import Base
from api_manager_books.config.config import SettingsManager

from api_manager_books.api import main_router

from api_manager_books.bootstrap.admin import create_default_admin

# --------- LIFESPAN: старт/остановка приложения ---------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # загружаем настройки
    settings = SettingsManager("config.ini")

    # создаём менеджер БД
    db_manager = AsyncDBManager(settings.db, Base)

    # Создаём схемы (таблицы) один раз при старте
    await db_manager.create_schema()

    # создаём базового админа, если users пустая
    await create_default_admin(db_manager)

    # Сохраняем менеджеры в app.state, чтобы доставать в зависимостях
    app.state.db_manager = db_manager

    app.state.settings_manager = settings

    # приложение запущено
    try:
        yield
    finally:
        # аккуратно закрываем коннекты
        await db_manager.dispose()


app = FastAPI(lifespan=lifespan)
app.include_router(main_router)
