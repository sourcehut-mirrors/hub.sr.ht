import sqlalchemy as sa
import sqlalchemy_utils as sau
from enum import Enum
from srht.database import Base

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
            sa.ForeignKey("project.id"), nullable=False)
    project = sa.orm.relationship("Project",
            backref=sa.orm.backref("source_repos"),
            foreign_keys=[project_id])

    # Note: in theory this may eventually be different from the project owner(?)
    owner_id = sa.Column(sa.Integer,
            sa.ForeignKey("user.id"), nullable=False)
    owner = sa.orm.relationship("User")

    name = sa.Column(sa.Unicode(128), nullable=False)
    description = sa.Column(sa.Unicode(512), nullable=False)
    repo_type = sa.Column(sau.ChoiceType(RepoType, impl=sa.String()),
            nullable=False)
