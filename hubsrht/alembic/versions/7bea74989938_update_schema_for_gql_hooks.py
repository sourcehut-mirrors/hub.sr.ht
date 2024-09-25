"""Update schema for GQL hooks

Revision ID: 7bea74989938
Revises: 9cfb231405a9
Create Date: 2024-09-24 14:58:11.845757

"""

# revision identifiers, used by Alembic.
revision = '7bea74989938'
down_revision = '9cfb231405a9'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.execute("""
    CREATE TABLE user_service_webhooks (
    	id serial PRIMARY KEY,
    	git_hook_id integer,
    	hg_hook_id integer,
    	list_hook_id integer,
    	todo_hook_id integer
    );

    ALTER TABLE "user" ADD COLUMN
        user_hooks integer REFERENCES user_service_webhooks(id);

    ALTER TABLE mailing_list
        ADD COLUMN remote_hook_id integer;
    ALTER TABLE source_repo
        ADD COLUMN remote_hook_id integer;
    ALTER TABLE tracker
        ADD COLUMN remote_hook_id integer;
    """)


def downgrade():
    op.execute("""
    DROP TABLE "user" DROP COLUMN user_hooks integer;
    DROP TABLE user_service_webhooks;

    ALTER TABLE mailing_list
        DROP COLUMN remote_hook_id integer;
    ALTER TABLE source_repo
        DROP COLUMN remote_hook_id integer;
    ALTER TABLE tracker
        DROP COLUMN remote_hook_id integer;
    """)
