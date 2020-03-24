from flask import Blueprint, render_template
from srht.oauth import current_user

public = Blueprint("public", __name__)

@public.route("/")
def index():
    if current_user:
        # TODO: If the user has any projects, render normal dashboard
        #return render_template("dashboard.html")
        return render_template("new-user-dashboard.html")
    return render_template("index.html")
