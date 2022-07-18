"""Use canonical user ID

Revision ID: 9a939f5d527e
Revises: 1cdfad7c20b8
Create Date: 2022-06-16 15:14:10.901524

"""

# revision identifiers, used by Alembic.
revision = '9a939f5d527e'
down_revision = '1cdfad7c20b8'

from alembic import op
import sqlalchemy as sa


# These tables all have a column referencing "user"(id)
tables = [
    ("event", "user_id"),
    ("mailing_list", "owner_id"),
    ("project", "owner_id"),
    ("source_repo", "owner_id"),
    ("tracker", "owner_id"),
]

def upgrade():
    # Drop foreign key constraints and update user IDs
    for (table, col) in tables:
        op.execute(f"""
        ALTER TABLE {table} DROP CONSTRAINT {table}_{col}_fkey;
        UPDATE {table} t SET {col} = u.remote_id FROM "user" u WHERE u.id = t.{col};
        """)

    # Update primary key
    op.execute("""
    ALTER TABLE "user" DROP CONSTRAINT user_pkey;
    ALTER TABLE "user" DROP CONSTRAINT user_remote_id_key;
    ALTER TABLE "user" RENAME COLUMN id TO old_id;
    ALTER TABLE "user" RENAME COLUMN remote_id TO id;
    ALTER TABLE "user" ADD PRIMARY KEY (id);
    ALTER TABLE "user" ADD UNIQUE (old_id);
    """)

    # Add foreign key constraints
    for (table, col) in tables:
        op.execute(f"""
        ALTER TABLE {table} ADD CONSTRAINT {table}_{col}_fkey FOREIGN KEY ({col}) REFERENCES "user"(id) ON DELETE CASCADE;
        """)


def downgrade():
    # Drop foreign key constraints and update user IDs
    for (table, col) in tables:
        op.execute(f"""
        ALTER TABLE {table} DROP CONSTRAINT {table}_{col}_fkey;
        UPDATE {table} t SET {col} = u.old_id FROM "user" u WHERE u.id = t.{col};
        """)

    # Update primary key
    op.execute("""
    ALTER TABLE "user" DROP CONSTRAINT user_pkey;
    ALTER TABLE "user" DROP CONSTRAINT user_old_id_key;
    ALTER TABLE "user" RENAME COLUMN id TO remote_id;
    ALTER TABLE "user" RENAME COLUMN old_id TO id;
    ALTER TABLE "user" ADD PRIMARY KEY (id);
    ALTER TABLE "user" ADD UNIQUE (remote_id);
    """)

    # Add foreign key constraints
    for (table, col) in tables:
        op.execute(f"""
        ALTER TABLE {table} ADD CONSTRAINT {table}_{col}_fkey FOREIGN KEY ({col}) REFERENCES "user"(id) ON DELETE CASCADE;
        """)
