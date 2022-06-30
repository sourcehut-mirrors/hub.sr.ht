"""Add visibility to resources

Revision ID: 7f512cdfc2f5
Revises: None
Create Date: 2020-04-29 12:44:42.864699

"""

# revision identifiers, used by Alembic.
revision = '7f512cdfc2f5'
down_revision = None

from alembic import op
import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker
from hubsrht.app import app
from hubsrht.types import SourceRepo, Tracker, MailingList, RepoType, Visibility
from hubsrht.services import git, hg, todo, lists

Session = sessionmaker()

def upgrade():
    op.add_column('tracker', sa.Column('visibility', sa.String(),
            nullable=False, server_default="unlisted"))
    op.add_column('mailing_list', sa.Column('visibility', sa.String(),
            nullable=False, server_default="unlisted"))
    op.add_column('source_repo', sa.Column('visibility', sa.String(),
            nullable=False, server_default="unlisted"))
    bind = op.get_bind()
    session = Session(bind=bind)
    with app.app_context():
        for repo in session.query(SourceRepo).all():
            if repo.repo_type == RepoType.git:
                r = git.get_repo(repo.owner, repo.name)
            elif repo.repo_type == RepoType.hg:
                r = hg.get_repo(repo.owner, repo.name)
            else:
                assert False
            repo.visibility = Visibility(r["visibility"])

        for ml in session.query(MailingList).all():
            m = lists.get_list(ml.owner, ml.name)
            if any(m["permissions"]["nonsubscriber"]):
                ml.visibility = Visibility.PUBLIC
            else:
                ml.visibility = Visibility.UNLISTED

        for tracker in session.query(Tracker).all():
            t = todo.get_tracker(tracker.owner, tracker.name)
            if any(t["default_permissions"]["anonymous"]):
                tracker.visibility = Visibility.PUBLIC
            else:
                tracker.visibility = Visibility.UNLISTED

        session.commit()

def downgrade():
    op.drop_column('tracker', 'visibility')
    op.drop_column('mailing_list', 'visibility')
    op.drop_column('source_repo', 'visibility')
