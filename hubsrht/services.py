import json
import requests
import yaml
from flask import url_for
from markupsafe import Markup, escape
from srht.api import ensure_webhooks
from srht.config import get_origin, cfg
from srht.graphql import gql_time, exec_gql, GraphQLError
from srht.markdown import markdown, sanitize
from typing import Any, Callable

_gitsrht = get_origin("git.sr.ht", default=None)
_gitsrht_api = cfg("git.sr.ht", "api-origin", default=None) or _gitsrht
_hgsrht = get_origin("hg.sr.ht", default=None)
_hgsrht_api = cfg("hg.sr.ht", "api-origin", default=None) or _hgsrht
_listsrht = get_origin("lists.sr.ht", default=None)
_listsrht_api = cfg("lists.sr.ht", "api-origin", default=None) or _listsrht
_todosrht = get_origin("todo.sr.ht", default=None)
_todosrht_api = cfg("todo.sr.ht", "api-origin", default=None) or _todosrht
_buildsrht = get_origin("builds.sr.ht", default=None)
_buildsrht_api = cfg("builds.sr.ht", "api-origin", default=None) or _buildsrht
origin = get_origin("hub.sr.ht")

class SrhtService:
    def __init__(self, site):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "SourceHut project hub (https://sr.ht - https://git.sr.ht/~sircmpwn/hub.sr.ht)"
        self.site = site

    def exec(self, user, query, valid=None, **kwargs):
        return exec_gql(self.site, query, user=user, valid=valid, **kwargs)

    def enumerate(self, user,
                  query: str,
                  collector: Callable[[Any], Any],
                  **kwargs):
        """Enumerate a cursor-driven list of resources from GraphQL.

        Parameters:
        - user: the user to authenticate as
        - query: the GraphQL query to execute
        - collector: function which extracts the cursor object from the GraphQL
          response
        - kwargs: variables for GraphQL query. "cursor" is added to this by
          enumerate.
        """

        items = []
        cursor = None

        while True:
            r = self.exec(user, query, cursor=cursor, **kwargs)
            result = collector(r)
            items.extend(result["results"])
            cursor = result["cursor"]
            if cursor is None:
                break

        return items

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
        config = { }
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
        config = { }
        owner = repo.owner
        url = f"{_gitsrht}/api/{owner.canonical_name}/repos/{repo.name}/webhooks"
        try:
            ensure_webhooks(owner, url, config)
        except:
            pass # nbd, upstream was presumably deleted

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

class ListService(SrhtService):
    def __init__(self):
        super().__init__("lists.sr.ht")

    def get_lists(self, user):
        lists = self.enumerate(user, """
        query GetLists($cursor: Cursor) {
            me {
                lists(cursor: $cursor) {
                    results {
                        id
                        name
                        description
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
        collector=lambda result: result["me"]["lists"])

        for ml in lists:
            ml["updated"] = gql_time(ml["updated"])

        return lists

    def get_list(self, user, list_name):
        resp = self.exec(user, """
        query GetList($listName: String!) {
            me {
                list(name: $listName) {
                    id
                    name
                    description
                    visibility
                    defaultACL {
                        browse
                    }
                }
            }
        }
        """, listName=list_name)
        return resp["me"]["list"]

    def create_list(self, user, valid):
        name = valid.require("name")
        description = valid.optional("description")
        if not valid.ok:
            return None

        resp = self.exec(user, """
        mutation CreateList(
                $name: String!,
                $description: String!) {
            createMailingList(name: $name,
                    description: $description,
                    visibility: PUBLIC) {
                id
                name
                description
                visibility
                defaultACL {
                    browse
                }
            }
        }
        """,
        name=name,
        description=description,
        valid=valid)

        if not valid.ok:
            return None

        return resp["createMailingList"]

    def delete_list(self, user, list_id):
        resp = self.exec(user, """
        mutation DeleteList($list_id: Int!) {
            deleteMailingList(id: $list_id) { id }
        }
        """, list_id=list_id)

    def patchset_create_tool(self, user, patchset_id, icon, details):
        resp = self.exec(user, """
        mutation CreateTool(
                $patchsetID: Int!,
                $details: String!,
                $icon: ToolIcon!) {
            createTool(patchsetID: $patchsetID, details: $details, icon: $icon) {
                id
            }
        }
        """,
        patchsetID=patchset_id,
        icon=icon,
        details=details)
        return resp["createTool"]["id"]

    def patchset_update_tool(self, user, tool_id, icon, details):
        resp = self.exec(user, """
        mutation UpdateTool(
                $toolID: Int!,
                $details: String!,
                $icon: ToolIcon!) {
            updateTool(id: $toolID, details: $details, icon: $icon) {
                id
            }
        }
        """,
        toolID=tool_id,
        icon=icon,
        details=details)
        return resp["updateTool"]["id"]

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
        try:
            ensure_webhooks(owner, url, config)
        except:
            pass # nbd, upstream was presumably deleted

class TodoService(SrhtService):
    def __init__(self):
        super().__init__("todo.sr.ht")

    def get_trackers(self, user):
        trackers = self.enumerate(user, """
        query GetTrackers($cursor: Cursor) {
            me {
                trackers(cursor: $cursor) {
                    results {
                        id
                        name
                        description
                        updated
                        owner {
                            canonicalName
                        }
                    }
                    cursor
                }
            }
        }
        """, collector=lambda result: result["me"]["trackers"])

        for tr in trackers:
            tr["updated"] = gql_time(tr["updated"])

        return trackers

    def get_tracker(self, user, tracker_name):
        resp = self.exec(user, """
        query GetTracker($trackerName: String!) {
            me {
                tracker(name: $trackerName) {
                    id
                    name
                    description
                    visibility
                    defaultACL {
                        browse
                    }
                }
            }
        }
        """, trackerName=tracker_name)
        return resp["me"]["tracker"]

    def create_tracker(self, user, valid, visibility):
        name = valid.require("name")
        description = valid.optional("description")
        if not valid.ok:
            return None

        resp = self.exec(user, """
        mutation CreateTracker(
                $name: String!,
                $description: String!,
                $visibility: Visibility!) {
            createTracker(name: $name,
                    description: $description,
                    visibility: $visibility) {
                id
                name
                description
                visibility
                defaultACL {
                    browse
                }
            }
        }
        """,
        name=name,
        description=description,
        visibility=visibility.value,
        valid=valid)

        if not valid.ok:
            return None

        return resp["createTracker"]

    def delete_tracker(self, user, tracker_id):
        self.exec(user, """
        mutation DeleteTracker($trackerID: Int!) {
            deleteTracker(id: $trackerID) { id }
        }
        """, trackerID=tracker_id)

    def get_ticket_comments(self, user, owner, tracker, ticket):
        resp = self.exec(user, """
          query TicketComments($username: String!, $tracker: String!, $ticket: Int!) {
            user(username: $username) {
              tracker(name: $tracker) {
                id
                ticket(id: $ticket) {
                  events {
                    results {
                      changes {
                        ... on Comment {
                          text
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        """, username=owner[1:], tracker=tracker, ticket=ticket)
        comments = []
        trackerId = resp["user"]["tracker"]["id"]
        for e in resp["user"]["tracker"]["ticket"]["events"]["results"]:
            for c in e["changes"]:
                if "text" in c:
                    comments.append(c["text"])
        return comments, trackerId

    def update_ticket(self, user, trackerId, ticketId, comment, resolution=None):
        commentInput = {
            "text": comment,
        }
        if resolution is not None:
            commentInput["resolution"] = resolution
            commentInput["status"] = "RESOLVED"

        self.exec(user, """
        mutation UpdateTicket(
            $trackerId: Int!,
            $ticketId: Int!,
            $commentInput: SubmitCommentInput!
        ) {
            submitComment(
                trackerId: $trackerId,
                ticketId: $ticketId,
                input: $commentInput,
            ) {
                id
            }
        }
        """, trackerId=trackerId, ticketId=ticketId, commentInput=commentInput)

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
        try:
            ensure_webhooks(user, url, config)
        except:
            pass # nbd, upstream was presumably deleted

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
        try:
            ensure_webhooks(owner, url, config)
        except:
            pass # nbd, upstream was presumably deleted

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
        try:
            ensure_webhooks(owner, url, config)
        except:
            pass # nbd, upstream was presumably deleted

class BuildService(SrhtService):
    def __init__(self):
        super().__init__("builds.sr.ht")

    def submit_build(self, user, manifest, note, tags, execute=True, valid=None, visibility=None):
        resp = self.exec(user, """
        mutation SubmitBuild(
            $manifest: String!,
            $note: String,
            $tags: [String!],
            $secrets: Boolean,
            $execute: Boolean,
            $visibility: Visibility,
        ) {
            submit(
                manifest: $manifest,
                note: $note,
                tags: $tags,
                secrets: $secrets,
                execute: $execute,
                visibility: $visibility,
            ) {
                id
            }
        }
        """, **{
            "manifest": yaml.dump(manifest.to_dict(), default_flow_style=False),
            "tags": tags,
            "note": note,
            "secrets": False,
            "execute": execute,
            "visibility": visibility.value if visibility else None,
        })
        return resp["submit"]

    def create_group(self, user, job_ids, note, triggers, valid=None):
        return self.exec(user, """
        mutation CreateGroup(
            $jobIds: [Int!]!,
            $triggers: [TriggerInput!]!,
            $note: String!,
        ) {
            createGroup(jobIds: $jobIds, triggers: $triggers, note: $note) {
                id
            }
        }
        """, jobIds=job_ids, note=note, triggers=triggers, valid=valid)

git = GitService()
hg = HgService()
lists = ListService()
todo = TodoService()
builds = BuildService()
