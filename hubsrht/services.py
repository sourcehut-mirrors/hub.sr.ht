import requests
from srht.api import ensure_webhooks, get_authorization, get_results
from srht.config import get_origin

_gitsrht = get_origin("git.sr.ht", external=True, default=None)

class GitService:
    def get_repos(self, user):
        return get_results(f"{_gitsrht}/api/repos", user)

    def get_repo(self, user, repo_name):
        r = requests.get(f"{_gitsrht}/api/repos/{repo_name}",
                headers=get_authorization(user))
        if r.status_code != 200:
            raise Exception(r.json())
        return r.json()

    def ensure_user_webhooks(self, user, config):
        ensure_webhooks(user, f"{_gitsrht}/api/user/webhooks", config)

git = GitService()
