"""Reconfigure user webhooks

Revision ID: e748f55a827c
Revises: 9a939f5d527e
Create Date: 2022-07-18 10:49:42.704659

"""

# revision identifiers, used by Alembic.
revision = 'e748f55a827c'
down_revision = '9a939f5d527e'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker
from flask import url_for
from srht.api import ensure_webhooks
from srht.config import get_origin
from srht.crypto import internal_anon
from srht.database import db
from srht.graphql import exec_gql
from hubsrht.app import app

Base = declarative_base()

app.config['SERVER_NAME'] = ''

_gitsrht = get_origin("git.sr.ht", external=True, default=None)
_hgsrht = get_origin("hg.sr.ht", external=True, default=None)
_todosrht = get_origin("todo.sr.ht", external=True, default=None)
origin = get_origin("hub.sr.ht")

class User(Base):
    __tablename__ = "user"
    id = sa.Column(sa.Integer, primary_key=True)
    old_id = sa.Column(sa.Integer, unique=True)
    username = sa.Column(sa.Unicode(256), index=True, unique=True)

def reconfigure_webhooks(user, old_id, id):
    # git user webhooks
    if _gitsrht:
        ensure_webhooks(user, f"{_gitsrht}/api/user/webhooks", {
            origin + url_for("webhooks.git_user", user_id=old_id, _external=False): None,
            origin + url_for("webhooks.git_user", user_id=id, _external=False):
                ["repo:update", "repo:delete"],
        })

    # hg user webhooks
    if _hgsrht:
        ensure_webhooks(user, f"{_hgsrht}/api/user/webhooks", {
            origin + url_for("webhooks.hg_user", user_id=old_id, _external=False): None,
            origin + url_for("webhooks.hg_user", user_id=id, _external=False):
                ["repo:update", "repo:delete"],
        })

    # todo user webhooks
    if _todosrht:
        ensure_webhooks(user, f"{_todosrht}/api/user/webhooks", {
            origin + url_for("webhooks.todo_user", user_id=old_id, _external=False): None,
            origin + url_for("webhooks.todo_user", user_id=id, _external=False):
                ["tracker:update", "tracker:delete"],
        })

    print(f"Reconfigured ~{user.username} webhooks: {old_id} -> {id}")

def upgrade():
    engine = op.get_bind()
    session = scoped_session(sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine))
    Base.query = session.query_property()

    with app.app_context():
        for user in User.query:
            reconfigure_webhooks(user, user.old_id, user.id)
    session.commit()

def downgrade():
    engine = op.get_bind()
    session = scoped_session(sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine))
    Base.query = session.query_property()

    with app.app_context():
        for user in User.query:
            reconfigure_webhooks(user, user.id, user.old_id)
    session.commit()
