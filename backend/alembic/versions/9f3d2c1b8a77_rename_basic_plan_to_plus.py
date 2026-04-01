"""rename basic plan code to plus

Revision ID: 9f3d2c1b8a77
Revises: 1c4f98e1b789
Create Date: 2026-03-05 17:31:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9f3d2c1b8a77"
down_revision: Union[str, None] = "1c4f98e1b789"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Canonicalize plans from (free, basic, pro) -> (free, plus, pro)
    # Handles both cases:
    # 1) only basic exists: rename it to plus
    # 2) basic and plus both exist: migrate refs from basic to plus, then remove basic
    op.execute(
        sa.text(
            """
DO $$
DECLARE
    basic_id integer;
    plus_id integer;
BEGIN
    SELECT id INTO basic_id FROM plans WHERE code = 'basic' ORDER BY id LIMIT 1;
    SELECT id INTO plus_id  FROM plans WHERE code = 'plus'  ORDER BY id LIMIT 1;

    IF basic_id IS NULL AND plus_id IS NOT NULL THEN
        UPDATE plans SET name = 'Plus' WHERE id = plus_id;
        RETURN;
    END IF;

    IF basic_id IS NOT NULL AND plus_id IS NULL THEN
        UPDATE plans
        SET code = 'plus', name = 'Plus'
        WHERE id = basic_id;
        RETURN;
    END IF;

    IF basic_id IS NOT NULL AND plus_id IS NOT NULL THEN
        -- Move users to canonical plus plan.
        UPDATE users SET plan_id = plus_id WHERE plan_id = basic_id;

        -- Ensure plus has an entitlement row; if missing, copy from basic.
        INSERT INTO plan_entitlements (
            plan_id,
            daily_messages_limit,
            monthly_messages_limit,
            per_minute_messages_limit,
            context_messages_limit,
            context_chars_limit,
            chat_basic,
            indicators_basic,
            indicators_advanced,
            strategy_builder,
            exports,
            alerts,
            long_term_memory,
            created_at
        )
        SELECT
            plus_id,
            pe.daily_messages_limit,
            pe.monthly_messages_limit,
            pe.per_minute_messages_limit,
            pe.context_messages_limit,
            pe.context_chars_limit,
            pe.chat_basic,
            pe.indicators_basic,
            pe.indicators_advanced,
            pe.strategy_builder,
            pe.exports,
            pe.alerts,
            pe.long_term_memory,
            pe.created_at
        FROM plan_entitlements pe
        WHERE pe.plan_id = basic_id
          AND NOT EXISTS (
              SELECT 1 FROM plan_entitlements x WHERE x.plan_id = plus_id
          );

        -- Remove duplicated basic entitlement row if still present.
        DELETE FROM plan_entitlements WHERE plan_id = basic_id;

        -- Remove deprecated basic plan row.
        DELETE FROM plans WHERE id = basic_id;

        UPDATE plans SET name = 'Plus' WHERE id = plus_id;
    END IF;
END $$;
"""
        )
    )


def downgrade() -> None:
    # Best-effort reverse: plus -> basic when basic does not exist.
    op.execute(
        sa.text(
            """
DO $$
DECLARE
    basic_id integer;
    plus_id integer;
BEGIN
    SELECT id INTO basic_id FROM plans WHERE code = 'basic' ORDER BY id LIMIT 1;
    SELECT id INTO plus_id  FROM plans WHERE code = 'plus'  ORDER BY id LIMIT 1;

    IF basic_id IS NULL AND plus_id IS NOT NULL THEN
        UPDATE plans
        SET code = 'basic', name = 'Basic'
        WHERE id = plus_id;
    END IF;
END $$;
"""
        )
    )
