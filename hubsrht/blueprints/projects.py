from flask import Blueprint, render_template, request, redirect, url_for
from hubsrht.decorators import adminrequired
from hubsrht.projects import ProjectAccess, get_project
from hubsrht.services import git, hg
from hubsrht.types import Feature, Event, EventType
from hubsrht.types import Project, RepoType, Visibility
from srht.database import db
from srht.flask import paginate_query
from srht.oauth import current_user, loginrequired
from srht.validation import Validation, valid_url

projects = Blueprint("projects", __name__)

@projects.route("/<owner>/<project_name>")
def summary_GET(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.read)

    summary = None
    summary_error = False
    if project.summary_repo_id is not None:
        repo = project.summary_repo
        try:
            if repo.repo_type == RepoType.git:
                summary = git.get_readme(owner, repo.name)
            elif repo.repo_type == RepoType.hg:
                summary = hg.get_readme(owner, repo.name)
            else:
                assert False
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

@projects.route("/<owner>/<project_name>/dismiss-checklist", methods=["POST"])
@loginrequired
def dismiss_checklist_POST(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    project.checklist_complete = True
    db.session.commit()
    return redirect(url_for("projects.summary_GET",
        owner=current_user.canonical_name,
        project_name=project.name))

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
    # TODO: Test that name passes some validity regex
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

@projects.route("/<owner>/<project_name>/settings")
@loginrequired
def config_GET(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    return render_template("project-config.html", view="add more",
            owner=owner, project=project)

@projects.route("/<owner>/<project_name>/settings", methods=["POST"])
@loginrequired
def config_POST(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.write)

    valid = Validation(request)
    description = valid.require("description")
    website = valid.optional("website")
    valid.expect(not website or valid_url(website),
            "Website must be a valid http or https URL")
    if not valid.ok:
        return render_template("project-config.html", view="add more",
                owner=owner, project=project, **valid.kwargs)

    project.description = description
    project.website = website
    db.session.commit()

    return redirect(url_for("projects.summary_GET",
        owner=current_user.canonical_name,
        project_name=project.name))

@projects.route("/<owner>/<project_name>/delete", methods=["POST"])
@loginrequired
def delete_POST(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    project.summary_repo_id = None
    db.session.delete(project)
    db.session.commit()
    return redirect(url_for("public.index"))

@projects.route("/<owner>/<project_name>/feature", methods=["POST"])
@adminrequired
def feature_POST(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.read)
    valid = Validation(request)

    feature = Feature()
    feature.project_id = project.id
    feature.summary = valid.require("summary")
    if not valid.ok:
        abort(400) # admin-only route, who cares
    db.session.add(feature)
    db.session.commit()
    return redirect(url_for("public.project_index"))
