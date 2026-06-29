from __future__ import annotations

import argparse
import asyncio
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from api_manager_books.db.migrations import run_migrations

DEFAULT_BATCH_SIZE = 1000


def batched[T](items: Iterable[T], size: int) -> Iterable[list[T]]:
    """Разбивает поток на батчи фиксированного размера."""
    batch: list[T] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def uuid_hex() -> str:
    """Возвращает UUID в формате SQLite Uuid."""
    return uuid.uuid4().hex


async def insert_users(conn: AsyncConnection, count: int) -> list[str]:
    """Создает тестовых пользователей."""
    user_ids = [uuid_hex() for _ in range(count)]
    await conn.execute(
        text(
            """
            INSERT INTO users (id, email, password_hash, role)
            VALUES (:id, :email, :password_hash, :role)
            """
        ),
        [
            {
                "id": user_id,
                "email": f"user-{index}@example.com",
                "password_hash": b"hash",
                "role": "user",
            }
            for index, user_id in enumerate(user_ids)
        ],
    )
    return user_ids


async def insert_books(conn: AsyncConnection, count: int, batch_size: int) -> list[str]:
    """Создает книги батчами."""
    book_ids = [uuid_hex() for _ in range(count)]
    base_time = datetime(2026, 1, 1, tzinfo=UTC)
    rows = (
        {
            "id": book_id,
            "title": f"Book {index}",
            "author": f"Author {index % 100}",
            "series": f"Series {index % 50}",
            "created_at": base_time + timedelta(seconds=index),
        }
        for index, book_id in enumerate(book_ids)
    )
    for batch in batched(rows, batch_size):
        await conn.execute(
            text(
                """
                INSERT INTO books (id, title, author, series, created_at)
                VALUES (:id, :title, :author, :series, :created_at)
                """
            ),
            batch,
        )
    return book_ids


async def insert_chapters(
    conn: AsyncConnection,
    book_ids: list[str],
    count: int,
    batch_size: int,
) -> list[dict[str, str]]:
    """Создает главы и возвращает связь chapter_id/book_id."""
    rows = (
        {
            "id": uuid_hex(),
            "book_id": book_ids[index % len(book_ids)],
            "chapter": index,
            "description": "Synthetic chapter",
        }
        for index in range(count)
    )
    chapter_refs: list[dict[str, str]] = []
    for batch in batched(rows, batch_size):
        chapter_refs.extend({"id": row["id"], "book_id": row["book_id"]} for row in batch)
        await conn.execute(
            text(
                """
                INSERT INTO book_chapters (id, book_id, chapter, description)
                VALUES (:id, :book_id, :chapter, :description)
                """
            ),
            batch,
        )
    return chapter_refs


async def insert_progress_and_logs(
    conn: AsyncConnection,
    *,
    user_id: str,
    chapter_refs: list[dict[str, str]],
    count: int,
    batch_size: int,
) -> None:
    """Создает прогресс чтения и аудит-логи."""
    base_time = datetime(2026, 2, 1, tzinfo=UTC)
    progress_rows = (
        {
            "user_id": user_id,
            "book_id": chapter_refs[index % len(chapter_refs)]["book_id"],
            "chapter_id": chapter_refs[index % len(chapter_refs)]["id"],
            "read_at": base_time + timedelta(seconds=index),
        }
        for index in range(count)
    )
    for batch in batched(progress_rows, batch_size):
        await conn.execute(
            text(
                """
                INSERT OR IGNORE INTO reading_progress (user_id, book_id, chapter_id, read_at)
                VALUES (:user_id, :book_id, :chapter_id, :read_at)
                """
            ),
            batch,
        )

    log_rows = (
        {
            "id": uuid_hex(),
            "user_id": user_id,
            "action": "get_chapter",
            "entity": "book_chapters",
            "entity_id": chapter_refs[index % len(chapter_refs)]["id"],
            "created_at": base_time + timedelta(seconds=index),
        }
        for index in range(count)
    )
    for batch in batched(log_rows, batch_size):
        await conn.execute(
            text(
                """
                INSERT INTO db_logs (id, user_id, action, entity, entity_id, created_at)
                VALUES (:id, :user_id, :action, :entity, :entity_id, :created_at)
                """
            ),
            batch,
        )


async def explain(conn: AsyncConnection, sql: str, params: dict[str, object]) -> None:
    """Печатает план выполнения запроса."""
    print(f"\nEXPLAIN: {sql.strip()}")
    result = await conn.execute(text(f"EXPLAIN QUERY PLAN {sql}"), params)
    for row in result:
        print(row)


async def run_probe(args: argparse.Namespace) -> None:
    """Запускает наполнение и EXPLAIN."""
    if not args.database_url.startswith("sqlite+aiosqlite://"):
        raise ValueError("Скрипт использует SQLite EXPLAIN QUERY PLAN и поддерживает только sqlite+aiosqlite URL")

    await run_migrations(args.database_url)
    engine = create_async_engine(args.database_url)
    try:
        async with engine.begin() as conn:
            user_ids = await insert_users(conn, 1)
            book_ids = await insert_books(conn, args.books, args.batch_size)
            chapter_refs = await insert_chapters(conn, book_ids, args.chapters, args.batch_size)
            await insert_progress_and_logs(
                conn,
                user_id=user_ids[0],
                chapter_refs=chapter_refs,
                count=args.progress,
                batch_size=args.batch_size,
            )

            sample_book_id = book_ids[0]
            await explain(
                conn,
                """
                SELECT id FROM books
                WHERE created_at < :cursor_created_at
                ORDER BY created_at DESC, id ASC
                LIMIT 100
                """,
                {"cursor_created_at": datetime(2026, 1, 2, tzinfo=UTC)},
            )
            await explain(
                conn,
                """
                SELECT count(*) FROM reading_progress
                WHERE user_id = :user_id AND book_id = :book_id
                """,
                {"user_id": user_ids[0], "book_id": sample_book_id},
            )
            await explain(
                conn,
                """
                DELETE FROM reading_progress
                WHERE user_id = :user_id AND book_id = :book_id
                """,
                {"user_id": user_ids[0], "book_id": sample_book_id},
            )
            await explain(
                conn,
                """
                SELECT data FROM book_file_chunks
                WHERE book_id = :book_id
                ORDER BY chunk_index
                """,
                {"book_id": sample_book_id},
            )
    finally:
        await engine.dispose()


def parse_args() -> argparse.Namespace:
    """Разбирает параметры командной строки."""
    parser = argparse.ArgumentParser(description="Проверка индексов БД через EXPLAIN.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--books", type=int, default=10_000)
    parser.add_argument("--chapters", type=int, default=100_000)
    parser.add_argument("--progress", type=int, default=1_000_000)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    return parser.parse_args()


def main() -> None:
    """Точка входа."""
    asyncio.run(run_probe(parse_args()))


if __name__ == "__main__":
    main()
