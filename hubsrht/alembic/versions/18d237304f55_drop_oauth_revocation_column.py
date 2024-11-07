"""Drop oauth_revocation column

Revision ID: 18d237304f55
Revises: 7bea74989938
Create Date: 2024-11-07 12:10:57.345924

"""

# revision identifiers, used by Alembic.
revision = '18d237304f55'
down_revision = '7bea74989938'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.execute("""
    ALTER TABLE "user" DROP COLUMN oauth_revocation_token;
    """)


def downgrade():
    op.execute("""
    ALTER TABLE "user"
    ADD COLUMN oauth_revocation_token character varying(256);
    """)
