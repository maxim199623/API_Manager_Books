"""reading progress and indexes

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-30 00:00:01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reading_progress",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("chapter_id", sa.Uuid(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chapter_id"], ["book_chapters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "chapter_id"),
        sa.UniqueConstraint("user_id", "chapter_id", name="uq_reading_progress_user_chapter"),
    )
    op.create_index(
        "ix_reading_progress_user_book_read_at",
        "reading_progress",
        ["user_id", "book_id", "read_at"],
        unique=False,
    )
    op.create_index(
        "ix_reading_progress_user_book_chapter",
        "reading_progress",
        ["user_id", "book_id", "chapter_id"],
        unique=False,
    )

    op.create_index("ix_books_created_at_id", "books", ["created_at", "id"], unique=False)
    op.create_index("ix_books_author_created_at_id", "books", ["author", "created_at", "id"], unique=False)
    op.create_index("ix_books_series_created_at_id", "books", ["series", "created_at", "id"], unique=False)
    op.create_index(
        "ix_db_logs_user_action_entity_created_at",
        "db_logs",
        ["user_id", "action", "entity", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_db_logs_user_action_entity_entity_id",
        "db_logs",
        ["user_id", "action", "entity", "entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_book_chapter_files_chapter_created_id",
        "book_chapter_files",
        ["chapter_id", "created_at", "id"],
        unique=False,
    )
    op.create_index("ix_users_refresh_token_hash", "users", ["refresh_token_hash"], unique=False)
    op.create_index("ix_users_role", "users", ["role"], unique=False)

    op.execute(
        """
        INSERT INTO reading_progress (user_id, book_id, chapter_id, read_at)
        SELECT logs.user_id, chapters.book_id, logs.entity_id, MAX(logs.created_at)
        FROM db_logs AS logs
        JOIN book_chapters AS chapters ON chapters.id = logs.entity_id
        WHERE logs.user_id IS NOT NULL
          AND logs.entity_id IS NOT NULL
          AND logs.action = 'get_chapter'
          AND logs.entity = 'book_chapters'
        GROUP BY logs.user_id, chapters.book_id, logs.entity_id
        """
    )


def downgrade() -> None:
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_refresh_token_hash", table_name="users")
    op.drop_index("ix_book_chapter_files_chapter_created_id", table_name="book_chapter_files")
    op.drop_index("ix_db_logs_user_action_entity_entity_id", table_name="db_logs")
    op.drop_index("ix_db_logs_user_action_entity_created_at", table_name="db_logs")
    op.drop_index("ix_books_series_created_at_id", table_name="books")
    op.drop_index("ix_books_author_created_at_id", table_name="books")
    op.drop_index("ix_books_created_at_id", table_name="books")
    op.drop_index("ix_reading_progress_user_book_chapter", table_name="reading_progress")
    op.drop_index("ix_reading_progress_user_book_read_at", table_name="reading_progress")
    op.drop_table("reading_progress")
