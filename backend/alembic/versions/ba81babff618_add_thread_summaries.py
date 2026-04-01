"""add thread_summaries

Revision ID: ba81babff618
Revises: 4b42e3eb7d5d
Create Date: 2026-01-06 15:52:42.672771

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ba81babff618'
down_revision: Union[str, None] = '4b42e3eb7d5d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "thread_summaries",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("covered_until_message_id", sa.String(length=36), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["threads.id"],
            ondelete="CASCADE",
            name="fk_thread_summaries_thread_id_threads",
        ),
    )

    op.create_unique_constraint(
        "uq_thread_summaries_thread_id",
        "thread_summaries",
        ["thread_id"],
    )

    op.create_index(
        "ix_thread_summaries_updated_at",
        "thread_summaries",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_thread_summaries_updated_at", table_name="thread_summaries")
    op.drop_constraint("uq_thread_summaries_thread_id", "thread_summaries", type_="unique")
    op.drop_table("thread_summaries")

