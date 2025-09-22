from flask import url_for
from srht.config import get_origin
from srht.api import ensure_webhooks

_origin = get_origin("hub.sr.ht")
_todosrht = get_origin("todo.sr.ht", default=None)

def ensure_user_webhooks(user):
    config = {
        _origin + url_for("webhooks.todo_user", user_id=user.id):
            ["tracker:update", "tracker:delete"]
    }
    url = f"{_todosrht}/api/user/webhooks"
    ensure_webhooks(user, url, config)

def unensure_user_webhooks(user):
    config = {
         _origin + url_for("webhooks.todo_user", user_id=user.id): None
    }
    url = f"{_todosrht}/api/user/webhooks"
    try:
        ensure_webhooks(user, url, config)
    except:
        pass # nbd, upstream was presumably deleted

def ensure_tracker_webhooks(tracker):
    config = {
        _origin + url_for("webhooks.todo_tracker", tracker_id=tracker.id):
            ["ticket:create"]
    }
    owner = tracker.owner
    url = f"{_todosrht}/api/user/{owner.canonical_name}/trackers/{tracker.name}/webhooks"
    ensure_webhooks(owner, url, config)

def unensure_tracker_webhooks(tracker):
    config = {
        _origin + url_for("webhooks.todo_tracker", tracker_id=tracker.id): None
    }
    owner = tracker.owner
    url = f"{_todosrht}/api/user/{owner.canonical_name}/trackers/{tracker.name}/webhooks"
    try:
        ensure_webhooks(owner, url, config)
    except:
        pass # nbd, upstream was presumably deleted

def ensure_ticket_webhooks(tracker, ticket_id):
    config = {
        _origin + url_for("webhooks.todo_ticket", tracker_id=tracker.id):
            ["event:create"]
    }
    owner = tracker.owner
    url = f"{_todosrht}/api/user/{owner.canonical_name}/trackers/{tracker.name}/tickets/{ticket_id}/webhooks"
    ensure_webhooks(owner, url, config)

def unensure_ticket_webhooks(tracker, ticket_id):
    config = { }
    owner = tracker.owner
    url = f"{_todosrht}/api/user/{owner.canonical_name}/trackers/{tracker.name}/tickets/{ticket_id}/webhooks"
    try:
        ensure_webhooks(owner, url, config)
    except:
        pass # nbd, upstream was presumably deleted
