from flask import Blueprint, render_template, request

from app.routes import handle_page_error, handle_success
from app.services.base_service import ServiceError
from app.services.environment_service import EnvironmentService
from app.services.project_service import ProjectService
from app.services.variable_service import VariableService
from app.project_context import resolve_project_id

variable_bp = Blueprint("variable", __name__, url_prefix="/variables")


@variable_bp.route("/")
def list_variables():
    project_id = resolve_project_id()
    environment_id = request.args.get("environment_id", type=int)

    variables = VariableService.list_all(project_id=project_id, environment_id=environment_id)
    projects = ProjectService.list_all()
    environments = EnvironmentService.list_all(project_id=project_id) if project_id else []
    all_environments = EnvironmentService.list_all()

    return render_template(
        "variables/list.html",
        variables=variables,
        projects=projects,
        environments=environments,
        all_environments=all_environments,
        selected_project_id=project_id,
        selected_environment_id=environment_id,
    )


@variable_bp.route("/create", methods=["POST"])
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
def delete_variable(variable_id):
    try:
        VariableService.delete(variable_id)
        return handle_success("变量删除成功。", "variable.list_variables")
    except ServiceError as exc:
        return handle_page_error(str(exc), "variable.list_variables")
