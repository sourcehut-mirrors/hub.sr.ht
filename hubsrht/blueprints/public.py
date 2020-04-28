from flask import Blueprint, render_template
from hubsrht.types import Project, Event, EventType, Visibility
from srht.flask import paginate_query
from srht.oauth import current_user, loginrequired

public = Blueprint("public", __name__)

@public.route("/")
def index():
    if current_user:
        projects = (Project.query
                .filter(Project.owner_id == current_user.id)
                .order_by(Project.updated.desc())
                .limit(5)).all()
        if any(projects):
            events = (Event.query
                    .filter(Event.user_id == current_user.id)
                    .order_by(Event.created.desc())
                    .limit(2)).all()
            return render_template("dashboard.html",
                    projects=projects, EventType=EventType, events=events)
        return render_template("new-user-dashboard.html")
    return render_template("index.html")

@public.route("/getting-started")
@loginrequired
def getting_started():
    return render_template("new-user-dashboard.html")

@public.route("/projects")
def project_index():
    projects = (Project.query
            .filter(Project.visibility == Visibility.public))
    projects, pagination = paginate_query(projects)
    return render_template("project-index.html",
            projects=projects, **pagination)
