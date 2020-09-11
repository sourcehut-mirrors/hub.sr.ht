"""Add project.tags

Revision ID: 4da86bb54214
Revises: 6763318a8bcb
Create Date: 2020-09-10 03:41:10.011430

"""

# revision identifiers, used by Alembic.
revision = '4da86bb54214'
down_revision = '6763318a8bcb'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column("project", sa.Column("tags",
            sa.ARRAY(sa.String(16), dimensions=1),
            nullable=False, server_default="{}"))


def downgrade():
    op.drop_column("project", "tags")
