from flask import Blueprint, render_template, request, redirect, url_for
from hubsrht.projects import ProjectAccess, get_project
from hubsrht.services import git
from hubsrht.types import Event, EventType
from hubsrht.types import RepoType, SourceRepo
from srht.database import db
from srht.flask import paginate_query
from srht.oauth import loginrequired
from srht.search import search_by
from srht.validation import Validation

sources = Blueprint("sources", __name__)

@sources.route("/<owner>/<project_name>/sources")
@loginrequired
def sources_GET(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.read)
    sources = (SourceRepo.query
            .filter(SourceRepo.project_id == project.id)
            .order_by(SourceRepo.updated.desc()))

    terms = request.args.get("search")
    search_error = None
    try:
        sources = search_by(sources, terms,
                [SourceRepo.name, SourceRepo.description])
    except ValueError as ex:
        search_error = str(ex)

    sources, pagination = paginate_query(sources)
    return render_template("project-sources.html", view="sources",
            owner=owner, project=project, sources=sources,
            search=terms, search_error=search_error,
            **pagination)

@sources.route("/<owner>/<project_name>/sources/new")
@loginrequired
def new_GET(owner, project_name):
    # TODO: Redirect appropriately if this instance only has git or hg support
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    return render_template("project-sources-new.html", view="new-resource",
            owner=owner, project=project)

@sources.route("/<owner>/<project_name>/git/new")
@loginrequired
def git_new_GET(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    # TODO: Pagination
    repos = git.get_repos(owner)
    repos = sorted(repos, key=lambda r: r["updated"], reverse=True)
    return render_template("project-sources-select.html",
            view="new-resource", vcs="git",
            owner=owner, project=project, repos=repos,
            existing=[]) # TODO: Fetch existing repos for this project

@sources.route("/<owner>/<project_name>/git/new", methods=["POST"])
@loginrequired
def git_new_POST(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    valid = Validation(request)
    if "create" in valid:
        git_repo = git.create_repo(owner, valid)
        if not valid.ok:
            repos = git.get_repos(owner)
            return render_template("project-sources-select.html",
                    view="new-resource", vcs="git",
                    owner=owner, project=project, repos=repos,
                    existing=[], **valid.kwargs)
    else:
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
    db.session.flush()

    event = Event()
    event.event_type = EventType.source_repo_added
    event.source_repo_id = repo.id
    event.project_id = project.id
    event.user_id = project.owner_id
    db.session.add(event)

    git.ensure_user_webhooks(owner)
    git.ensure_repo_webhooks(owner, repo.name)

    db.session.commit()

    return redirect(url_for("projects.summary_GET",
        owner=owner.canonical_name, project_name=project.name))

@sources.route("/<owner>/<project_name>/sources/manage")
@loginrequired
def manage_GET(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    sources = (SourceRepo.query
            .filter(SourceRepo.project_id == project.id)
            .order_by(SourceRepo.updated.desc()))

    terms = request.args.get("search")
    search_error = None
    try:
        sources = search_by(sources, terms,
                [SourceRepo.name, SourceRepo.description])
    except ValueError as ex:
        search_error = str(ex)

    sources, pagination = paginate_query(sources)
    return render_template("project-sources-manage.html", view="sources",
            owner=owner, project=project, sources=sources,
            search=terms, search_error=search_error,
            **pagination)

@sources.route("/<owner>/<project_name>/sources/summary/<int:repo_id>",
        methods=["POST"])
@loginrequired
def summary_POST(owner, project_name, repo_id):
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
