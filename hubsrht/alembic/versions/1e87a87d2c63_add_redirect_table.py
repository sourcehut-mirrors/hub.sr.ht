"""Add redirect table

Revision ID: 1e87a87d2c63
Revises: 2e24bd9655ce
Create Date: 2024-12-06 10:31:42.164799
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "1e87a87d2c63"
down_revision = "2e24bd9655ce"


def upgrade():
    op.execute("""
    CREATE TABLE redirect (
        id serial PRIMARY KEY,
        created timestamp without time zone NOT NULL,
        name character varying(256) NOT NULL,
        owner_id integer NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
        new_project_id integer NOT NULL REFERENCES project(id) ON DELETE CASCADE
    );
    """
    )


def downgrade():
    op.execute("DROP TABLE redirect;")
