from flask import Blueprint, render_template, request, redirect, url_for
from hubsrht.projects import ProjectAccess, get_project
from hubsrht.services import lists
from hubsrht.types import Event, EventType
from hubsrht.types import MailingList
from srht.database import db
from srht.flask import paginate_query
from srht.oauth import loginrequired
from srht.search import search_by
from srht.validation import Validation

mailing_lists = Blueprint("mailing_lists", __name__)

@mailing_lists.route("/<owner>/<project_name>/lists")
@loginrequired
def lists_GET(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.read)
    mailing_lists = (MailingList.query
            .filter(MailingList.project_id == project.id)
            .order_by(MailingList.updated.desc()))

    terms = request.args.get("search")
    search_error = None
    try:
        mailing_lists = search_by(mailing_lists, terms,
                [MailingList.name, MailingList.description])
    except ValueError as ex:
        search_error = str(ex)

    mailing_lists, pagination = paginate_query(mailing_lists)
    return render_template("project-mailing-lists.html", view="mailing lists",
            owner=owner, project=project,
            search=terms, search_error=search_error,
            mailing_lists=mailing_lists,
            **pagination)

@mailing_lists.route("/<owner>/<project_name>/lists/new")
@loginrequired
def new_GET(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    # TODO: Pagination
    mls = lists.get_lists(owner)
    mls = sorted(mls, key=lambda r: r["updated"], reverse=True)
    return render_template("project-lists-new.html", view="new-resource",
            owner=owner, project=project, lists=mls)

@mailing_lists.route("/<owner>/<project_name>/lists/new", methods=["POST"])
@loginrequired
def new_POST(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    valid = Validation(request)
    if "from-template" in valid:
        assert False # TODO: Create lists from template
    elif "create" in valid:
        mailing_list = lists.create_list(owner, valid)
        if not valid.ok:
            mls = lists.get_lists(owner)
            mls = sorted(mls, key=lambda r: r["updated"], reverse=True)
            return render_template("project-lists-new.html",
                    view="new-resource", owner=owner, project=project,
                    lists=mls, **valid.kwargs)
    else:
        list_name = None
        for field in valid.source:
            if field.startswith("existing-"):
                list_name = field[len("existing-"):]
                break
        if not list_name:
            search = valid.optional("search")
            mls = lists.get_list(owner)
            # TODO: Search properly
            mls = filter(lambda r: search.lower() in r["name"].lower(), mls)
            mls = sorted(mls, key=lambda r: r["updated"], reverse=True)
            return render_template("project-lists-new.html",
                    view="new-resource", owner=owner, project=project,
                    lists=mls)
        mailing_list = lists.get_list(owner, list_name)

    ml = MailingList()
    ml.remote_id = mailing_list["id"]
    ml.project_id = project.id
    ml.owner_id = project.owner_id
    ml.name = mailing_list["name"]
    ml.description = mailing_list["description"]
    db.session.add(ml)
    db.session.flush()

    event = Event()
    event.event_type = EventType.mailing_list_added 
    event.mailing_list_id = ml.id
    event.project_id = project.id
    event.user_id = project.owner_id
    db.session.add(event)

    lists.ensure_mailing_list_webhooks(owner, ml.name)

    db.session.commit()

    return redirect(url_for("projects.summary_GET",
        owner=owner.canonical_name, project_name=project.name))

@mailing_lists.route("/<owner>/<project_name>/lists/manage")
@loginrequired
def manage_GET(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    mailing_lists = (MailingList.query
            .filter(MailingList.project_id == project.id)
            .order_by(MailingList.updated.desc()))

    terms = request.args.get("search")
    search_error = None
    try:
        mailing_lists = search_by(mailing_lists, terms,
                [MailingList.name, MailingList.description])
    except ValueError as ex:
        search_error = str(ex)

    mailing_lists, pagination = paginate_query(mailing_lists)
    return render_template("project-mailing-lists-manage.html",
            view="mailing lists", owner=owner, project=project,
            search=terms, search_error=search_error,
            mailing_lists=mailing_lists,
            **pagination)
