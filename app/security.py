from functools import wraps

from flask import flash, g, redirect, request, session, url_for

from app import db
from app.models import Permission, Project, ProjectMember, User
from app.services.security_service import PROJECT_ACCESS_LEVELS, SecurityService

SESSION_USER_KEY = "user_id"
SESSION_PROJECT_KEY = "active_project_id"
PROJECT_ACCESS_ORDER = {"viewer": 1, "editor": 2, "executor": 2, "owner": 3}


def load_current_user():
    user_id = session.get(SESSION_USER_KEY)
    user = db.session.get(User, user_id) if user_id else None
    g.current_user = user
    g.current_permissions = None
    return user


def get_current_user():
    return getattr(g, "current_user", None)


def login_user(user):
    session[SESSION_USER_KEY] = user.id
    g.current_user = user
    g.current_permissions = None


def logout_user():
    session.pop(SESSION_USER_KEY, None)
    session.pop(SESSION_PROJECT_KEY, None)
    g.current_user = None
    g.current_permissions = None


def _collect_permissions(user):
    if not user:
        return set()
    if user.is_superuser:
        return {permission.code for permission in Permission.query.all()}

    codes = set()
    for role in user.roles:
        for permission in role.permissions:
            codes.add(permission.code)
    return codes


def get_user_permissions(user=None):
    user = user or get_current_user()
    cached = getattr(g, "current_permissions", None)
    if user and cached is not None:
        return cached
    permissions = _collect_permissions(user)
    if user:
        g.current_permissions = permissions
    return permissions


def has_permission(code):
    user = get_current_user()
    if not user:
        return False
    if user.is_superuser:
        return True
    return code in get_user_permissions(user)


def require_login(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not get_current_user():
            flash("请先登录后再访问系统。", "warning")
            return redirect(url_for("auth.login", next=request.url))
        return func(*args, **kwargs)

    return wrapper


def require_permission(*permission_codes, any_of=False):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user:
                flash("请先登录后再访问系统。", "warning")
                return redirect(url_for("auth.login", next=request.url))

            if user.is_superuser:
                return func(*args, **kwargs)

            permissions = get_user_permissions(user)
            if any_of:
                allowed = any(code in permissions for code in permission_codes)
            else:
                allowed = all(code in permissions for code in permission_codes)

            if not allowed:
                flash("你没有访问该功能的权限。", "danger")
                return redirect(url_for("dashboard.index"))
            return func(*args, **kwargs)

        return wrapper

    return decorator


def project_access_level(user, project_id):
    if not user:
        return None
    if user.is_superuser:
        return "owner"
    member = ProjectMember.query.filter_by(project_id=project_id, user_id=user.id).first()
    return member.access_level if member else None


def can_access_project(user, project_id):
    return bool(project_access_level(user, project_id))


def can_edit_project(user, project_id):
    if not user:
        return False
    if user.is_superuser:
        return True
    level = project_access_level(user, project_id)
    return bool(level and PROJECT_ACCESS_ORDER.get(level, 0) >= PROJECT_ACCESS_ORDER["editor"])


def can_run_project(user, project_id):
    if not user:
        return False
    if user.is_superuser:
        return True
    level = project_access_level(user, project_id)
    return bool(level and PROJECT_ACCESS_ORDER.get(level, 0) >= PROJECT_ACCESS_ORDER["executor"])


def accessible_projects(user=None):
    user = user or get_current_user()
    if not user:
        return []
    query = Project.query
    if not user.is_superuser:
        query = query.join(ProjectMember, ProjectMember.project_id == Project.id).filter(ProjectMember.user_id == user.id)
    return query.order_by(Project.created_at.desc()).all()


def accessible_project_ids(user=None):
    return [project.id for project in accessible_projects(user)]


def ensure_active_project_accessible():
    user = get_current_user()
    if not user:
        session.pop(SESSION_PROJECT_KEY, None)
        g.active_project_id = None
        return None

    raw_project_id = session.get(SESSION_PROJECT_KEY)
    if not raw_project_id:
        g.active_project_id = None
        return None

    try:
        project_id = int(raw_project_id)
    except (TypeError, ValueError):
        session.pop(SESSION_PROJECT_KEY, None)
        g.active_project_id = None
        return None

    if not can_access_project(user, project_id):
        session.pop(SESSION_PROJECT_KEY, None)
        g.active_project_id = None
        return None

    g.active_project_id = project_id
    return project_id


def set_active_project(project_id):
    user = get_current_user()
    if not user:
        session.pop(SESSION_PROJECT_KEY, None)
        g.active_project_id = None
        return None
    if not project_id:
        session.pop(SESSION_PROJECT_KEY, None)
        g.active_project_id = None
        return None
    if not can_access_project(user, project_id):
        return None
    session[SESSION_PROJECT_KEY] = project_id
    g.active_project_id = project_id
    return project_id


def current_project_id():
    return getattr(g, "active_project_id", session.get(SESSION_PROJECT_KEY))


def current_project():
    project_id = current_project_id()
    return db.session.get(Project, project_id) if project_id else None


def register_request_context():
    load_current_user()
    ensure_active_project_accessible()


def can_manage_project_members(user=None):
    user = user or get_current_user()
    return bool(user and (user.is_superuser or has_permission("project_member:manage")))
