"""expand password hash length

Revision ID: 369af1129a38
Revises: a71812feb508
Create Date: 2025-12-22 09:31:52.539978

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '369af1129a38'
down_revision: Union[str, None] = 'a71812feb508'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.alter_column("users", "password_hash", type_=sa.Text())

def downgrade():
    op.alter_column("users", "password_hash", type_=sa.String(length=255))
