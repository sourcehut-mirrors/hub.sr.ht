from flask import Blueprint, render_template, request, redirect, url_for
from hubsrht.projects import ProjectAccess, get_project
from hubsrht.services import git
from hubsrht.types import Event, EventType
from hubsrht.types import Project, RepoType, Visibility
from srht.database import db
from srht.flask import paginate_query
from srht.oauth import current_user, loginrequired
from srht.validation import Validation

projects = Blueprint("projects", __name__)

@projects.route("/<owner>/<project_name>")
def summary_GET(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.read)

    summary = None
    summary_error = False
    if project.summary_repo_id is not None:
        repo = project.summary_repo
        assert repo.repo_type != RepoType.hg # TODO
        try:
            summary = git.get_readme(owner, repo.name)
        except:
            summary = None
            summary_error = True

    events = (Event.query
        .filter(Event.project_id == project.id)
        .order_by(Event.created.desc())
        .limit(2)).all()

    return render_template("project-summary.html", view="summary",
            owner=owner, project=project,
            summary=summary, summary_error=summary_error,
            events=events, EventType=EventType)

@projects.route("/<owner>/<project_name>/feed")
def feed_GET(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.read)

    events = (Event.query
        .filter(Event.project_id == project.id)
        .order_by(Event.created.desc()))
    events, pagination = paginate_query(events)

    return render_template("project-feed.html",
            view="summary", owner=owner, project=project,
            events=events, EventType=EventType, **pagination)

@projects.route("/projects/create")
@loginrequired
def create_GET():
    return render_template("project-create.html")

@projects.route("/projects/create", methods=["POST"])
@loginrequired
def create_POST():
    valid = Validation(request)
    name = valid.require("name")
    description = valid.require("description")
    visibility = valid.require("visibility", cls=Visibility)
    valid.expect(not name or len(name) < 128,
            "Name must be fewer than 128 characters", field="name")
    valid.expect(not name or Project.query
            .filter(Project.name == name)
            .filter(Project.owner_id == current_user.id).count() == 0,
            "Name must be unique among your projects", field="name")
    valid.expect(not description or len(description) < 512,
            "Description must be fewer than 512 characters",
            field="description")
    if not valid.ok:
        return render_template("project-create.html", **valid.kwargs)

    project = Project()
    project.name = name
    project.description = description
    project.visibility = visibility
    project.owner_id = current_user.id
    db.session.add(project)
    db.session.commit()

    return redirect(url_for("projects.summary_GET",
        owner=current_user.canonical_name,
        project_name=project.name))
