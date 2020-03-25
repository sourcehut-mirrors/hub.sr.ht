import sqlalchemy as sa
from srht.config import get_origin
from srht.database import Base

_listsrht = get_origin("lists.sr.ht", external=True, default=None)

class MailingList(Base):
    __tablename__ = "mailing_list"
    id = sa.Column(sa.Integer, primary_key=True)
    remote_id = sa.Column(sa.Integer, nullable=False)
    created = sa.Column(sa.DateTime, nullable=False)
    updated = sa.Column(sa.DateTime, nullable=False)

    project_id = sa.Column(sa.Integer,
            sa.ForeignKey("project.id"), nullable=False)
    project = sa.orm.relationship("Project",
            backref=sa.orm.backref("mailing_lists"),
            foreign_keys=[project_id])

    # Note: in theory this may eventually be different from the project owner(?)
    owner_id = sa.Column(sa.Integer,
            sa.ForeignKey("user.id"), nullable=False)
    owner = sa.orm.relationship("User")

    name = sa.Column(sa.Unicode(128), nullable=False)
    description = sa.Column(sa.Unicode(512), nullable=False)

    def url(self):
        return f"{_listsrht}/{self.owner.canonical_name}/{self.name}"
