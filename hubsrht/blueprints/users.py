from flask import Blueprint, render_template, request
from hubsrht.types import User, Project, Visibility, Event, EventType
from srht.flask import paginate_query
from srht.oauth import current_user
from srht.search import search_by

users = Blueprint("users", __name__)

@users.route("/~<username>")
def summary_GET(username):
    user = User.query.filter(User.username == username).first()
    if not user:
        abort(404)
    projects = (Project.query
            .filter(Project.owner_id == current_user.id)
            .order_by(Project.updated.desc()))
    events = (Event.query
            .filter(Event.user_id == current_user.id)
            .order_by(Event.created.desc()))

    if not current_user or current_user.id != user.id:
        # TODO: ACLs
        projects = projects.filter(Project.visibility == Visibility.public)
        events = (events
                .join(Project)
                .filter(Project.visibility == Visibility.public))

    projects = projects.limit(5).all()
    events, pagination = paginate_query(events)

    return render_template("profile.html",
            user=user, projects=projects, EventType=EventType, events=events,
            **pagination)

@users.route("/projects/<owner>")
def projects_GET(owner):
    if owner.startswith("~"):
        owner = owner[1:]
    owner = User.query.filter(User.username == owner).first()
    if not owner:
        abort(404)
    projects = (Project.query
        .filter(Project.owner_id == owner.id))
    if not current_user or current_user.id != owner.id:
        # TODO: ACLs
        projects = projects.filter(Project.visibility == Visibility.public)

    search = request.args.get("search")
    if search:
        projects = search_by(projects, search,
                [Project.name, Project.description])

    projects, pagination = paginate_query(projects)

    return render_template("projects.html", user=owner, projects=projects,
            search=search, **pagination)
