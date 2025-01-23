"""Add webhook ID & version to lists

Revision ID: e4b380a0eb98
Revises: 7129b483a070
Create Date: 2025-01-23 11:59:02.381528

"""

# revision identifiers, used by Alembic.
revision = 'e4b380a0eb98'
down_revision = '7129b483a070'

from alembic import op
import sqlalchemy as sa


def upgrade():
    # Part 1 of 2, adds columns without NOT NULL
    op.execute("""
    ALTER TABLE mailing_list
    ADD COLUMN webhook_id integer,
    ADD COLUMN webhook_version integer;
    """)


def downgrade():
    op.execute("""
    ALTER TABLE mailing_list
    DROP COLUMN webhook_id,
    ADROPDD COLUMN webhook_version integer;
    """)
