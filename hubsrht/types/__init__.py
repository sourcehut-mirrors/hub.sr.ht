from srht.database import Base
from srht.oauth import ExternalUserMixin
from enum import Enum

class User(Base, ExternalUserMixin):
    pass

class Visibility(Enum):
    public = "public"
    unlisted = "unlisted"
    private = "private"

from hubsrht.types.event import Event, EventType
from hubsrht.types.feature import Feature
from hubsrht.types.mailinglist import MailingList
from hubsrht.types.project import Project
from hubsrht.types.sourcerepo import SourceRepo, RepoType
from hubsrht.types.tracker import Tracker
