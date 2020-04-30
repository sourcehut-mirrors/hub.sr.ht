import requests
from abc import ABC
from flask import url_for
from srht.api import ensure_webhooks, get_authorization, get_results
from srht.config import get_origin

_gitsrht = get_origin("git.sr.ht", external=True, default=None)
_hgsrht = get_origin("hg.sr.ht", external=True, default=None)
_listsrht = get_origin("lists.sr.ht", external=True, default=None)
_todosrht = get_origin("todo.sr.ht", external=True, default=None)
origin = get_origin("hub.sr.ht")

class SrhtService(ABC):
    def __init__(self):
        self.session = requests.Session()

    def post(self, user, valid, url, payload):
        r = self.session.post(url,
            headers=get_authorization(user),
            json=payload)
        if r.status_code == 400:
            for error in r.json()["errors"]:
                valid.error(error["reason"], field=error.get("field"))
            return None
        elif r.status_code != 201:
            raise Exception(r.text)
        return r.json()

class GitService(SrhtService):
    def __init__(self):
        super().__init__()

    def get_repos(self, user):
        return get_results(f"{_gitsrht}/api/repos", user)

    def get_repo(self, user, repo_name):
        r = self.session.get(f"{_gitsrht}/api/repos/{repo_name}",
                headers=get_authorization(user))
        if r.status_code != 200:
            raise Exception(r.text)
        return r.json()

    def get_readme(self, user, repo_name):
        # TODO: Cache?
        # TODO: Use default branch
        r = self.session.get(f"{_gitsrht}/api/repos/{repo_name}/blob/master/README.md",
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
        return self.post(user, valid, f"{_gitsrht}/api/repos", {
            "name": name,
            "description": description,
            "visibility": "public", # TODO: Should this be different?
        })

    def delete_repo(self, user, repo_name):
        r = self.session.delete(f"{_gitsrht}/api/repos/{repo_name}",
                headers=get_authorization(user))
        if r.status_code != 204:
            raise Exception(r.text)

    def ensure_user_webhooks(self, user):
        config = {
            origin + url_for("webhooks.git_user", user_id=user.id):
                ["repo:update", "repo:delete"],
        }
        ensure_webhooks(user, f"{_gitsrht}/api/user/webhooks", config)

    def ensure_user_webhooks(self, user):
        config = { }
        ensure_webhooks(user, f"{_gitsrht}/api/user/webhooks", config)

    def ensure_repo_webhooks(self, repo):
        config = {
            origin + url_for("webhooks.git_repo", repo_id=repo.id):
                ["repo:post-update"],
        }
        owner = repo.owner
        url = f"{_gitsrht}/api/{owner.canonical_name}/repos/{repo.name}/webhooks"
        ensure_webhooks(owner, url, config)

    def unensure_repo_webhooks(self, repo):
        config = { }
        owner = repo.owner
        url = f"{_gitsrht}/api/{owner.canonical_name}/repos/{repo.name}/webhooks"
        ensure_webhooks(owner, url, config)

class HgService(SrhtService):
    def __init__(self):
        super().__init__()

    def get_repos(self, user):
        return get_results(f"{_hgsrht}/api/repos", user)

    def get_repo(self, user, repo_name):
        r = self.session.get(f"{_hgsrht}/api/repos/{repo_name}",
                headers=get_authorization(user))
        if r.status_code != 200:
            raise Exception(r.text)
        return r.json()

    def get_readme(self, user, repo_name):
        # TODO: Cache?
        r = self.session.get(f"{_hgsrht}/api/repos/{repo_name}/raw/README.md",
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
        return self.post(user, valid, f"{_hgsrht}/api/repos", {
            "name": name,
            "description": description,
            "visibility": "public", # TODO: Should this be different?
        })

    def delete_repo(self, user, repo_name):
        r = self.session.delete(f"{_hgsrht}/api/repos/{repo_name}",
                headers=get_authorization(user))
        if r.status_code != 204:
            raise Exception(r.text)

    def ensure_user_webhooks(self, user):
        config = {
            origin + url_for("webhooks.hg_user", user_id=user.id):
                ["repo:update", "repo:delete"],
        }
        ensure_webhooks(user, f"{_hgsrht}/api/user/webhooks", config)

    def unensure_user_webhooks(self, user):
        config = { }
        ensure_webhooks(user, f"{_hgsrht}/api/user/webhooks", config)

class ListService(SrhtService):
    def get_lists(self, user):
        return get_results(f"{_listsrht}/api/lists", user)

    def get_list(self, user, list_name):
        r = self.session.get(f"{_listsrht}/api/lists/{list_name}",
                headers=get_authorization(user))
        if r.status_code != 200:
            raise Exception(r.json())
        return r.json()

    def ensure_mailing_list_webhooks(self, mailing_list):
        config = {
            origin + url_for("webhooks.mailing_list", list_id=mailing_list.id):
                ["list:update", "list:delete", "post:received", "patchset:received"],
        }
        owner = mailing_list.owner
        url = f"{_listsrht}/api/user/{owner.canonical_name}/lists/{mailing_list.name}/webhooks"
        ensure_webhooks(owner, url, config)

    def unensure_mailing_list_webhooks(self, mailing_list):
        config = { }
        owner = mailing_list.owner
        url = f"{_listsrht}/api/user/{owner.canonical_name}/lists/{mailing_list.name}/webhooks"
        ensure_webhooks(owner, url, config)

    def create_list(self, user, valid):
        name = valid.require("name")
        description = valid.optional("description")
        if not valid.ok:
            return None
        return self.post(user, valid, f"{_listsrht}/api/lists", {
            "name": name,
            "description": description,
        })

class TodoService(SrhtService):
    def get_trackers(self, user):
        return get_results(f"{_todosrht}/api/trackers", user)

    def get_tracker(self, user, tracker_name):
        r = self.session.get(f"{_todosrht}/api/trackers/{tracker_name}",
                headers=get_authorization(user))
        if r.status_code != 200:
            raise Exception(r.json())
        return r.json()

    def create_tracker(self, user, valid):
        name = valid.require("name")
        description = valid.optional("description")
        if not valid.ok:
            return None
        return self.post(user, valid, f"{_todosrht}/api/trackers", {
            "name": name,
            "description": description,
        })

    def delete_tracker(self, user, tracker_name):
        r = self.session.delete(f"{_todosrht}/api/trackers/{tracker_name}",
                headers=get_authorization(user))
        if r.status_code != 204:
            raise Exception(r.text)

    def ensure_user_webhooks(self, user):
        config = {
            origin + url_for("webhooks.todo_user", user_id=user.id):
                ["tracker:update", "tracker:delete"]
        }
        url = f"{_todosrht}/api/user/webhooks"
        ensure_webhooks(user, url, config)

    def unensure_user_webhooks(self, user):
        config = { }
        url = f"{_todosrht}/api/user/webhooks"
        ensure_webhooks(user, url, config)

    def ensure_tracker_webhooks(self, tracker):
        config = {
            origin + url_for("webhooks.todo_tracker", tracker_id=tracker.id):
                ["ticket:create"]
        }
        owner = tracker.owner
        url = f"{_todosrht}/api/user/{owner.canonical_name}/trackers/{tracker.name}/webhooks"
        ensure_webhooks(owner, url, config)

    def unensure_tracker_webhooks(self, tracker):
        config = { }
        owner = tracker.owner
        url = f"{_todosrht}/api/user/{owner.canonical_name}/trackers/{tracker.name}/webhooks"
        ensure_webhooks(owner, url, config)

    def ensure_ticket_webhooks(self, tracker, ticket_id):
        config = {
            origin + url_for("webhooks.todo_ticket", tracker_id=tracker.id):
                ["event:create"]
        }
        owner = tracker.owner
        url = f"{_todosrht}/api/user/{owner.canonical_name}/trackers/{tracker.name}/tickets/{ticket_id}/webhooks"
        ensure_webhooks(owner, url, config)

    def unensure_ticket_webhooks(self, tracker, ticket_id):
        config = { }
        owner = tracker.owner
        url = f"{_todosrht}/api/user/{owner.canonical_name}/trackers/{tracker.name}/tickets/{ticket_id}/webhooks"
        ensure_webhooks(owner, url, config)

    def create_tracker(self, user, valid):
        name = valid.require("name")
        description = valid.optional("description")
        if not valid.ok:
            return None
        return self.post(user, valid, f"{_todosrht}/api/trackers", {
            "name": name,
            "description": description,
        })

git = GitService()
hg = HgService()
lists = ListService()
todo = TodoService()
