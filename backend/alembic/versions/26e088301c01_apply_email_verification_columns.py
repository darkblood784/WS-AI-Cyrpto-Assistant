"""apply email verification columns

Revision ID: <KEEP_WHATEVER_THIS_FILE_SAYS>
Revises: c0db42272fb4
Create Date: <KEEP>
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "26e088301c01"
down_revision = "c0db42272fb4"
branch_labels = None
depends_on = None


def upgrade() -> None:
#    op.add_column(
#        "users",
#        sa.Column(
#            "is_email_verified",
#            sa.Boolean(),
#            nullable=False,
#            server_default=sa.false(),
#        ),
#    )
#    op.add_column("users", sa.Column("email_verification_token", sa.Text(), nullable=True))
#    op.add_column("users", sa.Column("email_verification_expires_at", sa.DateTime(), nullable=True))

    # remove default after existing rows are backfilled
#    op.alter_column("users", "is_email_verified", server_default=None)
	pass

def downgrade() -> None:
#    op.drop_column("users", "email_verification_expires_at")
#    op.drop_column("users", "email_verification_token")
#    op.drop_column("users", "is_email_verified")
	pass
