from flask import Blueprint, flash, redirect, render_template, request, url_for
from collections import defaultdict

from app.models import Project
from app.security import accessible_projects, get_current_user
from app.services.base_service import ServiceError, commit_session
from app.services.security_service import PROJECT_ACCESS_LEVELS, SecurityService
from app.security import require_permission

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/users")
@require_permission("user:manage")
def users_page():
    users = SecurityService.list_users()
    roles = SecurityService.list_roles()
    user_payloads = [
        {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name or "",
            "email": user.email or "",
            "is_active": user.is_active,
            "is_superuser": user.is_superuser,
            "role_codes": [role.code for role in user.roles],
        }
        for user in users
    ]
    return render_template(
        "admin/users.html",
        users=users,
        roles=roles,
        user_payloads=user_payloads,
    )


@admin_bp.route("/users/create", methods=["POST"])
@require_permission("user:manage")
def create_user():
    try:
        SecurityService.create_user(
            username=request.form.get("username"),
            display_name=request.form.get("display_name", ""),
            email=request.form.get("email", ""),
            password=request.form.get("password"),
            is_active=request.form.get("is_active") == "1",
            is_superuser=request.form.get("is_superuser") == "1",
            role_codes=request.form.getlist("role_codes"),
        )
        flash("用户创建成功。", "success")
    except ServiceError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin.users_page"))


@admin_bp.route("/users/<int:user_id>/edit", methods=["POST"])
@require_permission("user:manage")
def edit_user(user_id):
    try:
        SecurityService.update_user(
            user_id=user_id,
            username=request.form.get("username"),
            display_name=request.form.get("display_name", ""),
            email=request.form.get("email", ""),
            password=request.form.get("password", ""),
            is_active=request.form.get("is_active") == "1",
            is_superuser=request.form.get("is_superuser") == "1",
            role_codes=request.form.getlist("role_codes"),
        )
        flash("用户更新成功。", "success")
    except ServiceError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin.users_page"))


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@require_permission("user:manage")
def delete_user(user_id):
    try:
        user = SecurityService.get_user_by_id(user_id)
        if user.is_superuser:
            raise ServiceError("超级管理员不能删除。")
        from app import db

        db.session.delete(user)
        commit_session()
        flash("用户删除成功。", "success")
    except ServiceError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin.users_page"))


@admin_bp.route("/roles")
@require_permission("role:manage")
def roles_page():
    permissions = SecurityService.list_permissions()
    roles = SecurityService.list_roles()
    grouped_permissions = defaultdict(list)
    for permission in permissions:
        grouped_permissions[permission.group_name or "其他"].append(permission)
    role_payloads = [
        {
            "id": role.id,
            "code": role.code,
            "name": role.name,
            "description": role.description,
            "sort_order": role.sort_order,
            "is_system": role.is_system,
            "permission_codes": [permission.code for permission in role.permissions],
        }
        for role in roles
    ]
    return render_template(
        "admin/roles.html",
        roles=roles,
        permissions=permissions,
        grouped_permissions=dict(grouped_permissions),
        role_payloads=role_payloads,
    )


@admin_bp.route("/roles/create", methods=["POST"])
@require_permission("role:manage")
def create_role():
    try:
        SecurityService.create_role(
            code=request.form.get("code"),
            name=request.form.get("name"),
            description=request.form.get("description", ""),
            is_system=request.form.get("is_system") == "1",
            sort_order=request.form.get("sort_order", type=int) or 0,
            permission_codes=request.form.getlist("permission_codes"),
        )
        flash("角色创建成功。", "success")
    except ServiceError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin.roles_page"))


@admin_bp.route("/roles/<int:role_id>/edit", methods=["POST"])
@require_permission("role:manage")
def edit_role(role_id):
    try:
        SecurityService.update_role(
            role_id=role_id,
            code=request.form.get("code"),
            name=request.form.get("name"),
            description=request.form.get("description", ""),
            is_system=request.form.get("is_system") == "1",
            sort_order=request.form.get("sort_order", type=int) or 0,
            permission_codes=request.form.getlist("permission_codes"),
        )
        flash("角色更新成功。", "success")
    except ServiceError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin.roles_page"))


@admin_bp.route("/roles/<int:role_id>/delete", methods=["POST"])
@require_permission("role:manage")
def delete_role(role_id):
    try:
        role = SecurityService.get_role_by_id(role_id)
        if role.is_system:
            raise ServiceError("系统角色不能删除。")
        from app import db

        db.session.delete(role)
        commit_session()
        flash("角色删除成功。", "success")
    except ServiceError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin.roles_page"))


@admin_bp.route("/projects")
@require_permission("project_member:manage")
def projects_page():
    user = get_current_user()
    projects = Project.query.order_by(Project.created_at.desc()).all() if user and user.is_superuser else accessible_projects(user)
    members = SecurityService.list_project_members()
    users = SecurityService.list_users()
    return render_template(
        "admin/projects.html",
        projects=projects,
        members=members,
        users=users,
        access_levels=PROJECT_ACCESS_LEVELS,
    )


@admin_bp.route("/projects/members", methods=["POST"])
@require_permission("project_member:manage")
def upsert_project_member():
    try:
        SecurityService.update_project_member(
            project_id=request.form.get("project_id", type=int),
            user_id=request.form.get("user_id", type=int),
            access_level=request.form.get("access_level", "viewer"),
            remark=request.form.get("remark", ""),
        )
        flash("项目成员设置成功。", "success")
    except ServiceError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin.projects_page"))


@admin_bp.route("/projects/members/<int:project_id>/<int:user_id>/delete", methods=["POST"])
@require_permission("project_member:manage")
def delete_project_member(project_id, user_id):
    try:
        SecurityService.remove_project_member(project_id=project_id, user_id=user_id)
        flash("项目成员移除成功。", "success")
    except ServiceError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin.projects_page"))


@admin_bp.route("/audit")
@require_permission("audit:view")
def audit_page():
    page = request.args.get("page", 1, type=int)
    project_id = request.args.get("project_id", type=int)
    pagination = SecurityService.list_audit_logs(page=page, per_page=20, project_id=project_id)
    return render_template(
        "admin/audit.html",
        pagination=pagination,
        projects=accessible_projects(get_current_user()),
        selected_project_id=project_id,
    )
