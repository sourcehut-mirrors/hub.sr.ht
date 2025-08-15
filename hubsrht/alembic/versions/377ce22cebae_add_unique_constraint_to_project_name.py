"""Add unique constraint to project name

Revision ID: 377ce22cebae
Revises: 1e87a87d2c63
Create Date: 2025-08-15 09:22:43.565267

"""

# revision identifiers, used by Alembic.
revision = '377ce22cebae'
down_revision = '1e87a87d2c63'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.execute("""
    CREATE UNIQUE INDEX
    project_owner_id_name_key
    ON project (owner_id, name);
    """)


def downgrade():
    op.execute("""
    DROP INDEX project_owner_id_name_key;
    """)
