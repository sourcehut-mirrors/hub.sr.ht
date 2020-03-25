from flask import Blueprint, render_template, request, redirect, url_for
from hubsrht.projects import ProjectAccess, get_project
from hubsrht.services import git, lists
from hubsrht.types import Project, RepoType, SourceRepo, Visibility
from hubsrht.types import MailingList
from srht.config import get_origin
from srht.database import db
from srht.flask import paginate_query
from srht.oauth import current_user, loginrequired
from srht.validation import Validation

projects = Blueprint("projects", __name__)
origin = get_origin("hub.sr.ht")

@projects.route("/<owner>/<project_name>")
def summary_GET(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.read)

    summary = None
    if project.summary_repo_id is not None:
        repo = project.summary_repo
        assert repo.repo_type != RepoType.hg # TODO
        summary = git.get_readme(owner, repo.name)

    return render_template("project-summary.html", view="summary",
            owner=owner, project=project, summary=summary)

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

@projects.route("/<owner>/<project_name>/sources")
@loginrequired
def sources_GET(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.read)
    sources = (SourceRepo.query
            .filter(SourceRepo.project_id == project.id)
            .order_by(SourceRepo.updated.desc()))
    sources, pagination = paginate_query(sources)
    return render_template("project-sources.html", view="sources",
            owner=owner, project=project, sources=sources, **pagination)

@projects.route("/<owner>/<project_name>/sources/new")
@loginrequired
def sources_new_GET(owner, project_name):
    # TODO: Redirect appropriately if this instance only has git or hg support
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    return render_template("project-sources-new.html", view="new-resource",
            owner=owner, project=project)

@projects.route("/<owner>/<project_name>/sources/new", methods=["POST"])
@loginrequired
def sources_new_POST(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    valid = Validation(request)
    if "git" in valid:
        return redirect(url_for("projects.sources_git_new_GET",
            owner=owner.canonical_name, project_name=project.name))
    if "hg" in valid:
        # TODO: Hg repos
        return redirect(url_for("projects.sources_hg_new_GET",
            owner=owner.canonical_name, project_name=project.name))

@projects.route("/<owner>/<project_name>/git/new")
@loginrequired
def sources_git_new_GET(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    # TODO: Pagination
    repos = git.get_repos(owner)
    repos = sorted(repos, key=lambda r: r["updated"], reverse=True)
    return render_template("project-sources-select.html",
            view="new-resource", vcs="git",
            owner=owner, project=project, repos=repos,
            existing=[]) # TODO: Fetch existing repos for this project

@projects.route("/<owner>/<project_name>/git/new", methods=["POST"])
@loginrequired
def sources_git_new_POST(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    valid = Validation(request)
    if "create" in valid:
        assert False # TODO: Create repo

    repo_name = None
    for field in valid.source:
        if field.startswith("existing-"):
            repo_name = field[len("existing-"):]
            break

    if not repo_name:
        search = valid.optional("search")
        repos = git.get_repos(owner)
        # TODO: Search properly
        repos = filter(lambda r: search.lower() in r["name"].lower(), repos)
        repos = sorted(repos, key=lambda r: r["updated"], reverse=True)
        # TODO: Fetch existing repos for this project
        return render_template("project-sources-select.html",
                view="new-resource", vcs="git",
                owner=owner, project=project, repos=repos,
                existing=[], search=search)

    git_repo = git.get_repo(owner, repo_name)
    repo = SourceRepo()
    repo.remote_id = git_repo["id"]
    repo.project_id = project.id
    repo.owner_id = owner.id
    repo.name = git_repo["name"]
    repo.description = git_repo["description"]
    repo.repo_type = RepoType.git
    db.session.add(repo)

    git.ensure_user_webhooks(owner, {
        url_for("webhooks.git_repo_update"): ["repo:update", "repo:delete"],
    })

    db.session.commit()

    return redirect(url_for("projects.summary_GET",
        owner=owner.canonical_name, project_name=project.name))

@projects.route("/<owner>/<project_name>/sources/set-summary/<int:repo_id>",
        methods=["POST"])
@loginrequired
def set_summary_repo(owner, project_name, repo_id):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    repo = (SourceRepo.query
        .filter(SourceRepo.id == repo_id)
        .filter(SourceRepo.project_id == project.id)).one_or_none()
    if not repo:
        abort(404)
    project.summary_repo_id = repo.id
    db.session.commit()
    return redirect(url_for("projects.summary_GET",
        owner=owner.canonical_name, project_name=project.name))

@projects.route("/<owner>/<project_name>/lists")
@loginrequired
def mailing_lists_GET(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.read)
    mailing_lists = (MailingList.query
            .filter(MailingList.project_id == project.id)
            .order_by(MailingList.updated.desc()))
    mailing_lists, pagination = paginate_query(mailing_lists)
    return render_template("project-mailing-lists.html", view="mailing lists",
            owner=owner, project=project, mailing_lists=mailing_lists,
            **pagination)

@projects.route("/<owner>/<project_name>/lists/new")
@loginrequired
def mailing_lists_new_GET(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    # TODO: Pagination
    mls = lists.get_lists(owner)
    mls = sorted(mls, key=lambda r: r["updated"], reverse=True)
    return render_template("project-lists-new.html", view="new-resource",
            owner=owner, project=project, lists=mls)

@projects.route("/<owner>/<project_name>/lists/new", methods=["POST"])
@loginrequired
def mailing_lists_new_POST(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    valid = Validation(request)
    if "create" in valid:
        assert False # TODO: Create list
    if "from-template" in valid:
        assert False # TODO: Create lists from template

    list_name = None
    for field in valid.source:
        if field.startswith("existing-"):
            list_name = field[len("existing-"):]
            break

    mailing_list = lists.get_list(owner, list_name)
    ml = MailingList()
    ml.remote_id = mailing_list["id"]
    ml.project_id = project.id
    ml.owner_id = project.owner_id
    ml.name = mailing_list["name"]
    ml.description = mailing_list["description"]
    db.session.add(ml)

    lists.ensure_mailing_list_webhooks(owner, list_name, {
        url_for("webhooks.mailing_list_update"): ["list:update", "list:delete"],
    })

    db.session.commit()

    return redirect(url_for("projects.summary_GET",
        owner=owner.canonical_name, project_name=project.name))
