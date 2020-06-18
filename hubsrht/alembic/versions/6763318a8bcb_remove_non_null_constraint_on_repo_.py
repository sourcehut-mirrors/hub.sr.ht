"""Remove non-null constraint on repo description

Revision ID: 6763318a8bcb
Revises: 9bc56ae84494
Create Date: 2020-06-18 09:45:55.946706

"""

# revision identifiers, used by Alembic.
revision = '6763318a8bcb'
down_revision = '9bc56ae84494'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.alter_column("source_repo", "description", nullable=True)


def downgrade():
    op.alter_column("source_repo", "description", nullable=False)
