"""add email verification fields to users

Revision ID: add_email_verification_fields
Revises: 369af1129a38
Create Date: 2025-12-23
"""

from alembic import op
import sqlalchemy as sa

# IMPORTANT: set this to your real previous revision:
revision = "c0db42272fb4"
down_revision = "369af1129a38"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("users", sa.Column("email_verification_token", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("email_verification_expires_at", sa.DateTime(), nullable=True))

    # remove default after existing rows are backfilled
    op.alter_column("users", "is_email_verified", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "email_verification_expires_at")
    op.drop_column("users", "email_verification_token")
    op.drop_column("users", "is_email_verified")
