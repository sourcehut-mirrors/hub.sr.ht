"""Syncronize nullable columns with service policy

Revision ID: 5b1ac5bdb471
Revises: 9deca12b2917
Create Date: 2021-01-18 15:23:15.963586

"""

# revision identifiers, used by Alembic.
revision = '5b1ac5bdb471'
down_revision = '9deca12b2917'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.alter_column('mailing_list', 'description', nullable=True)
    op.alter_column('tracker', 'description', nullable=True)


def downgrade():
    op.alter_column('mailing_list', 'description', nullable=False)
    op.alter_column('tracker', 'description', nullable=False)
