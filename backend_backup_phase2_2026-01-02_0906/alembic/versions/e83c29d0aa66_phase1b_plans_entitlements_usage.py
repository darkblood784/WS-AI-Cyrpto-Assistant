"""phase1b plans entitlements usage

Revision ID: e83c29d0aa66
Revises: 26e088301c01
Create Date: 2025-12-26 08:10:03.701470

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e83c29d0aa66'
down_revision: Union[str, None] = '26e088301c01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) plans
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False, unique=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(op.f("ix_plans_code"), "plans", ["code"], unique=True)

    # 2) plan_entitlements (one row per plan)
    op.create_table(
        "plan_entitlements",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("daily_messages_limit", sa.Integer(), nullable=True),
        sa.Column("monthly_messages_limit", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_plan_entitlements_plan_id"), "plan_entitlements", ["plan_id"], unique=True)

    # 3) usage_counters (day/month buckets)
    op.create_table(
        "usage_counters",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("period_type", sa.String(length=16), nullable=False),  # 'day' | 'month'
        sa.Column("period_start", sa.DateTime(), nullable=False),        # naive UTC bucket start
        sa.Column("messages_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_usage_counters_user_id"), "usage_counters", ["user_id"], unique=False)
    op.create_index(
        "uq_usage_user_period",
        "usage_counters",
        ["user_id", "period_type", "period_start"],
        unique=True,
    )

    # 4) seed plans
    op.execute(sa.text("""
        INSERT INTO plans (code, name) VALUES
          ('free',  'Free'),
          ('basic', 'Basic'),
          ('pro',   'Pro')
        ON CONFLICT (code) DO NOTHING
    """))

    # 5) seed entitlements by joining on plan code (no ID assumptions)
    op.execute(sa.text("""
        INSERT INTO plan_entitlements (plan_id, daily_messages_limit, monthly_messages_limit)
        SELECT p.id, v.daily_messages_limit, v.monthly_messages_limit
        FROM plans p
        JOIN (
          VALUES
            ('free',  20,   300),
            ('basic', 200,  5000),
            ('pro',   1000, 30000)
        ) AS v(code, daily_messages_limit, monthly_messages_limit)
          ON v.code = p.code
        ON CONFLICT (plan_id) DO NOTHING
    """))

    # 6) users.plan_id (nullable first), backfill free, then NOT NULL
    op.add_column("users", sa.Column("plan_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_users_plan_id"), "users", ["plan_id"], unique=False)
    op.create_foreign_key(
        "fk_users_plan_id_plans",
        "users",
        "plans",
        ["plan_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.execute(sa.text("""
        UPDATE users
        SET plan_id = (SELECT id FROM plans WHERE code = 'free')
        WHERE plan_id IS NULL
    """))

    op.alter_column("users", "plan_id", nullable=False)


def downgrade() -> None:
    op.drop_constraint("fk_users_plan_id_plans", "users", type_="foreignkey")
    op.drop_index(op.f("ix_users_plan_id"), table_name="users")
    op.drop_column("users", "plan_id")

    op.drop_index("uq_usage_user_period", table_name="usage_counters")
    op.drop_index(op.f("ix_usage_counters_user_id"), table_name="usage_counters")
    op.drop_table("usage_counters")

    op.drop_index(op.f("ix_plan_entitlements_plan_id"), table_name="plan_entitlements")
    op.drop_table("plan_entitlements")

    op.drop_index(op.f("ix_plans_code"), table_name="plans")
    op.drop_table("plans")