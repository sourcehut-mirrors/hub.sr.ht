"""Set lists webhook_id to NOT NULL

Revision ID: 2e24bd9655ce
Revises: e4b380a0eb98
Create Date: 2025-01-24 10:49:27.462807

"""

# revision identifiers, used by Alembic.
revision = '2e24bd9655ce'
down_revision = 'e4b380a0eb98'

from alembic import op
import sqlalchemy as sa


def upgrade():
    # Part 2 of 2
    try:
        op.execute("""
        ALTER TABLE mailing_list
        ALTER COLUMN webhook_id SET NOT NULL,
        ALTER COLUMN webhook_version SET NOT NULL;
        """)
    except:
        print()
        print("You might have to run contrib/ensure-webhooks before applying this upgrade")
        print("https://git.sr.ht/~sircmpwn/hub.sr.ht/tree/master/item/contrib/ensure-webhooks")
        print("See notice on sr.ht-admins for more information")
        print()
        raise


def downgrade():
    op.execute("""
    ALTER TABLE mailing_list
    ALTER COLUMN webhook_id DROP NOT NULL,
    ALTER COLUMN webhook_version DROP NOT NULL;
    """)
