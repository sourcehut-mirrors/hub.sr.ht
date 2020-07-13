import email
import json
from datetime import datetime
from flask import Blueprint, request, current_app
from hubsrht.builds import submit_patchset
from hubsrht.services import todo, lists
from hubsrht.types import Event, EventType, MailingList, SourceRepo, RepoType
from hubsrht.types import Tracker, User, Visibility
from srht.config import get_origin
from srht.crypto import fernet, verify_request_signature
from srht.database import db
from srht.flask import csrf_bypass
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
        repo = (SourceRepo.query
                .filter(SourceRepo.remote_id == payload["id"])
                .filter(SourceRepo.repo_type == RepoType.git)).one_or_none()
        if not repo:
            return "I don't recognize this git repo.", 404
        repo.name = payload["name"]
        repo.description = payload["description"]
        repo.visibility = Visibility(payload["visibility"])
        repo.project.updated = datetime.utcnow()
        db.session.commit()
        return f"Updated local:{repo.id}/remote:{repo.remote_id}. Thanks!", 200
    elif event == "repo:delete":
        repo = (SourceRepo.query
                .filter(SourceRepo.remote_id == payload["id"])
                .filter(SourceRepo.repo_type == RepoType.git)).one_or_none()
        if not repo:
            return "I don't recognize this git repo.", 404
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
            f"<code>{commit_message}</code>")
        event.external_details = (
            f"<a href='{pusher_url}'>{pusher_name}</a> pushed to " +
            f"<a href='{repo.url()}'>{repo_name}</a> git")

        repo.project.updated = datetime.utcnow()
        db.session.add(event)
        db.session.commit()
        return "Thanks!"
    else:
        raise NotImplementedError()

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
        repo.visibility = Visibility(payload["visibility"])
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
@webhooks.route("/webhooks/mailing-list/<list_id>", methods=["POST"])
def mailing_list(list_id):
    event = request.headers.get("X-Webhook-Event")
    payload = verify_request_signature(request)
    payload = json.loads(payload.decode('utf-8'))
    ml = MailingList.query.get(list_id)
    if not ml:
            return "I don't recognize that mailing list.", 404
    if event == "list:update":
        ml.name = payload["name"]
        ml.description = payload["description"]
        if any(payload["permissions"]["nonsubscriber"]):
            ml.visibility = Visibility.public
        else:
            ml.visibility = Visibility.unlisted
        ml.project.updated = datetime.utcnow()
        db.session.commit()
        return f"Updated local:{ml.id}/remote:{ml.remote_id}. Thanks!", 200
    elif event == "list:delete":
        db.session.delete(ml)
        ml.project.updated = datetime.utcnow()
        db.session.commit()
        return f"Deleted local:{ml.id}/remote:{ml.remote_id}. Thanks!", 200
    elif event == "post:received":
        event = Event()
        sender = payload["sender"]
        if sender:
            sender = current_app.oauth_service.lookup_user(sender['name'])
            event.user_id = sender.id
            sender_url = f"<a href='{_listssrht}/{sender.canonical_name}'>{sender.canonical_name}</a>"
        else:
            msg = email.message_from_string(payload["envelope"],
                    policy=email.policy.SMTP)
            sender = email.utils.parseaddr(msg['From'])
            sender_url = sender[0] if sender[0] else sender[1]

        event.event_type = EventType.external_event
        event.mailing_list_id = ml.id
        event.project_id = ml.project_id

        archive_url = ml.url() + f"/{quote(payload['message_id'])}"
        subject = payload["subject"]

        event.external_source = "todo.sr.ht"
        event.external_summary = (
            f"<a href='{archive_url}'>{subject}</a>")
        event.external_details = (
            f"{sender_url} via <a href='{ml.url()}'>{ml.name}</a>")

        db.session.add(event)
        db.session.commit()
        return "Thanks!"
    elif event == "patchset:received":
        build_ids = submit_patchset(ml, payload)
        if build_ids:
            return f"Submitted builds #{build_ids}. Thanks!"
        else:
            return "Thanks!"
    else:
        raise NotImplementedError()

@csrf_bypass
@webhooks.route("/webhooks/todo-user/<int:user_id>", methods=["POST"])
def todo_user(user_id):
    event = request.headers.get("X-Webhook-Event")
    payload = verify_request_signature(request)
    payload = json.loads(payload.decode('utf-8'))

    user = User.query.get(user_id)
    if not user:
        return "I don't recognize this tracker.", 404

    if event == "tracker:update":
        tracker = (Tracker.query
                .filter(Tracker.remote_id == payload["id"])
                .one_or_none())
        if not tracker:
            return "I don't recognize this tracker.", 404
        tracker.name = payload["name"]
        tracker.description = payload["description"]
        if any(payload["default_permissions"]["anonymous"]):
            tracker.visibility = Visibility.public
        else:
            tracker.visibility = Visibility.unlisted
        tracker.project.updated = datetime.utcnow()
        db.session.commit()
        return f"Updated local:{tracker.id}/remote:{tracker.remote_id}. Thanks!", 200
    elif event == "tracker:delete":
        tracker = (Tracker.query
                .filter(Tracker.remote_id == payload["id"])
                .one_or_none())
        if not tracker:
            return "I don't recognize this tracker.", 404
        tracker.project.updated = datetime.utcnow()
        db.session.delete(tracker)
        db.session.commit()
        return f"Deleted local:{tracker.id}/remote:{tracker.remote_id}. Thanks!", 200
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
        elif submitter["type"] == "email":
            submitter_url = f"{submitter['name']}"
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
            f"{ticket_subject}")
        event.external_details = (
            f"{submitter_url} filed ticket on " +
            f"<a href='{tracker.url()}'>{tracker.name}</a> todo")

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
            participant_url = f"{participant['name']}"
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
            f"{ticket_subject}")
        event.external_details = (
            f"{participant_url} commented on " +
            f"<a href='{tracker.url()}'>{tracker.name}</a> todo")

        db.session.add(event)
        db.session.commit()
        return "Thanks!"
    else:
        raise NotImplementedError()

@csrf_bypass
@webhooks.route("/webhooks/build-complete/<details>", methods=["POST"])
def build_complete(details):
    payload = json.loads(request.data.decode())
    details = fernet.decrypt(details.encode())
    if not details:
        return "Bad payload", 400
    details = json.loads(details.decode())
    ml = (MailingList.query
            .filter(MailingList.id == details["mailing_list"])).one_or_none()
    if not ml:
        return "Unknown mailing list", 404
    project = ml.project

    buildsrht = get_origin("builds.sr.ht", external=True)
    build_url = f"{buildsrht}/{project.owner.canonical_name}/job/{payload['id']}"

    lists.patchset_set_tool(ml.owner, ml.name, details["patchset_id"],
            details['key'], payload["status"],
            f"[#{payload['id']}]({build_url}) {details['name']} {payload['status']}")

    return "Thanks!"
