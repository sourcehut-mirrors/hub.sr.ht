from flask import Blueprint

users = Blueprint("users", __name__)

@users.route("/~<username>")
def summary_GET(username):
    pass # TODO

@users.route("/projects/<owner>")
def projects_GET(owner):
    pass # TODO
