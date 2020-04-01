from hubsrht.oauth import HubOAuthService
from srht.config import cfg
from srht.database import DbSession
from srht.flask import SrhtFlask

db = DbSession(cfg("hub.sr.ht", "connection-string"))
db.init()

class HubApp(SrhtFlask):
    def __init__(self):
        super().__init__("hub.sr.ht", __name__,
                oauth_service=HubOAuthService())

        from hubsrht.blueprints.projects import projects
        from hubsrht.blueprints.public import public
        from hubsrht.blueprints.sources import sources
        from hubsrht.blueprints.users import users
        from hubsrht.blueprints.webhooks import webhooks

        self.register_blueprint(projects)
        self.register_blueprint(public)
        self.register_blueprint(sources)
        self.register_blueprint(users)
        self.register_blueprint(webhooks)

app = HubApp()
