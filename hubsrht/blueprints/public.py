from flask import Blueprint, render_template, request
from hubsrht.types import Project, Feature, Event, EventType, Visibility, User
from srht.flask import paginate_query
from srht.oauth import current_user, loginrequired
from srht.search import search_by

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
            .filter(Project.visibility == Visibility.public)
            .filter(Project.checklist_complete))

    search = request.args.get("search")
    if search:
        projects = search_by(projects, search,
                [Project.name, Project.description])

    sort = request.args.get("sort")
    if sort and sort == "recently-updated":
        projects = projects.order_by(Project.updated.desc())
    elif sort and sort == "longest-active":
        projects = projects.order_by((Project.updated - Project.created).desc())
    else:
        projects = projects.order_by(Project.updated.desc())

    projects, pagination = paginate_query(projects)

    features = (Feature.query
            .join(Project, Feature.project_id == Project.id)
            .join(User, Project.owner_id == User.id)
            .filter(Project.visibility == Visibility.public)
            .order_by(Feature.created.desc())
            .limit(5)).all()

    return render_template("project-index.html", projects=projects,
            search=search, features=features, sort=sort, **pagination)
