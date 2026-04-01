"""add user role

Revision ID: 8632d91c9a6d
Revises: 60d2071c34bb
Create Date: 2026-01-02 01:06:59.075592

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8632d91c9a6d'
down_revision: Union[str, None] = '60d2071c34bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("role", sa.String(length=16), nullable=False, server_default="user"))
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)
    op.execute("UPDATE users SET role='user' WHERE role IS NULL")
    op.alter_column("users", "role", server_default=None)

def downgrade() -> None:
    op.drop_index(op.f("ix_users_role"), table_name="users")
    op.drop_column("users", "role")
