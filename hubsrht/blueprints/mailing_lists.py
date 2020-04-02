from flask import Blueprint, render_template, request, redirect, url_for
from hubsrht.projects import ProjectAccess, get_project
from hubsrht.services import lists
from hubsrht.types import Event, EventType
from hubsrht.types import MailingList
from srht.config import get_origin
from srht.database import db
from srht.flask import paginate_query
from srht.oauth import current_user, loginrequired
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
    return render_template("mailing-lists.html", view="mailing lists",
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
    return render_template("mailing-list-new.html", view="new-resource",
            owner=owner, project=project, lists=mls)

def lists_from_template(owner, project, template):
    project_url = url_for("projects.summary_GET",
        owner=owner.canonical_name, project_name=project.name)
    project_url = get_origin("hub.sr.ht", external=True) + project_url
    templates = {
        "public-inbox": ["public-inbox"],
        "announce-devel": [f"{project.name}-announce", f"{project.name}-devel"],
        "announce-devel-discuss": [
            f"{project.name}-announce",
            f"{project.name}-devel",
            f"{project.name}-discuss", 
        ],
    }
    descs = {
        "public-inbox": f"""
General catch-all for patches, questions, and discussions for any of
{current_user.canonical_name}'s projects which do not have their own mailing
list.

When posting patches to this list, please edit the [PATCH] line to include the
specific project you're contributing to, e.g.

    [PATCH {project.name} v2] Add thing to stuff
""",
        f"{project.name}-announce": f"""
Low-volume mailing list for announcements related to the
[{project.name}]({project_url}) project.
""",
        f"{project.name}-devel": f"""
Mailing list for development discussion and patches related to the
[{project.name}]({project_url}) project. For help sending patches to this
list, please consult [git-send-email.io](https://git-send-email.io).
""",
        f"{project.name}-discuss": f"""
Mailing list for end-user discussion and questions related to the
[{project.name}]({project_url}) project.
""",
    }
    template = templates[template]

    for list_name in template:
        try:
            mailing_list = lists.get_list(owner, list_name)
        except:
            mailing_list = lists.create_list(owner, Validation({
                "name": list_name,
                "description": descs[list_name],
            }))

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

    return redirect(project_url)

@mailing_lists.route("/<owner>/<project_name>/lists/new", methods=["POST"])
@loginrequired
def new_POST(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    valid = Validation(request)
    if "from-template" in valid:
        template = valid.require("template")
        valid.expect(template in ["public-inbox",
                "announce-devel", "announce-devel-discuss"],
            "Invalid template selection")
        if not valid.ok:
            mls = lists.get_lists(owner)
            mls = sorted(mls, key=lambda r: r["updated"], reverse=True)
            return render_template("mailing-list-new.html",
                    view="new-resource", owner=owner, project=project,
                    lists=mls, **valid.kwargs)
        return lists_from_template(owner, project, template)
    elif "create" in valid:
        mailing_list = lists.create_list(owner, valid)
        if not valid.ok:
            mls = lists.get_lists(owner)
            mls = sorted(mls, key=lambda r: r["updated"], reverse=True)
            return render_template("mailing-list-new.html",
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
            mls = lists.get_lists(owner)
            # TODO: Search properly
            mls = filter(lambda r: search.lower() in r["name"].lower(), mls)
            mls = sorted(mls, key=lambda r: r["updated"], reverse=True)
            return render_template("mailing-list-new.html",
                    view="new-resource", owner=owner, project=project,
                    lists=mls, search=search)
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
    return render_template("mailing-lists-manage.html",
            view="mailing lists", owner=owner, project=project,
            search=terms, search_error=search_error,
            mailing_lists=mailing_lists,
            **pagination)

@mailing_lists.route("/<owner>/<project_name>/lists/delete/<int:list_id>")
@loginrequired
def delete_GET(owner, project_name, list_id):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    mailing_list = (MailingList.query
        .filter(MailingList.id == list_id)
        .filter(MailingList.project_id == project.id)).one_or_none()
    if not mailing_list:
        abort(404)
    return render_template("resource-delete.html", view="mailing lists",
            owner=owner, project=project, resource=mailing_list,
            resource_type="mailing list",
            undeletable=True) # TODO: mailing list deletion

@mailing_lists.route("/<owner>/<project_name>/lists/delete/<int:list_id>",
        methods=["POST"])
@loginrequired
def delete_POST(owner, project_name, list_id):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    mailing_list = (MailingList.query
        .filter(MailingList.id == list_id)
        .filter(MailingList.project_id == project.id)).one_or_none()
    if not mailing_list:
        abort(404)
    db.session.delete(mailing_list)

    valid = Validation(request)
    delete_remote = valid.optional("delete-remote") == "on"
    if delete_remote:
        assert False # TODO: mailing list deletion

    db.session.commit()
    return redirect(url_for("projects.summary_GET",
        owner=owner.canonical_name, project_name=project.name))
