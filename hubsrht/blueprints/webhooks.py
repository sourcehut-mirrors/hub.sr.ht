import json
from flask import Blueprint, request
from hubsrht.types import Event, EventType, MailingList, SourceRepo, RepoType
from srht.database import db
from srht.flask import csrf_bypass

webhooks = Blueprint("webhooks", __name__)

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
        db.session.commit()
        return f"Updated local:{repo.id}/remote:{repo.remote_id}. Thanks!", 200
    elif event == "repo:delete":
        repo = (SourceRepo.query
                .filter(SourceRepo.remote_id == payload["id"])
                .filter(SourceRepo.repo_type == RepoType.git)).one_or_none()
        if not repo:
            return "I don't recognize this git repo.", 404
        raise NotImplementedError()
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
        raise NotImplementedError()
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
                .filter(SourceRepo.id == repo_id)
                .filter(SourceRepo.repo_type == RepoType.hg)).one_or_none()
        if not repo:
            return "I don't recognize that repository.", 404
        repo.name = payload["name"]
        repo.description = payload["description"]
        db.session.commit()
        return f"Updated local:{repo.id}/remote:{repo.remote_id}. Thanks!", 200
    elif event == "repo:delete":
        raise NotImplementedError()
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

    user = User.query.get(tracker_id)
    if not user:
        return "I don't recognize this tracker.", 404

    if event == "tracker:update":
        tracker = (Tracker.query
                .filter(Tracker.remote_id == payload["id"])
                .one_or_default())
        if not tracker:
            return "I don't recognize this tracker.", 404
        tracker.name = payload["name"]
        tracker.description = payload["description"]
        db.session.commit()
        return f"Updated local:{tracker.id}/remote:{tracker.remote_id}. Thanks!", 200
    elif event == "tracker:delete":
        tracker = (Tracker.query
                .filter(Tracker.remote_id == payload["id"])
                .one_or_default())
        if not tracker:
            return "I don't recognize this tracker.", 404
        raise NotImplementedError()
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

    if event == "tracker:update":
        tracker.name = payload["name"]
        tracker.description = payload["description"]
        db.session.commit()
        return f"Updated local:{tracker.id}/remote:{tracker.remote_id}. Thanks!", 200
    elif event == "tracker:delete":
        raise NotImplementedError()
    elif event == "ticket:create":
        raise NotImplementedError()
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
