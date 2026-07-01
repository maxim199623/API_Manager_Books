import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

# Импорт регистрирует ORM-модели в metadata SQLAlchemy.
import api_manager_books.db.models  # noqa: F401
from api_manager_books.api import main_router
from api_manager_books.api.request_body_limit import RequestBodyLimitMiddleware
from api_manager_books.bootstrap.admin import create_initial_admin
from api_manager_books.config.config import SettingsManager
from api_manager_books.db.base import Base
from api_manager_books.db.Manager.manager import AsyncDBManager
from api_manager_books.db.migrations import run_migrations

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управляет запуском и остановкой приложения."""
    db_manager = None
    try:
        logger.info("Loading application settings")
        settings = SettingsManager("config.ini")

        logger.info("Creating database manager")
        db_manager = AsyncDBManager(settings.db, Base)

        logger.info("Starting database migrations")
        await run_migrations(settings.db.get_url)
        logger.info("Database migrations completed")

        logger.info("Starting initial admin bootstrap")
        await create_initial_admin(db_manager)
        logger.info("Initial admin bootstrap completed")

        app.state.db_manager = db_manager
        app.state.settings_manager = settings
        logger.info("Application startup completed")
    except Exception:
        logger.exception("Application startup failed")
        if db_manager is not None:
            await db_manager.dispose()
        raise

    try:
        yield
    finally:
        logger.info("Application shutdown started")
        await db_manager.dispose()
        logger.info("Application shutdown completed")


app = FastAPI(lifespan=lifespan)
app.add_middleware(RequestBodyLimitMiddleware)
app.include_router(main_router)
