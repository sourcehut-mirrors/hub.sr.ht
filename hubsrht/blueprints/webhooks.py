import json
from datetime import datetime
from flask import Blueprint, request, current_app
from hubsrht.types import Event, EventType, MailingList, SourceRepo, RepoType
from hubsrht.types import Tracker, User
from srht.config import get_origin
from srht.database import db
from srht.flask import csrf_bypass

webhooks = Blueprint("webhooks", __name__)

_gitsrht = get_origin("git.sr.ht", external=True, default=None)
_hgsrht = get_origin("hg.sr.ht", external=True, default=None)
_todosrht = get_origin("todo.sr.ht", external=True, default=None)
_listssrht = get_origin("lists.sr.ht", external=True, default=None)

@csrf_bypass
@webhooks.route("/webhooks/git-user/<int:user_id>", methods=["POST"])
def git_user(user_id):
    event = request.headers.get("X-Webhook-Event")
    payload = json.loads(request.data.decode("utf-8"))
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
    payload = json.loads(request.data.decode("utf-8"))
    repo = SourceRepo.query.get(repo_id)
    if not repo:
        return "I don't recognize that repository.", 404

    if event == "repo:post-update":
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

        db.session.add(event)
        db.session.commit()
        return "Thanks!"
    else:
        raise NotImplementedError()

@csrf_bypass
@webhooks.route("/webhooks/hg-user/<int:user_id>", methods=["POST"])
def hg_user(user_id):
    event = request.headers.get("X-Webhook-Event")
    payload = json.loads(request.data.decode("utf-8"))
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
@webhooks.route("/webhooks/mailing-list", methods=["POST"])
def mailing_list():
    event = request.headers.get("X-Webhook-Event")
    payload = json.loads(request.data.decode("utf-8"))
    if event == "list:update":
        ml = (MailingList.query
                .filter(MailingList.remote_id == payload["id"])
                .one_or_none())
        if not ml:
            return "I don't recognize that mailing list.", 404
        ml.name = payload["name"]
        ml.description = payload["description"]
        ml.project.updated = datetime.utcnow()
        db.session.commit()
        return f"Updated local:{ml.id}/remote:{ml.remote_id}. Thanks!", 200
    elif event == "list:delete":
        raise NotImplementedError()
    elif event == "post:received":
        raise NotImplementedError()
    elif event == "patchset:received":
        raise NotImplementedError()
    else:
        raise NotImplementedError()

@csrf_bypass
@webhooks.route("/webhooks/todo-user/<int:user_id>", methods=["POST"])
def todo_user(user_id):
    event = request.headers.get("X-Webhook-Event")
    payload = json.loads(request.data.decode("utf-8"))

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
    payload = json.loads(request.data.decode("utf-8"))

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
            f"<a href='{tracker.url()}'>{tracker.name}</a>")

        db.session.add(event)
        db.session.commit()
        return "Thanks!"
    else:
        raise NotImplementedError()

@csrf_bypass
@webhooks.route("/webhooks/todo-ticket/<int:tracker_id>/ticket", methods=["POST"])
def todo_ticket(tracker_id):
    event = request.headers.get("X-Webhook-Event")
    payload = json.loads(request.data.decode("utf-8"))

    tracker = Tracker.query.get(tracker_id)
    if not tracker:
        return "I don't recognize this tracker.", 404

    if event == "event:create":
        raise NotImplementedError()
    else:
        raise NotImplementedError()
