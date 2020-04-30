import sqlalchemy as sa
import sqlalchemy_utils as sau
from hubsrht.types import Visibility
from srht.database import Base

class Project(Base):
    __tablename__ = "project"
    id = sa.Column(sa.Integer, primary_key=True)
    created = sa.Column(sa.DateTime, nullable=False)
    updated = sa.Column(sa.DateTime, nullable=False)

    owner_id = sa.Column(sa.Integer,
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False)
    owner = sa.orm.relationship("User",
            backref=sa.orm.backref("projects", cascade="all, delete"))

    name = sa.Column(sa.Unicode(128), nullable=False)
    description = sa.Column(sa.Unicode(512), nullable=False)
    website = sa.Column(sa.Unicode)
    visibility = sa.Column(sau.ChoiceType(Visibility, impl=sa.String()),
            nullable=False, server_default="unlisted")

    checklist_complete = sa.Column(sa.Boolean,
            nullable=False, server_default='f')

    summary_repo_id = sa.Column(sa.Integer,
            sa.ForeignKey("source_repo.id", ondelete="CASCADE"))
    summary_repo = sa.orm.relationship("SourceRepo",
            foreign_keys=[summary_repo_id],
            cascade="all, delete",
            post_update=True)
