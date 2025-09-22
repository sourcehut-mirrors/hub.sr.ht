from flask import url_for
from srht.config import get_origin
from srht.api import ensure_webhooks

_origin = get_origin("hub.sr.ht")
_gitsrht = get_origin("git.sr.ht", default=None)

def ensure_user_webhooks(user):
    config = {
        _origin + url_for("webhooks.git_user", user_id=user.id):
            ["repo:update", "repo:delete"],
    }
    ensure_webhooks(user, f"{_gitsrht}/api/user/webhooks", config)

def unensure_user_webhooks(user):
    config = {
        _origin + url_for("webhooks.git_user", user_id=user.id): None
    }
    try:
        ensure_webhooks(user, f"{_gitsrht}/api/user/webhooks", config)
    except:
        pass # nbd, upstream was probably deleted

def ensure_repo_webhooks(repo):
    config = {
        _origin + url_for("webhooks.git_repo", repo_id=repo.id):
            ["repo:post-update"],
    }
    owner = repo.owner
    url = f"{_gitsrht}/api/{owner.canonical_name}/repos/{repo.name}/webhooks"
    ensure_webhooks(owner, url, config)

def unensure_repo_webhooks(repo):
    config = {
        _origin + url_for("webhooks.git_repo", repo_id=repo.id): None
    }
    owner = repo.owner
    url = f"{_gitsrht}/api/{owner.canonical_name}/repos/{repo.name}/webhooks"
    try:
        ensure_webhooks(owner, url, config)
    except:
        pass # nbd, upstream was presumably deleted
