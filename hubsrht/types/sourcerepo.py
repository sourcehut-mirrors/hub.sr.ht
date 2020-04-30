import sqlalchemy as sa
import sqlalchemy_utils as sau
from enum import Enum
from hubsrht.types import Visibility
from srht.config import get_origin
from srht.database import Base

_gitsrht = get_origin("git.sr.ht", external=True, default=None)
_hgsrht = get_origin("hg.sr.ht", external=True, default=None)

class RepoType(Enum):
    git = "git"
    hg = "hg"

class SourceRepo(Base):
    __tablename__ = "source_repo"
    id = sa.Column(sa.Integer, primary_key=True)
    remote_id = sa.Column(sa.Integer, nullable=False)
    created = sa.Column(sa.DateTime, nullable=False)
    updated = sa.Column(sa.DateTime, nullable=False)

    project_id = sa.Column(sa.Integer,
            sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False)
    project = sa.orm.relationship("Project",
            backref=sa.orm.backref("source_repos", cascade="all, delete"),
            foreign_keys=[project_id])

    # Note: in theory this may eventually be different from the project owner(?)
    owner_id = sa.Column(sa.Integer,
            sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    owner = sa.orm.relationship("User")

    name = sa.Column(sa.Unicode(128), nullable=False)
    description = sa.Column(sa.Unicode, nullable=False)
    repo_type = sa.Column(sau.ChoiceType(RepoType, impl=sa.String()),
            nullable=False)
    visibility = sa.Column(sau.ChoiceType(Visibility, impl=sa.String()),
            nullable=False, server_default="unlisted")

    def url(self):
        origin = _gitsrht if self.repo_type == RepoType.git else _hgsrht
        return f"{origin}/{self.owner.canonical_name}/{self.name}"
