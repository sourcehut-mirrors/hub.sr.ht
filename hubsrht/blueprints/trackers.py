from flask import Blueprint, render_template, request, redirect, url_for
from flask import abort
from hubsrht.projects import ProjectAccess, get_project
from hubsrht.services import todo
from hubsrht.types import Event, EventType, Tracker, Visibility
from srht.database import db
from srht.flask import paginate_query
from srht.oauth import current_user, loginrequired
from srht.search import search_by
from srht.validation import Validation

trackers = Blueprint("trackers", __name__)

@trackers.route("/<owner>/<project_name>/trackers")
def trackers_GET(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.read)
    trackers = (Tracker.query
            .filter(Tracker.project_id == project.id)
            .order_by(Tracker.updated.desc()))
    if not current_user or current_user.id != owner.id:
        trackers = trackers.filter(Tracker.visibility == Visibility.public)

    terms = request.args.get("search")
    search_error = None
    try:
        trackers = search_by(trackers, terms,
                [Tracker.name, Tracker.description])
    except ValueError as ex:
        search_error = str(ex)

    trackers, pagination = paginate_query(trackers)
    return render_template("trackers.html", view="tickets",
            owner=owner, project=project, trackers=trackers,
            search=terms, search_error=search_error,
            **pagination)

@trackers.route("/<owner>/<project_name>/trackers/new")
@loginrequired
def new_GET(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    # TODO: Pagination
    trackers = todo.get_trackers(owner)
    trackers = sorted(trackers, key=lambda r: r["updated"], reverse=True)
    existing = [t.remote_id for t in (Tracker.query
            .filter(Tracker.project_id == project.id)).all()]
    return render_template("tracker-new.html", view="new-resource",
            owner=owner, project=project, trackers=trackers, existing=existing)

@trackers.route("/<owner>/<project_name>/trackers/new", methods=["POST"])
@loginrequired
def new_POST(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    valid = Validation(request)
    if "create" in valid:
        remote_tracker = todo.create_tracker(owner, valid, project.visibility)
        trackers = todo.get_trackers(owner)
        trackers = sorted(trackers, key=lambda r: r["updated"], reverse=True)
        if not valid.ok:
            existing = [t.remote_id for t in (Tracker.query
                    .filter(Tracker.project_id == project.id)).all()]
            return render_template("tracker-new.html",
                    view="new-resource", owner=owner, project=project,
                    trackers=trackers, existing=existing, **valid.kwargs)
    else:
        tracker_name = None
        for field in valid.source:
            if field.startswith("existing-"):
                tracker_name = field[len("existing-"):]
                break

        if not tracker_name:
            search = valid.optional("search")
            trackers = todo.get_trackers(owner)
            trackers = filter(lambda r:
                    search.lower() in r["name"].lower()
                    or search.lower() in r["description"].lower(), trackers)
            trackers = sorted(trackers, key=lambda r: r["updated"], reverse=True)
            existing = [t.remote_id for t in (Tracker.query
                    .filter(Tracker.project_id == project.id)).all()]
            return render_template("tracker-new.html", view="new-resource",
                    owner=owner, project=project, trackers=trackers,
                    existing=existing, search=search)

        remote_tracker = todo.get_tracker(owner, tracker_name)

    tracker = Tracker()
    tracker.remote_id = remote_tracker["id"]
    tracker.project_id = project.id
    tracker.owner_id = owner.id
    tracker.name = remote_tracker["name"]
    tracker.description = remote_tracker["description"]
    if any(remote_tracker["default_access"]):
        tracker.visibility = Visibility.public
    else:
        tracker.visibility = Visibility.unlisted
    db.session.add(tracker)
    db.session.flush()

    event = Event()
    event.event_type = EventType.tracker_added
    event.tracker_id = tracker.id
    event.project_id = project.id
    event.user_id = project.owner_id
    db.session.add(event)

    todo.ensure_user_webhooks(owner)
    todo.ensure_tracker_webhooks(tracker)

    db.session.commit()

    return redirect(url_for("projects.summary_GET",
        owner=owner.canonical_name, project_name=project.name))

@trackers.route("/<owner>/<project_name>/trackers/manage")
@loginrequired
def manage_GET(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    trackers = (Tracker.query
            .filter(Tracker.project_id == project.id)
            .order_by(Tracker.updated.desc()))

    terms = request.args.get("search")
    search_error = None
    try:
        trackers = search_by(trackers, terms,
                [Tracker.name, Tracker.description])
    except ValueError as ex:
        search_error = str(ex)

    trackers, pagination = paginate_query(trackers)
    return render_template("trackers-manage.html", view="tickets",
            owner=owner, project=project, trackers=trackers,
            search=terms, search_error=search_error,
            **pagination)

@trackers.route("/<owner>/<project_name>/trackers/delete/<int:tracker_id>")
@loginrequired
def delete_GET(owner, project_name, tracker_id):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    tracker = (Tracker.query
        .filter(Tracker.id == tracker_id)
        .filter(Tracker.project_id == project.id)).one_or_none()
    if not tracker:
        abort(404)
    return render_template("resource-delete.html", view="tickets",
            owner=owner, project=project, resource=tracker,
            resource_type="ticket tracker")

@trackers.route("/<owner>/<project_name>/trackers/delete/<int:tracker_id>",
        methods=["POST"])
@loginrequired
def delete_POST(owner, project_name, tracker_id):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    tracker = (Tracker.query
        .filter(Tracker.id == tracker_id)
        .filter(Tracker.project_id == project.id)).one_or_none()
    if not tracker:
        abort(404)
    tracker_name = tracker.name
    db.session.delete(tracker)
    db.session.commit()

    valid = Validation(request)
    delete_remote = valid.optional("delete-remote") == "on"
    if delete_remote:
        todo.delete_tracker(owner, tracker_name)

    return redirect(url_for("projects.summary_GET",
        owner=owner.canonical_name, project_name=project.name))
