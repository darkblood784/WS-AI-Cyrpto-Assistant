"""add unique constraints usage counters and plan entitlements

Revision ID: 60d2071c34bb
Revises: 556de3fe7b46
Create Date: 2025-12-31 09:33:01.487583

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '60d2071c34bb'
down_revision: Union[str, None] = '556de3fe7b46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) plan_entitlements: enforce 1 row per plan
    op.create_unique_constraint(
        "uq_plan_entitlements_plan_id",
        "plan_entitlements",
        ["plan_id"],
    )

    # 2) usage_counters: enforce 1 row per (user, period_type, period_start)
    op.create_unique_constraint(
        "uq_usage_counters_user_period",
        "usage_counters",
        ["user_id", "period_type", "period_start"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_usage_counters_user_period",
        "usage_counters",
        type_="unique",
    )
    op.drop_constraint(
        "uq_plan_entitlements_plan_id",
        "plan_entitlements",
        type_="unique",
    )
