import email
import html
import json
import re
from datetime import datetime
from flask import Blueprint, request, current_app
from hubsrht.builds import submit_patchset
from hubsrht.services import git, todo, lists
from hubsrht.trailers import commit_trailers
from hubsrht.types import Event, EventType, MailingList, SourceRepo, RepoType
from hubsrht.types import Tracker, User, Visibility
from srht.config import get_origin
from srht.crypto import fernet, verify_request_signature
from srht.database import db
from srht.flask import csrf_bypass
from srht.graphql import GraphQLError, Error
from srht.validation import Validation
from urllib.parse import quote

webhooks = Blueprint("webhooks", __name__)

_gitsrht = get_origin("git.sr.ht", external=True, default=None)
_hgsrht = get_origin("hg.sr.ht", external=True, default=None)
_todosrht = get_origin("todo.sr.ht", external=True, default=None)
_listssrht = get_origin("lists.sr.ht", external=True, default=None)

@csrf_bypass
@webhooks.route("/webhooks/git-user/<int:user_id>", methods=["POST"])
def git_user(user_id):
    event = request.headers.get("X-Webhook-Event")
    payload = verify_request_signature(request)
    payload = json.loads(payload.decode('utf-8'))
    user = User.query.get(user_id)
    if not user:
        return "I don't recognize this user.", 404

    if event == "repo:update":
        repos = (SourceRepo.query
                .filter(SourceRepo.remote_id == payload["id"])
                .filter(SourceRepo.repo_type == RepoType.git))
        summary = ""
        for repo in repos:
            repo.name = payload["name"]
            repo.description = payload["description"]
            repo.visibility = Visibility(payload["visibility"].upper())
            repo.project.updated = datetime.utcnow()
            db.session.commit()
            summary += f"Updated local:{repo.id}/remote:{repo.remote_id}. Thanks!\n"
        return summary, 200
    elif event == "repo:delete":
        repos = (SourceRepo.query
                .filter(SourceRepo.remote_id == payload["id"])
                .filter(SourceRepo.repo_type == RepoType.git))
        summary = ""
        for repo in repos:
            if repo.project.summary_repo_id == repo.id:
                repo.project.summary_repo = None
                db.session.commit()
            db.session.delete(repo)
            repo.project.updated = datetime.utcnow()
            db.session.commit()
            summary += f"Deleted local:{repo.id}/remote:{repo.remote_id}. Thanks!\n"
        return summary, 200
    else:
        raise NotImplementedError()

@csrf_bypass
@webhooks.route("/webhooks/git-repo/<int:repo_id>", methods=["POST"])
def git_repo(repo_id):
    event = request.headers.get("X-Webhook-Event")
    payload = verify_request_signature(request)
    payload = json.loads(payload.decode('utf-8'))
    repo = SourceRepo.query.get(repo_id)
    if not repo:
        return "I don't recognize that repository.", 404

    if event == "repo:post-update":
        if not payload["refs"][0]["new"]:
            return "Thanks!"
        commit_sha = payload["refs"][0]["new"]["id"][:7]
        commit_url = repo.url() + f"/commit/{commit_sha}"
        commit_message = payload["refs"][0]["new"]["message"].split("\n")[0]
        pusher_name = payload['pusher']['canonical_name']
        pusher_url = f"{_gitsrht}/{pusher_name}"
        repo_name = repo.owner.canonical_name + "/" + repo.name

        pusher = current_app.oauth_service.lookup_user(payload['pusher']['name'])

        event = Event()
        event.event_type = EventType.external_event
        event.source_repo_id = repo.id
        event.project_id = repo.project_id
        event.user_id = pusher.id

        event.external_source = "git.sr.ht"
        event.external_summary = (
            f"<a href='{commit_url}'>{commit_sha}</a> " +
            f"<code>{html.escape(commit_message)}</code>")
        event.external_summary_plain = f"{commit_sha} - {commit_message}"
        event.external_details = (
            f"<a href='{pusher_url}'>{pusher_name}</a> pushed to " +
            f"<a href='{repo.url()}'>{repo_name}</a> git")
        event.external_details_plain = f"{pusher_name} pushed to {repo_name} git"
        event.external_url = commit_url

        repo.project.updated = datetime.utcnow()
        db.session.add(event)
        db.session.commit()

        for ref in payload["refs"]:
            old = (ref["old"] or {}).get("id")
            new = (ref["new"] or {}).get("id")
            if not old or not new:
                continue # New ref, or ref deleted
            for commit in reversed(git.log(pusher, repo, old, new)):
                for trailer, value in commit_trailers(commit["message"]):
                    _handle_commit_trailer(trailer, value, pusher, repo, commit)

        return "Thanks!"
    else:
        raise NotImplementedError()

_ticket_url_re = re.compile(
    rf"""
    ^
    {re.escape(_todosrht)}
    /(?P<owner>~[a-z_][a-z0-9_-]+)
    /(?P<tracker>[\w.-]+)
    /(?P<ticket>\d+)
    $
    """,
    re.VERBOSE,
) if _todosrht else None

def _handle_commit_trailer(trailer, value, pusher, repo, commit):
    if not _todosrht:
        return

    if trailer == "Closes":
        resolution = "CLOSED"
    elif trailer == "Fixes":
        resolution = "FIXED"
    elif trailer == "Implements":
        resolution = "IMPLEMENTED"
    elif trailer == "References":
        resolution = None
    else:
        return

    match = _ticket_url_re.match(value.strip())
    if not match:
        return

    commit_message = html.escape(commit["message"].split("\n")[0])
    commit_author = html.escape(commit["author"]["name"].strip())
    commit_sha = commit["id"][:7]
    commit_url = repo.url() + f"/commit/{commit_sha}"
    comment = f"""\
*{commit_author} referenced this ticket in commit [{commit_sha}].*

[{commit_sha}]: {commit_url} "{commit_message}"\
"""
    existing_comments, trackerId = todo.get_ticket_comments(
        user=pusher,
        owner=match["owner"],
        tracker=match["tracker"],
        ticket=int(match["ticket"]),
    )
    if comment in existing_comments:
        # avoid duplicate comments
        return
    ticketId = int(match["ticket"])
    try:
        todo.update_ticket(pusher, trackerId, ticketId, comment, resolution)
    except GraphQLError as err:
        if not err.has(Error.ACCESS_DENIED):
            raise
        # Try again without resolving the ticket, in case this user has comment
        # access but not triage access
        try:
            todo.update_ticket(pusher, trackerId, ticketId, comment)
        except GraphQLError as err:
            # Silently discard further access denied errors
            if not err.has(Error.ACCESS_DENIED):
                raise

@csrf_bypass
@webhooks.route("/webhooks/hg-user/<int:user_id>", methods=["POST"])
def hg_user(user_id):
    event = request.headers.get("X-Webhook-Event")
    payload = verify_request_signature(request)
    payload = json.loads(payload.decode('utf-8'))
    user = User.query.get(user_id)
    if not user:
        return "I don't recognize this user.", 404

    if event == "repo:update":
        repo = (SourceRepo.query
                .filter(SourceRepo.id == payload["id"])
                .filter(SourceRepo.repo_type == RepoType.hg)).one_or_none()
        if not repo:
            return "I don't recognize that repository.", 404
        repo.name = payload["name"]
        repo.description = payload["description"]
        repo.project.updated = datetime.utcnow()
        repo.visibility = Visibility(payload["visibility"].upper())
        db.session.commit()
        return f"Updated local:{repo.id}/remote:{repo.remote_id}. Thanks!", 200
    elif event == "repo:delete":
        repo = (SourceRepo.query
                .filter(SourceRepo.remote_id == payload["id"])
                .filter(SourceRepo.repo_type == RepoType.hg)).one_or_none()
        if not repo:
            return "I don't recognize this hg repo.", 404
        if repo.project.summary_repo_id == repo.id:
            repo.project.summary_repo = None
            db.session.commit()
        db.session.delete(repo)
        repo.project.updated = datetime.utcnow()
        db.session.commit()
        return f"Deleted local:{repo.id}/remote:{repo.remote_id}. Thanks!", 200
    else:
        raise NotImplementedError()

@csrf_bypass
@webhooks.route("/webhooks/gql/mailing-list/<int:list_id>", methods=["POST"])
def project_mailing_list(list_id):
    event = request.headers.get("X-Webhook-Event")
    payload = verify_request_signature(request)
    payload = json.loads(payload.decode('utf-8'))["data"]["webhook"]

    mailing_list = (MailingList.query
             .filter(MailingList.id == list_id)).one_or_none()
    if not mailing_list:
        return "I don't recognize that mailing list.", 404

    if event == "LIST_UPDATED":
        data = payload["list"]

        mailing_list.name = data["name"]
        mailing_list.description = data["description"]
        mailing_list.visibility = Visibility(data["visibility"])
        mailing_list.project.updated = datetime.utcnow()
        db.session.commit()

        local_id = mailing_list.id
        remote_id = mailing_list.remote_id
        return f"Updated local:{local_id}/remote:{remote_id}", 200
    elif event == "LIST_DELETED":
        local_id = mailing_list.id
        remote_id = mailing_list.remote_id
        mailing_list.project.updated = datetime.utcnow()
        db.session.delete(mailing_list)
        db.session.commit()
        return f"Deleted mailing lists local:{local_id}/remote:{remote_id}", 200
    elif event == "EMAIL_RECEIVED":
        data = payload["email"]
        sender_canon = data["sender"]["canonicalName"]
        sender_username = data["sender"].get("username")
        subject = data["subject"]
        message_id = f"<{data['messageID']}>"
        archive_url = f"{mailing_list.url()}/{quote(message_id)}"

        event = Event()
        if sender_username:
            sender = current_app.oauth_service.lookup_user(sender_username)
            event.user_id = sender.id
            attrib = f"<a href='{_listssrht}/{sender_canon}'>{sender_canon}</a>"
        else:
            attrib = sender_canon

        event.event_type = EventType.external_event
        event.mailing_list_id = mailing_list.id
        event.project_id = mailing_list.project_id

        event.external_source = "lists.sr.ht"
        event.external_summary = f"<a href='{archive_url}'>{html.escape(subject)}</a>"
        event.external_details = (f"{attrib} via " +
                f"<a href='{mailing_list.url()}'>{mailing_list.name}</a>")
        event.external_url = archive_url

        db.session.add(event)
        db.session.commit()
        return f"Assigned event ID {event.id}"
    elif event == "PATCHSET_RECEIVED":
        data = payload["patchset"]
        valid = Validation(request)
        job_ids = []

        try:
            ids = submit_patchset(mailing_list, data, valid)
            if ids is not None:
                job_ids.extend(ids)
        except Exception as ex:
            return "Error submitting builds: " + str(ex)

        if not valid.ok:
            return valid.response
        else:
            return "Submitted builds: " + ", ".join([str(x) for x in job_ids])
    else:
        raise Exception(f"Unknown mailing list webhook event: {event}")

@csrf_bypass
@webhooks.route("/webhooks/todo-user/<int:user_id>", methods=["POST"])
def todo_user(user_id):
    event = request.headers.get("X-Webhook-Event")
    payload = verify_request_signature(request)
    payload = json.loads(payload.decode('utf-8'))

    user = User.query.get(user_id)
    if not user:
        return "I don't recognize this tracker.", 404

    summary = ""
    if event == "tracker:update":
        trackers = Tracker.query.filter(Tracker.remote_id == payload["id"])
        for tracker in trackers:
            tracker.name = payload["name"]
            tracker.description = payload["description"]
            if any(payload["default_access"]):
                tracker.visibility = Visibility.PUBLIC
            else:
                tracker.visibility = Visibility.UNLISTED
            tracker.project.updated = datetime.utcnow()
            summary += f"Updated local:{tracker.id}/remote:{tracker.remote_id}\n"
        db.session.commit()
        return summary, 200
    elif event == "tracker:delete":
        trackers = Tracker.query.filter(Tracker.remote_id == payload["id"])
        for tracker in trackers:
            tracker.project.updated = datetime.utcnow()
            db.session.delete(tracker)
            db.session.commit()
            summary += f"Deleted local:{tracker.id}/remote:{tracker.remote_id}\n"
        return summary, 200
    else:
        raise NotImplementedError()

@csrf_bypass
@webhooks.route("/webhooks/todo-tracker/<int:tracker_id>", methods=["POST"])
def todo_tracker(tracker_id):
    event = request.headers.get("X-Webhook-Event")
    payload = verify_request_signature(request)
    payload = json.loads(payload.decode('utf-8'))

    tracker = Tracker.query.get(tracker_id)
    if not tracker:
        return "I don't recognize this tracker.", 404

    if event == "ticket:create":
        event = Event()
        submitter = payload["submitter"]
        if submitter["type"] == "user":
            event.user_id = current_app.oauth_service.lookup_user(submitter['name']).id
            # TODO: Move this to a hub.sr.ht user page
            submitter_url = f"{_todosrht}/{submitter['canonical_name']}"
            submitter_url = f"<a href='{submitter_url}'>{submitter['canonical_name']}</a>"
        elif submitter["type"] == "email" and 'name' in submitter:
            submitter_url = f"{submitter['name']}"
        elif submitter["type"] == "email":
            submitter_url = f"{submitter['email']}"
        else:
            submitter_url = f"{submitter['external_id']}"

        event.event_type = EventType.external_event
        event.tracker_id = tracker.id
        event.project_id = tracker.project_id

        ticket_id = payload["id"]
        ticket_url = tracker.url() + f"/{ticket_id}"
        ticket_subject = payload["title"]

        event.external_source = "todo.sr.ht"
        event.external_summary = (
            f"<a href='{ticket_url}'>#{ticket_id}</a> " +
            f"{html.escape(ticket_subject)}")
        event.external_summary_plain = f"#{ticket_id} {ticket_subject}"
        event.external_details = (
            f"{submitter_url} filed ticket on " +
            f"<a href='{tracker.url()}'>{tracker.name}</a> todo")
        assert submitter['type'] in ['user', 'email']
        if submitter['type'] == 'user':
            event.external_details_plain = f"{submitter['canonical_name']} filed ticket on {tracker.name} todo"
        elif submitter['type'] == 'email':
            event.external_details_plain = f"{submitter['name']} filed ticket on {tracker.name} todo"
        event.external_url = ticket_url

        db.session.add(event)
        db.session.commit()
        todo.ensure_ticket_webhooks(tracker, ticket_id)
        return "Thanks!"
    else:
        raise NotImplementedError()

@csrf_bypass
@webhooks.route("/webhooks/todo-ticket/<int:tracker_id>/ticket", methods=["POST"])
def todo_ticket(tracker_id):
    event = request.headers.get("X-Webhook-Event")
    payload = verify_request_signature(request)
    payload = json.loads(payload.decode('utf-8'))

    tracker = Tracker.query.get(tracker_id)
    if not tracker:
        return "I don't recognize this tracker.", 404

    if event == "event:create":
        event = Event()
        participant = payload["user"]
        if participant["type"] == "user":
            event.user_id = current_app.oauth_service.lookup_user(participant['name']).id
            # TODO: Move this to a hub.sr.ht user page
            participant_url = f"{_todosrht}/{participant['canonical_name']}"
            participant_url = f"<a href='{participant_url}'>{participant['canonical_name']}</a>"
        elif participant["type"] == "email":
            if 'name' in participant:
                participant_url = participant['name']
            else:
                participant_url = participant['email']
        else:
            participant_url = f"{participant['external_id']}"

        if not "comment" in payload["event_type"]:
            return "Thanks!"

        event.event_type = EventType.external_event
        event.tracker_id = tracker.id
        event.project_id = tracker.project_id

        ticket_id = payload["ticket"]["id"]
        ticket_url = tracker.url() + f"/{ticket_id}"
        ticket_subject = payload["ticket"]["title"]

        event.external_source = "todo.sr.ht"
        event.external_summary = (
            f"<a href='{ticket_url}'>#{ticket_id}</a> " +
            f"{html.escape(ticket_subject)}")
        event.external_summary_plain = f"#{ticket_id} {ticket_subject}"
        event.external_details = (
            f"{participant_url} commented on " +
            f"<a href='{tracker.url()}'>{tracker.name}</a> todo")

        if participant['type'] == 'user':
            event.external_details_plain = f"{participant['canonical_name']} commented on {tracker.name} todo"
        elif participant['type'] == 'email':
            event.external_details_plain = f"{participant_url} commented on {tracker.name} todo"
        event.external_url = ticket_url

        db.session.add(event)
        db.session.commit()
        return "Thanks!"
    else:
        raise NotImplementedError()

@csrf_bypass
@webhooks.route("/webhooks/build-complete/<details>", methods=["POST"])
def build_complete(details):
    payload = verify_request_signature(request)
    payload = json.loads(payload.decode('utf-8'))
    details = fernet.decrypt(details.encode())
    if not details:
        return "Bad payload", 400
    details = json.loads(details.decode())
    ml = (MailingList.query
            .filter(MailingList.id == details["mailing_list"])).one_or_none()
    if not ml:
        return "Unknown mailing list", 404
    project = ml.project
    if payload["owner"]["canonical_name"] != details["user"]:
        return "Discarding webhook from unauthorized build", 401

    buildsrht = get_origin("builds.sr.ht", external=True)
    build_url = f"{buildsrht}/{project.owner.canonical_name}/job/{payload['id']}"

    tool_details = f"[#{payload['id']}]({build_url}) {details['name']} {payload['status']}"
    status = payload["status"].upper()
    if status == 'TIMEOUT':
        status = 'FAILED'
    lists.patchset_update_tool(ml.owner, details["tool_id"], status, tool_details)

    return "Thanks!"
