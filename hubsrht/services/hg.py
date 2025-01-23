import json
from flask import url_for
from hubsrht.services import SrhtService
from markupsafe import Markup, escape
from srht.api import ensure_webhooks
from srht.config import get_origin, cfg
from srht.graphql import gql_time, GraphQLError
from srht.markdown import markdown, sanitize

origin = get_origin("hub.sr.ht")
_hgsrht = get_origin("hg.sr.ht", default=None)
_hgsrht_api = cfg("hg.sr.ht", "api-origin", default=None) or _hgsrht

class HgService(SrhtService):
    def __init__(self):
        super().__init__("hg.sr.ht")

    def get_repos(self, user):
        repos = self.enumerate(user, """
            query GetRepos($cursor: Cursor) {
                me {
                    repositories(cursor: $cursor) {
                        results {
                            id
                            name
                            updated
                            owner {
                                canonicalName
                            }
                        }
                        cursor
                    }
                }
            }
        """, collector=lambda result: result["me"]["repositories"])

        for repo in repos:
            repo["updated"] = gql_time(repo["updated"])

        return repos

    def get_repo(self, user, repo_name):
        resp = self.exec(user, """
            query GetRepo($repoName: String!) {
                me {
                    repository(name: $repoName) {
                        id
                        name
                        description
                        visibility
                    }
                }
            }
        """, repoName=repo_name)
        return resp["me"]["repository"]

    def get_readme(self, user, repo_name, repo_url):
        try:
            resp = self.exec(user, """
                query Readme($username: String!, $repoName: String!) {
                    user(username: $username) {
                        repository(name: $repoName) {
                            html: readme
                            md: cat(path: "README.md")
                            markdown: cat(path: "README.markdown")
                            plaintext: cat(path: "README")
                        }
                    }
                }
            """, username=user.username, repoName=repo_name)
        except GraphQLError as err:
            # hg.sr.ht returns an error if any of the requested paths cannot be
            # found. Ignore these errors.
            resp = err.data

        if not resp["user"]["repository"]:
            raise Exception("hg.sr.ht returned no repository: " +
                    json.dumps(r, indent=1))
        repo = resp["user"]["repository"]

        content = repo["html"]
        if content:
            return Markup(sanitize(content))

        content = repo["md"] or repo["markdown"]
        if content:
            html = markdown(content)
            return Markup(html)

        content = repo["plaintext"]
        if content:
            return Markup(f"<pre>{escape(content)}</pre>")

        return None

    def create_repo(self, user, valid, visibility):
        name = valid.require("name")
        description = valid.require("description")
        if not valid.ok:
            return None

        resp = self.exec(user, """
        mutation CreateRepo(
                $name: String!,
                $description: String!,
                $visibility: Visibility!) {
            createRepository(name: $name,
                    description: $description,
                    visibility: $visibility) {
                id, name, description, visibility
            }
        }
        """,
        name=name,
        description=description,
        visibility=visibility.value,
        valid=valid)

        if not valid.ok:
            return None

        return resp["createRepository"]

    def delete_repo(self, user, repo_id):
        self.exec(user, """
        mutation DeleteRepo($repo_id: Int!) {
            deleteRepository(id: $repo_id) { id }
        }
        """, repo_id=repo_id)

    def ensure_user_webhooks(self, user):
        config = {
            origin + url_for("webhooks.hg_user", user_id=user.id):
                ["repo:update", "repo:delete"],
        }
        ensure_webhooks(user, f"{_hgsrht}/api/user/webhooks", config)

    def unensure_user_webhooks(self, user):
        config = { }
        try:
            ensure_webhooks(user, f"{_hgsrht}/api/user/webhooks", config)
        except:
            pass # nbd, upstream was presumably deleted
