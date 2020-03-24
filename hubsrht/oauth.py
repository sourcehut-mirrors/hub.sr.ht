from srht.config import cfg
from srht.oauth import AbstractOAuthService, DelegatedScope
from hubsrht.types import User

client_id = cfg("hub.sr.ht", "oauth-client-id")
client_secret = cfg("hub.sr.ht", "oauth-client-secret")

class HubOAuthService(AbstractOAuthService):
    def __init__(self):
        super().__init__(client_id, client_secret, user_class=User)
