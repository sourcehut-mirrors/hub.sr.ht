import requests
from srht.graphql import exec_gql
from typing import Any, Callable

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

from hubsrht.services.lists import ListService
from hubsrht.services.git import GitService
from hubsrht.services.hg import HgService
from hubsrht.services.todo import TodoService
from hubsrht.services.builds import BuildService

# Singletons
git = GitService()
hg = HgService()
lists = ListService()
todo = TodoService()
builds = BuildService()
