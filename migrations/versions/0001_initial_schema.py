"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-06-30 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.LargeBinary(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("session", sa.Uuid(), nullable=True),
        sa.Column("refresh_token_hash", sa.LargeBinary(), nullable=True),
        sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "books",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("series", sa.String(length=255), nullable=True),
        sa.Column("genres", sa.Text(), nullable=True),
        sa.Column("format", sa.String(length=50), nullable=True),
        sa.Column("cover_mime", sa.String(length=255), nullable=True),
        sa.Column("cover_size", sa.Integer(), server_default="0", nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("file_mime", sa.String(length=255), nullable=True),
        sa.Column("file_size", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_books_author"), "books", ["author"], unique=False)
    op.create_index(op.f("ix_books_series"), "books", ["series"], unique=False)
    op.create_index(op.f("ix_books_title"), "books", ["title"], unique=False)

    op.create_table(
        "book_chapters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("chapter", sa.Integer(), nullable=False),
        sa.Column("chapter_name", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("file", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("book_id", "chapter", name="uq_book_chapter_num"),
    )
    op.create_index(op.f("ix_book_chapters_book_id"), "book_chapters", ["book_id"], unique=False)

    op.create_table(
        "book_cover_chunks",
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("book_id", "chunk_index"),
    )
    op.create_table(
        "book_file_chunks",
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("book_id", "chunk_index"),
    )
    op.create_table(
        "favorite_books",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "book_id", name="uq_favorite_books_user_book"),
    )
    op.create_index(op.f("ix_favorite_books_book_id"), "favorite_books", ["book_id"], unique=False)
    op.create_index(op.f("ix_favorite_books_user_id"), "favorite_books", ["user_id"], unique=False)

    op.create_table(
        "db_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("entity", sa.String(length=100), nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_db_logs_created_at"), "db_logs", ["created_at"], unique=False)
    op.create_index(op.f("ix_db_logs_entity"), "db_logs", ["entity"], unique=False)
    op.create_index(op.f("ix_db_logs_entity_id"), "db_logs", ["entity_id"], unique=False)
    op.create_index(op.f("ix_db_logs_user_id"), "db_logs", ["user_id"], unique=False)

    op.create_table(
        "book_chapter_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chapter_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("extension", sa.String(length=50), nullable=True),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("size", sa.Integer(), server_default="0", nullable=False),
        sa.Column("chunks_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["chapter_id"], ["book_chapters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_book_chapter_files_chapter_id"), "book_chapter_files", ["chapter_id"], unique=False)
    op.create_index(op.f("ix_book_chapter_files_extension"), "book_chapter_files", ["extension"], unique=False)
    op.create_index(op.f("ix_book_chapter_files_file_name"), "book_chapter_files", ["file_name"], unique=False)

    op.create_table(
        "book_chapter_file_chunks",
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["book_chapter_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("file_id", "chunk_index"),
    )


def downgrade() -> None:
    op.drop_table("book_chapter_file_chunks")
    op.drop_table("book_chapter_files")
    op.drop_table("db_logs")
    op.drop_table("favorite_books")
    op.drop_table("book_file_chunks")
    op.drop_table("book_cover_chunks")
    op.drop_table("book_chapters")
    op.drop_table("books")
    op.drop_table("users")
