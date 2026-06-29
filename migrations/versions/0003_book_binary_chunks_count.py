"""book binary chunks count

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-30 00:00:02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "books",
        sa.Column("cover_chunks_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "books",
        sa.Column("file_chunks_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.execute(
        """
        UPDATE books
        SET cover_chunks_count = (
            SELECT COUNT(*)
            FROM book_cover_chunks
            WHERE book_cover_chunks.book_id = books.id
        )
        """
    )
    op.execute(
        """
        UPDATE books
        SET file_chunks_count = (
            SELECT COUNT(*)
            FROM book_file_chunks
            WHERE book_file_chunks.book_id = books.id
        )
        """
    )


def downgrade() -> None:
    op.drop_column("books", "file_chunks_count")
    op.drop_column("books", "cover_chunks_count")
