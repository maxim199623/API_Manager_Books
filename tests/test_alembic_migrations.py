import uuid
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from api_manager_books.db.migrations import run_migrations

pytestmark = pytest.mark.asyncio


async def test_alembic_upgrade_head_creates_reading_progress_and_indexes(tmp_path: Path):
    """Проверяет схему, созданную только миграциями Alembic."""
    db_path = tmp_path / "schema.db"
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = create_async_engine(database_url)

    try:
        await run_migrations(database_url)

        async with engine.connect() as conn:
            tables = await conn.run_sync(lambda sync_conn: set(inspect(sync_conn).get_table_names()))
            assert "reading_progress" in tables
            book_columns = await conn.run_sync(
                lambda sync_conn: {
                    column["name"]
                    for column in inspect(sync_conn).get_columns("books")
                }
            )

            indexes = await conn.run_sync(
                lambda sync_conn: {
                    table_name: {
                        index["name"]
                        for index in inspect(sync_conn).get_indexes(table_name)
                    }
                    for table_name in (
                        "books",
                        "db_logs",
                        "book_chapter_files",
                        "users",
                        "reading_progress",
                    )
                }
            )

        assert "ix_books_created_at_id" in indexes["books"]
        assert "ix_books_author_created_at_id" in indexes["books"]
        assert "ix_books_series_created_at_id" in indexes["books"]
        assert "ix_db_logs_user_action_entity_created_at" in indexes["db_logs"]
        assert "ix_db_logs_user_action_entity_entity_id" in indexes["db_logs"]
        assert "ix_book_chapter_files_chapter_created_id" in indexes["book_chapter_files"]
        assert "ix_users_refresh_token_hash" in indexes["users"]
        assert "ix_users_role" in indexes["users"]
        assert "ix_reading_progress_user_book_read_at" in indexes["reading_progress"]
        assert "ix_reading_progress_user_book_chapter" in indexes["reading_progress"]
        assert "cover_chunks_count" in book_columns
        assert "file_chunks_count" in book_columns
    finally:
        await engine.dispose()


async def test_alembic_backfills_reading_progress_from_existing_logs(tmp_path: Path):
    """Проверяет перенос старой истории чтения из db_logs."""
    db_path = tmp_path / "backfill.db"
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = create_async_engine(database_url)

    try:
        await run_migrations(database_url, revision="0001")

        user_id = uuid.uuid4()
        book_id = uuid.uuid4()
        chapter_id = uuid.uuid4()
        other_chapter_id = uuid.uuid4()

        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO users (id, email, password_hash, role)
                    VALUES (:id, :email, :password_hash, :role)
                    """
                ),
                {
                    "id": user_id.hex,
                    "email": "reader@example.com",
                    "password_hash": b"hash",
                    "role": "user",
                },
            )
            await conn.execute(
                text("INSERT INTO books (id, title) VALUES (:id, :title)"),
                {"id": book_id.hex, "title": "Book"},
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO book_chapters (id, book_id, chapter, description)
                    VALUES (:id, :book_id, :chapter, :description)
                    """
                ),
                [
                    {
                        "id": chapter_id.hex,
                        "book_id": book_id.hex,
                        "chapter": 1,
                        "description": "One",
                    },
                    {
                        "id": other_chapter_id.hex,
                        "book_id": book_id.hex,
                        "chapter": 2,
                        "description": "Two",
                    },
                ],
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO db_logs (id, user_id, action, entity, entity_id)
                    VALUES (:id, :user_id, :action, :entity, :entity_id)
                    """
                ),
                [
                    {
                        "id": uuid.uuid4().hex,
                        "user_id": user_id.hex,
                        "action": "get_chapter",
                        "entity": "book_chapters",
                        "entity_id": chapter_id.hex,
                    },
                    {
                        "id": uuid.uuid4().hex,
                        "user_id": user_id.hex,
                        "action": "update_chapter",
                        "entity": "book_chapters",
                        "entity_id": other_chapter_id.hex,
                    },
                ],
            )

        await run_migrations(database_url)

        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        """
                        SELECT user_id, book_id, chapter_id
                        FROM reading_progress
                        """
                    )
                )
            ).mappings().all()

        assert rows == [
            {
                "user_id": user_id.hex,
                "book_id": book_id.hex,
                "chapter_id": chapter_id.hex,
            }
        ]
    finally:
        await engine.dispose()
