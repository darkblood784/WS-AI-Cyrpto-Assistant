"""add news_items table

Revision ID: 1c4f98e1b789
Revises: ba81babff618
Create Date: 2026-01-08 17:12:45.315408

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1c4f98e1b789'
down_revision: Union[str, None] = 'ba81babff618'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "news_items",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("symbol", sa.String(length=16), nullable=True),
        sa.Column("source", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("summary", sa.String(length=1024), nullable=True),
    )
    op.create_index("ix_news_items_url", "news_items", ["url"], unique=True)
    op.create_index("ix_news_items_symbol", "news_items", ["symbol"], unique=False)
    op.create_index("ix_news_items_published_at", "news_items", ["published_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_news_items_published_at", table_name="news_items")
    op.drop_index("ix_news_items_symbol", table_name="news_items")
    op.drop_index("ix_news_items_url", table_name="news_items")
    op.drop_table("news_items")
