import json
from flask import url_for
from hubsrht.services import SrhtService
from markupsafe import Markup, escape
from srht.api import ensure_webhooks
from srht.config import get_origin, cfg
from srht.graphql import gql_time, GraphQLError
from srht.markdown import markdown, sanitize

origin = get_origin("hub.sr.ht")
_gitsrht = get_origin("git.sr.ht", default=None)
_gitsrht_api = cfg("git.sr.ht", "api-origin", default=None) or _gitsrht

class GitService(SrhtService):
    def __init__(self):
        super().__init__("git.sr.ht")

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
            """,
            collector=lambda result: result["me"]["repositories"])

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
        resp = self.exec(user, """
            query Readme($username: String!, $repoName: String!) {
                user(username: $username) {
                    repository(name: $repoName) {
                        html: readme
                        md: path(path: "README.md") { ...textData }
                        markdown: path(path: "README.markdown") { ...textData }
                        plaintext: path(path: "README") { ...textData }
                    }
                }
            }

            fragment textData on TreeEntry {
                object {
                    ... on TextBlob {
                        text
                    }
                }
            }
            """,
            username=user.username, repoName=repo_name)

        if not resp["user"]["repository"]:
            raise Exception("git.sr.ht returned no repository: " +
                    json.dumps(r, indent=1))
        repo = resp["user"]["repository"]

        content = repo["html"]
        if content:
            return Markup(sanitize(content))

        content = repo["md"] or repo["markdown"]
        if content:
            blob_prefix = repo_url + "/blob/HEAD/"
            rendered_prefix = repo_url + "/tree/HEAD/"
            html = markdown(content["object"]["text"],
                    link_prefix=[rendered_prefix, blob_prefix])
            return Markup(html)

        content = repo["plaintext"]
        if content:
            content = content["object"]["text"]
            return Markup(f"<pre>{escape(content)}</pre>")

        return None

    def get_manifests(self, user, repo_name):
        resp = self.exec(user, """
            query Manifests($username: String!, $repo_name: String!) {
              user(username: $username) {
                repository(name: $repo_name) {
                  multiple: path(path:".builds") {
                    object {
                      ... on Tree {
                        entries {
                          results {
                            name
                            object { ... on TextBlob { text } }
                          }
                        }
                      }
                    }
                  },
                  singleYML: path(path:".build.yml") {
                    object {
                      ... on TextBlob { text }
                    }
                  },
                  singleYAML: path(path:".build.yaml") {
                    object {
                      ... on TextBlob { text }
                    }
                  }
                }
              }
            }
            """, username=user.username, repo_name=repo_name)

        if not resp["user"]["repository"]:
            raise Exception(f"git.sr.ht did not find repo {repo_name} (requesting on behalf of {user.username})\n" +
                    json.dumps(r, indent=1))
        repo = resp["user"]["repository"]

        manifests = dict()

        if repo["multiple"]:
            for ent in repo["multiple"]["object"]["entries"]["results"]:
                if not ent["object"]:
                    continue
                manifests[ent["name"]] = ent["object"]["text"]
        elif repo["singleYML"]:
            manifests[".build.yml"] = repo["singleYML"]["object"]["text"]
        elif repo["singleYAML"]:
            manifests[".build.yaml"] = repo["singleYAML"]["object"]["text"]
        else:
            return None

        return manifests

    def log(self, user, repo, old, new):
        resp = self.exec(user, """
            query Log($username: String!, $repo: String!, $from: String!) {
                user(username: $username) {
                    repository(name: $repo) {
                        log(from: $from) {
                            results {
                                id
                                message
                                author {
                                    name
                                }
                            }
                        }
                    }
                }
            }
            """, **{
                "username": repo.owner.username,
                "repo": repo.name,
                "from": new,
            })

        commits = []
        for c in resp["user"]["repository"]["log"]["results"]:
            if c["id"] == old:
                break
            commits.append(c)
        return commits

    def create_repo(self, user, valid, visibility):
        name = valid.require("name")
        description = valid.require("description")
        if not valid.ok:
            return None

        resp = self.exec(user, """
            mutation CreateRepo(
                    $name: String!,
                    $description: String,
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
            origin + url_for("webhooks.git_user", user_id=user.id):
                ["repo:update", "repo:delete"],
        }
        ensure_webhooks(user, f"{_gitsrht}/api/user/webhooks", config)

    def unensure_user_webhooks(self, user):
        config = {
            origin + url_for("webhooks.git_user", user_id=user.id): None
        }
        try:
            ensure_webhooks(user, f"{_gitsrht}/api/user/webhooks", config)
        except:
            pass # nbd, upstream was probably deleted

    def ensure_repo_webhooks(self, repo):
        config = {
            origin + url_for("webhooks.git_repo", repo_id=repo.id):
                ["repo:post-update"],
        }
        owner = repo.owner
        url = f"{_gitsrht}/api/{owner.canonical_name}/repos/{repo.name}/webhooks"
        ensure_webhooks(owner, url, config)

    def unensure_repo_webhooks(self, repo):
        config = {
            origin + url_for("webhooks.git_repo", repo_id=repo.id): None
        }
        owner = repo.owner
        url = f"{_gitsrht}/api/{owner.canonical_name}/repos/{repo.name}/webhooks"
        try:
            ensure_webhooks(owner, url, config)
        except:
            pass # nbd, upstream was presumably deleted
