from flask import Blueprint

users = Blueprint("users", __name__)

@users.route("/~<username>")
def user_summary_GET(username):
    pass # TODO
