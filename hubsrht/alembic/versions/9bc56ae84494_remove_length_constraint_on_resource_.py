"""Remove length constraint on resource descriptions

Revision ID: 9bc56ae84494
Revises: 7f512cdfc2f5
Create Date: 2020-04-30 15:35:24.647489

"""

# revision identifiers, used by Alembic.
revision = '9bc56ae84494'
down_revision = '7f512cdfc2f5'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.alter_column("tracker", "description", type_=sa.Unicode)
    op.alter_column("mailing_list", "description", type_=sa.Unicode)
    op.alter_column("source_repo", "description", type_=sa.Unicode)


def downgrade():
    op.alter_column("tracker", "description", type_=sa.Unicode(512))
    op.alter_column("mailing_list", "description", type_=sa.Unicode(512))
    op.alter_column("source_repo", "description", type_=sa.Unicode(512))
