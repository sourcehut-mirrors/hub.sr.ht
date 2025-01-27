from flask import url_for
from hubsrht.services import SrhtService
from srht.config import get_origin, cfg
from srht.graphql import gql_time

origin = get_origin("hub.sr.ht")
_listsrht = get_origin("lists.sr.ht", default=None)
_listsrht_api = cfg("lists.sr.ht", "api-origin", default=None) or _listsrht

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

    def create_list_webhook(self, user, list_id):
        url = origin + url_for("webhooks.mailing_list", _external=False)
        resp = self.exec(user, """
            mutation CreateWebhook(
                $listId: Int!,
                $payload: String!
                $url: String!,
            ) {
                webhook: createMailingListWebhook(
                    listId: $listId,
                    config: {
                        url: $url,
                        query: $payload,
                        events: [
                          LIST_UPDATED,
                          LIST_DELETED,
                          EMAIL_RECEIVED,
                          PATCHSET_RECEIVED,
                        ],
                    },
                ) { 
                    id
                }
            }
            """,
            listId=list_id,
            payload=lists_webhook_payload,
            url=url)
        return (resp["webhook"]["id"], lists_webhook_version)

    def delete_list_webhook(self, user, hook_id):
        self.exec(user, """
            mutation DeleteWebhook($id: Int!) {
                deleteMailingListWebhook(id: $id) { id }
            }
            """,
            id=hook_id)

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

lists_webhook_version = 1
lists_webhook_payload = """
query {
    webhook {
        uuid
        event
        date

        ... on MailingListEvent {
            list {
                id
                name
                description
                visibility
            }
        }

        ... on EmailEvent {
            email {
                id
                list { id }
                messageID
                subject

                sender {
                    canonicalName

                    ... on User {
                        username
                    }
                }
            }
        }

        ... on PatchsetEvent {
            patchset {
                id
                subject
                prefix
                version
                list { id }

                thread {
                    root {
                        messageID
                        reply_to: header(want: "In-Reply-To")
                    }
                }

                submitter {
                    ... on User {
                        name: canonicalName
                        address: email
                    }

                    ... on Mailbox {
                        name
                        address
                    }
                }
            }
        }
    }
}
"""
