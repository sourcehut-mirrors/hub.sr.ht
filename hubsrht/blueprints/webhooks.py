import json
from flask import Blueprint, request
from hubsrht.types import MailingList, SourceRepo, RepoType
from srht.database import db
from srht.flask import csrf_bypass

webhooks = Blueprint("webhooks", __name__)

@csrf_bypass
@webhooks.route("/webhooks/git-repo", methods=["POST"])
def git_repo():
    event = request.headers.get("X-Webhook-Event")
    payload = json.loads(request.data.decode("utf-8"))
    if event == "repo:update":
        repo = (SourceRepo.query
                .filter(SourceRepo.remote_id == payload["id"])
                .filter(SourceRepo.repo_type == RepoType.git)
                .one_or_none())
        if not repo:
            return "I don't recognize that repository.", 404
        repo.name = payload["name"]
        repo.description = payload["description"]
        db.session.commit()
        return f"Updated local:{repo.id}/remote:{repo.remote_id}. Thanks!", 200
    elif event == "repo:delete":
        raise NotImplementedError()
    elif event == "repo:post-update":
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

@csrf_bypass
@webhooks.route("/webhooks/tracker", methods=["POST"])
def tracker():
    event = request.headers.get("X-Webhook-Event")
    payload = json.loads(request.data.decode("utf-8"))
    if event == "tracker:update":
        tracker = (Tracker.query
                .filter(Tracker.remote_id == payload["id"])
                .one_or_none())
        if not tracker:
            return "I don't recognize this tracker.", 404
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
