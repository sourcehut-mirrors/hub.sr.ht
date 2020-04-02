import sqlalchemy as sa
import sqlalchemy_utils as sau
from enum import Enum
from srht.database import Base

class EventType(Enum):
    source_repo_added = "source_repo_added"
    mailing_list_added = "mailing_list_added"
    tracker_added = "tracker_added"
    external_event = "external_event"

class Event(Base):
    __tablename__ = "events"
    id = sa.Column(sa.Integer, primary_key=True)
    created = sa.Column(sa.DateTime, nullable=False)

    project_id = sa.Column(sa.Integer,
            sa.ForeignKey("project.id", ondelete="CASCADE"),
            nullable=False)
    project = sa.orm.relationship("Project",
            backref=sa.orm.backref("events", cascade="all, delete"))
    """The project implicated in this event"""

    user_id = sa.Column(sa.Integer,
            sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    user = sa.orm.relationship("User", backref=sa.orm.backref("events"),
            cascade="all, delete")
    """The user implicated in this event"""

    event_type = sa.Column(sau.ChoiceType(EventType, impl=sa.String()),
            nullable=False)

    source_repo_id = sa.Column(sa.Integer,
            sa.ForeignKey("source_repo.id", ondelete="CASCADE"))
    source_repo = sa.orm.relationship("SourceRepo", cascade="all, delete")
    """The source repository implicated in this event, if applicable"""

    mailing_list_id = sa.Column(sa.Integer,
            sa.ForeignKey("mailing_list.id", ondelete="CASCADE"))
    mailing_list = sa.orm.relationship("MailingList", cascade="all, delete")
    """The mailing list implicated in this event, if applicable"""

    tracker_id = sa.Column(sa.Integer,
            sa.ForeignKey("tracker.id", ondelete="CASCADE"))
    tracker = sa.orm.relationship("Tracker", cascade="all, delete")
    """The ticket tracker implicated in this event, if applicable"""

    external_source = sa.Column(sa.Unicode) # e.g. "lists.sr.ht"
    external_summary = sa.Column(sa.Unicode) # markdown
    external_details = sa.Column(sa.Unicode) # markdown
