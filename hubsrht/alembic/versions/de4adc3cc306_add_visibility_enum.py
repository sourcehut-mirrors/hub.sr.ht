"""Add visibility enum

Revision ID: de4adc3cc306
Revises: 5b1ac5bdb471
Create Date: 2022-06-16 01:32:20.691725

"""

# revision identifiers, used by Alembic.
revision = 'de4adc3cc306'
down_revision = '5b1ac5bdb471'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.execute("""
    CREATE TYPE visibility AS ENUM (
        'PUBLIC',
        'PRIVATE',
        'UNLISTED'
    );

    ALTER TABLE project
    ALTER COLUMN visibility DROP DEFAULT;
    ALTER TABLE project
    ALTER COLUMN visibility TYPE visibility USING upper(visibility)::visibility;
    ALTER TABLE project
    ALTER COLUMN visibility SET DEFAULT 'UNLISTED'::visibility;
    """)


def downgrade():
    op.execute("""
    ALTER TABLE project
    ALTER COLUMN visibility TYPE varchar USING lower(visibility::varchar);
    ALTER TABLE project
    ALTER COLUMN visibility SET DEFAULT 'unlisted';
    DROP TYPE visibility;
    """)
