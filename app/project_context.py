from flask import g, request, session

from app.security import can_access_project, current_project_id as get_security_project_id, get_current_user
from app.security import ensure_active_project_accessible, set_active_project

SESSION_KEY = "active_project_id"
ALL_PROJECTS_VALUE = "__all__"


def sync_active_project_id():
    if "project_id" in request.args:
        raw_value = request.args.get("project_id")
        if raw_value in (None, "", ALL_PROJECTS_VALUE):
            session.pop(SESSION_KEY, None)
            g.active_project_id = None
            return None

        try:
            project_id = int(raw_value)
        except (TypeError, ValueError):
            session.pop(SESSION_KEY, None)
            g.active_project_id = None
            return None

        if set_active_project(project_id) is None:
            session.pop(SESSION_KEY, None)
            g.active_project_id = None
            return None
        return project_id

    ensure_active_project_accessible()
    return g.active_project_id


def get_active_project_id(default=None):
    value = getattr(g, "active_project_id", get_security_project_id())
    if value is None:
        return default
    return value


def resolve_project_id(default=None):
    if "project_id" in request.args:
        raw_value = request.args.get("project_id")
        if raw_value in (None, "", ALL_PROJECTS_VALUE):
            return None
        try:
            project_id = int(raw_value)
        except (TypeError, ValueError):
            return default
        user = get_current_user()
        if user and not can_access_project(user, project_id):
            return default
        return project_id
    return get_active_project_id(default)
