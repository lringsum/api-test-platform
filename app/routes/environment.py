from flask import Blueprint, render_template, request

from app.routes import handle_page_error, handle_success
from app.services.base_service import ServiceError
from app.services.environment_service import EnvironmentService
from app.services.project_service import ProjectService
from app.project_context import resolve_project_id

environment_bp = Blueprint("environment", __name__, url_prefix="/environments")


@environment_bp.route("/")
def list_environments():
    project_id = resolve_project_id()
    environments = EnvironmentService.list_all(project_id=project_id)
    projects = ProjectService.list_all()
    return render_template(
        "environments/list.html",
        environments=environments,
        projects=projects,
        selected_project_id=project_id,
    )


@environment_bp.route("/create", methods=["POST"])
def create_environment():
    try:
        EnvironmentService.create(
            project_id=request.form.get("project_id", type=int),
            name=request.form.get("name"),
            base_url=request.form.get("base_url"),
            headers_json=request.form.get("headers_json", "{}"),
            variables_json=request.form.get("variables_json", "{}"),
            description=request.form.get("description", ""),
        )
        return handle_success("环境创建成功。", "environment.list_environments")
    except ServiceError as exc:
        return handle_page_error(str(exc), "environment.list_environments")


@environment_bp.route("/<int:environment_id>/edit", methods=["POST"])
def edit_environment(environment_id):
    try:
        EnvironmentService.update(
            environment_id=environment_id,
            name=request.form.get("name"),
            base_url=request.form.get("base_url"),
            headers_json=request.form.get("headers_json", "{}"),
            variables_json=request.form.get("variables_json", "{}"),
            description=request.form.get("description", ""),
            is_active=request.form.get("is_active") == "1",
        )
        return handle_success("环境更新成功。", "environment.list_environments")
    except ServiceError as exc:
        return handle_page_error(str(exc), "environment.list_environments")


@environment_bp.route("/<int:environment_id>/delete", methods=["POST"])
def delete_environment(environment_id):
    try:
        EnvironmentService.delete(environment_id)
        return handle_success("环境删除成功。", "environment.list_environments")
    except ServiceError as exc:
        return handle_page_error(str(exc), "environment.list_environments")
