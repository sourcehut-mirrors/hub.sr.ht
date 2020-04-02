from flask import Blueprint, render_template, request, redirect, url_for
from hubsrht.projects import ProjectAccess, get_project
from hubsrht.services import todo
from hubsrht.types import Event, EventType, Tracker
from srht.database import db
from srht.flask import paginate_query
from srht.oauth import loginrequired
from srht.search import search_by
from srht.validation import Validation

trackers = Blueprint("trackers", __name__)

@trackers.route("/<owner>/<project_name>/trackers/new")
@loginrequired
def new_GET(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    # TODO: Pagination
    trackers = todo.get_trackers(owner)
    trackers = sorted(trackers, key=lambda r: r["updated"], reverse=True)
    return render_template("tracker-new.html", view="new-resource",
            owner=owner, project=project, trackers=trackers)

@trackers.route("/<owner>/<project_name>/trackers/new", methods=["POST"])
@loginrequired
def new_POST(owner, project_name):
    owner, project = get_project(owner, project_name, ProjectAccess.write)
    valid = Validation(request)
    if "create" in valid:
        assert False # TODO
    else:
        tracker_name = None
        for field in valid.source:
            if field.startswith("existing-"):
                tracker_name = field[len("existing-"):]
                break

        if not tracker_name:
            search = valid.optional("search")
            trackers = todo.get_trackers(owner)
            # TODO: Search properly
            tracker = filter(lambda r: search.lower() in r["name"].lower(), trackers)
            tracker = sorted(trackers, key=lambda r: r["updated"], reverse=True)
            return render_template("tracker-new.html", view="new-resource",
                    owner=owner, project=project, trackers=trackers,
                    search=search)

        remote_tracker = todo.get_tracker(owner, tracker_name)

    tracker = Tracker()
    tracker.remote_id = remote_tracker["id"]
    tracker.project_id = project.id
    tracker.owner_id = owner.id
    tracker.name = remote_tracker["name"]
    tracker.description = remote_tracker["description"]
    db.session.add(tracker)
    db.session.flush()

    event = Event()
    event.event_type = EventType.tracker_added
    event.tracker_id = tracker.id
    event.project_id = project.id
    event.user_id = project.owner_id
    db.session.add(event)

    todo.ensure_user_webhooks(owner)
    todo.ensure_tracker_webhooks(owner, tracker.name)

    db.session.commit()

    return redirect(url_for("projects.summary_GET",
        owner=owner.canonical_name, project_name=project.name))
