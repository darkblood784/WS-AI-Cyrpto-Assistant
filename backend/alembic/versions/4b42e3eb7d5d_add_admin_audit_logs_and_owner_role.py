"""add admin audit logs and owner role

Revision ID: 4b42e3eb7d5d
Revises: 8632d91c9a6d
Create Date: 2026-01-02 01:57:53.272739

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4b42e3eb7d5d'
down_revision: Union[str, None] = '8632d91c9a6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=False),
        sa.Column("target_user_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )

    op.create_index("ix_admin_audit_logs_actor_user_id", "admin_audit_logs", ["actor_user_id"])
    op.create_index("ix_admin_audit_logs_target_user_id", "admin_audit_logs", ["target_user_id"])
    op.create_index("ix_admin_audit_logs_action", "admin_audit_logs", ["action"])
    op.create_index("ix_admin_audit_logs_created_at", "admin_audit_logs", ["created_at"])

    op.create_foreign_key(
        "fk_admin_audit_logs_actor_user",
        "admin_audit_logs",
        "users",
        ["actor_user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_admin_audit_logs_target_user",
        "admin_audit_logs",
        "users",
        ["target_user_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint("fk_admin_audit_logs_target_user", "admin_audit_logs", type_="foreignkey")
    op.drop_constraint("fk_admin_audit_logs_actor_user", "admin_audit_logs", type_="foreignkey")

    op.drop_index("ix_admin_audit_logs_created_at", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_action", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_target_user_id", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_actor_user_id", table_name="admin_audit_logs")

    op.drop_table("admin_audit_logs")
