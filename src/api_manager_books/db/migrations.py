from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config


def _build_config(database_url: str) -> Config:
    """Готовит конфигурацию Alembic для программного запуска."""
    project_root = Path(__file__).resolve().parents[3]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


async def run_migrations(database_url: str, *, revision: str = "head") -> None:
    """Применяет миграции Alembic к указанной БД."""
    config = _build_config(database_url)
    await asyncio.to_thread(command.upgrade, config, revision)
