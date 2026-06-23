from datetime import datetime, timedelta

from flask import Blueprint, render_template, request

from app.routes import handle_page_error, handle_success
from app.security import accessible_project_ids, accessible_projects, require_permission
from app.services.base_service import ServiceError
from app.services.environment_service import EnvironmentService
from app.services.project_service import ProjectService
from app.services.variable_service import VariableService
from app.project_context import resolve_project_id

variable_bp = Blueprint("variable", __name__, url_prefix="/variables")


@variable_bp.route("/")
@require_permission("variable:view")
def list_variables():
    project_id = request.args.get("project_id", type=int) or resolve_project_id()
    environment_id = request.args.get("environment_id", type=int)
    keyword = (request.args.get("keyword") or "").strip()
    scope = (request.args.get("scope") or "").strip()

    variables = VariableService.list_all(project_id=project_id, environment_id=environment_id)
    if keyword:
        lowered = keyword.lower()
        variables = [
            item
            for item in variables
            if lowered in item.name.lower()
            or lowered in (item.value or "").lower()
            or lowered in (item.description or "").lower()
        ]
    if scope in {"project", "environment"}:
        variables = [item for item in variables if item.scope == scope]
    projects = accessible_projects()
    environments = EnvironmentService.list_all(project_id=project_id) if project_id else []
    project_ids = accessible_project_ids()
    all_environments = [env for env in EnvironmentService.list_all() if env.project_id in project_ids] if project_ids else []

    return render_template(
        "variables/list.html",
        variables=variables,
        projects=projects,
        environments=environments,
        all_environments=all_environments,
        selected_project_id=project_id,
        selected_environment_id=environment_id,
        keyword=keyword,
        selected_scope=scope,
        recent_cutoff=datetime.utcnow() - timedelta(days=7),
    )


@variable_bp.route("/create", methods=["POST"])
@require_permission("variable:create")
def create_variable():
    try:
        VariableService.create(
            project_id=request.form.get("project_id", type=int),
            name=request.form.get("name"),
            value=request.form.get("value", ""),
            scope=request.form.get("scope", "project"),
            environment_id=request.form.get("environment_id", type=int),
            description=request.form.get("description", ""),
        )
        return handle_success("变量创建成功。", "variable.list_variables")
    except ServiceError as exc:
        return handle_page_error(str(exc), "variable.list_variables")


@variable_bp.route("/<int:variable_id>/edit", methods=["POST"])
@require_permission("variable:edit")
def edit_variable(variable_id):
    try:
        VariableService.update(
            variable_id=variable_id,
            name=request.form.get("name"),
            value=request.form.get("value", ""),
            scope=request.form.get("scope", "project"),
            environment_id=request.form.get("environment_id", type=int),
            description=request.form.get("description", ""),
        )
        return handle_success("变量更新成功。", "variable.list_variables")
    except ServiceError as exc:
        return handle_page_error(str(exc), "variable.list_variables")


@variable_bp.route("/<int:variable_id>/delete", methods=["POST"])
@require_permission("variable:delete")
def delete_variable(variable_id):
    try:
        VariableService.delete(variable_id)
        return handle_success("变量删除成功。", "variable.list_variables")
    except ServiceError as exc:
        return handle_page_error(str(exc), "variable.list_variables")
