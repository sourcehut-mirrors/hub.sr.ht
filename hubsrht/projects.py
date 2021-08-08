from flask import abort
from hubsrht.types import Project, User, Visibility
from srht.oauth import current_user
from enum import Enum

class ProjectAccess(Enum):
    read = "read"
    write = "write"

def get_project(owner, project_name, access, user=current_user):
    if owner.startswith("~"):
        owner = owner[1:]
    project = (Project.query
            .join(User, Project.owner_id == User.id)
            .filter(User.username == owner)
            .filter(Project.name.ilike(project_name.replace('_', '\\_')))
        ).one_or_none()
    if not project:
        abort(404)
    if user != None and user.id == project.owner_id:
        return project.owner, project
    if access == ProjectAccess.write:
        abort(401)
    # TODO: ACLs
    if project.visibility in (Visibility.public, Visibility.unlisted):
        return project.owner, project
    elif project.visibility == Visibility.private:
        abort(401)
    assert False
