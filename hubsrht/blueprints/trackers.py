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
