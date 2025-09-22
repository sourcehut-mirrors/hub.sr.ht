from flask import url_for
from srht.config import get_origin
from srht.api import ensure_webhooks

_origin = get_origin("hub.sr.ht")
_hgsrht = get_origin("hg.sr.ht", default=None)

def ensure_user_webhooks(user):
    config = {
        _origin + url_for("webhooks.hg_user", user_id=user.id):
            ["repo:update", "repo:delete"],
    }
    ensure_webhooks(user, f"{_hgsrht}/api/user/webhooks", config)

def unensure_user_webhooks(user):
    config = {
        _origin + url_for("webhooks.hg_user", user_id=user.id): None
    }
    try:
        ensure_webhooks(user, f"{_hgsrht}/api/user/webhooks", config)
    except:
        pass # nbd, upstream was presumably deleted
