"""Expand external events

Revision ID: 9cfb231405a9
Revises: e748f55a827c
Create Date: 2022-11-14 18:00:00.000000

"""

# revision identifiers, used by Alembic.
revision = '9cfb231405a9'
down_revision = 'e748f55a827c'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.execute("""
    ALTER TABLE "event"
    ADD COLUMN external_summary_plain character varying,
    ADD COLUMN external_details_plain character varying,
    ADD COLUMN external_url character varying;
    """)


def downgrade():
    op.execute("""
    ALTER TABLE "event"
    DROP COLUMN external_summary_plain,
    DROP COLUMN external_details_plain,
    DROP COLUMN external_url;
    """)
