from flask import g, request, session

SESSION_KEY = "active_project_id"


def sync_active_project_id():
    if "project_id" in request.args:
        raw_value = request.args.get("project_id")
        if raw_value in (None, ""):
            session.pop(SESSION_KEY, None)
            g.active_project_id = None
            return None

        try:
            project_id = int(raw_value)
        except (TypeError, ValueError):
            session.pop(SESSION_KEY, None)
            g.active_project_id = None
            return None

        session[SESSION_KEY] = project_id
        g.active_project_id = project_id
        return project_id

    g.active_project_id = session.get(SESSION_KEY)
    return g.active_project_id


def get_active_project_id(default=None):
    value = getattr(g, "active_project_id", session.get(SESSION_KEY))
    if value is None:
        return default
    return value


def resolve_project_id(default=None):
    if "project_id" in request.args:
        raw_value = request.args.get("project_id")
        if raw_value in (None, ""):
            return None
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return default
    return get_active_project_id(default)
