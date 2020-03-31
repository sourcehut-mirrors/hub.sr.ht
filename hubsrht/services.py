import requests
from srht.api import ensure_webhooks, get_authorization, get_results
from srht.config import get_origin

_gitsrht = get_origin("git.sr.ht", external=True, default=None)
_listsrht = get_origin("lists.sr.ht", external=True, default=None)

class GitService:
    def get_repos(self, user):
        return get_results(f"{_gitsrht}/api/repos", user)

    def get_repo(self, user, repo_name):
        r = requests.get(f"{_gitsrht}/api/repos/{repo_name}",
                headers=get_authorization(user))
        if r.status_code != 200:
            raise Exception(r.text)
        return r.json()

    def get_readme(self, user, repo_name):
        # TODO: Cache?
        # TODO: Use default branch
        r = requests.get(f"{_gitsrht}/api/repos/{repo_name}/blob/master/README.md",
                headers=get_authorization(user))
        if r.status_code == 404:
            return ""
        elif r.status_code != 200:
            raise Exception(r.text)
        return r.text

    def create_repo(self, user, valid):
        name = valid.require("name")
        description = valid.require("description")
        if not valid.ok:
            return None
        r = requests.post(f"{_gitsrht}/api/repos",
            headers=get_authorization(user),
            json={
                "name": name,
                "description": description,
                "visibility": "public", # TODO: Should this be different?
            })
        if r.status_code == 400:
            for error in r.json()["errors"]:
                valid.error(error["reason"], field=error.get("field"))
            return None
        elif r.status_code != 201:
            raise Exception(r.text)
        return r.json()

    def ensure_user_webhooks(self, user, config):
        ensure_webhooks(user, f"{_gitsrht}/api/user/webhooks", config)

class ListService():
    def get_lists(self, user):
        return get_results(f"{_listsrht}/api/lists", user)

    def get_list(self, user, list_name):
        r = requests.get(f"{_listsrht}/api/lists/{list_name}",
                headers=get_authorization(user))
        if r.status_code != 200:
            raise Exception(r.json())
        return r.json()

    def ensure_mailing_list_webhooks(self, user, list_name, config):
        url = f"{_listsrht}/api/user/{user.canonical_name}/lists/{list_name}/webhooks"
        ensure_webhooks(user, url, config)

git = GitService()
lists = ListService()
