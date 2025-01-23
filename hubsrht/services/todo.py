from flask import url_for
from hubsrht.services import SrhtService
from srht.config import get_origin, cfg
from srht.graphql import gql_time

origin = get_origin("hub.sr.ht")
_todosrht = get_origin("todo.sr.ht", default=None)
_todosrht_api = cfg("todo.sr.ht", "api-origin", default=None) or _todosrht

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
