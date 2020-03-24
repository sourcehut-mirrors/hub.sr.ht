from flask import Blueprint

webhooks = Blueprint("webhooks", __name__)

@webhooks.route("/webhooks/git-repo")
def git_repo_update():
    pass # TODO
