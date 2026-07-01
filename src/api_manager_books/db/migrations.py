from __future__ import annotations

import asyncio
import logging
import sqlite3
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

logger = logging.getLogger(__name__)


class DatabasePreflightError(RuntimeError):
    """База данных недоступна для безопасного запуска миграций."""


def _build_config(database_url: str) -> Config:
    """Готовит конфигурацию Alembic для программного запуска."""
    project_root = Path(__file__).resolve().parents[3]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.config_file_name = None
    return config


def _unlink_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


def _preflight_sqlite_database(database_url: str) -> None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        return

    database_path = url.database
    if database_path in {None, "", ":memory:"}:
        return

    db_path = Path(database_path)
    db_dir = db_path.parent
    temp_db = db_dir / f".sqlite-preflight-{uuid.uuid4().hex}.db"
    sidecar_paths = (
        temp_db,
        temp_db.with_name(f"{temp_db.name}-journal"),
        temp_db.with_name(f"{temp_db.name}-wal"),
        temp_db.with_name(f"{temp_db.name}-shm"),
    )

    if not db_dir.exists():
        raise DatabasePreflightError(
            f"SQLite database preflight failed: directory does not exist: {db_dir}"
        )

    try:
        connection = sqlite3.connect(temp_db)
        try:
            connection.execute("CREATE TABLE preflight (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("INSERT INTO preflight (value) VALUES (?)", ("ok",))
            connection.commit()
        finally:
            connection.close()
    except Exception as exc:
        raise DatabasePreflightError(
            f"SQLite database preflight failed: cannot write test database in {db_dir}: {exc}"
        ) from exc

    for path in sidecar_paths:
        try:
            _unlink_if_exists(path)
        except Exception as exc:
            raise DatabasePreflightError(
                f"SQLite database preflight failed: cannot delete temporary file "
                f"during SQLite journal cleanup in {db_dir}; operation=delete temporary file; "
                f"path={path}; error={exc}"
            ) from exc


async def run_migrations(database_url: str, *, revision: str = "head") -> None:
    """Применяет миграции Alembic к указанной БД."""
    logger.info("Starting database migrations to %s", revision)
    try:
        _preflight_sqlite_database(database_url)
        config = _build_config(database_url)
        await asyncio.to_thread(command.upgrade, config, revision)
    except Exception:
        logger.exception("Database migrations failed")
        raise
    logger.info("Database migrations completed")
