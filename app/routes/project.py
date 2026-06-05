from flask import Blueprint, render_template, request

from app.routes import handle_page_error, handle_success
from app.services.base_service import ServiceError
from app.services.project_service import ProjectService

project_bp = Blueprint("project", __name__, url_prefix="/projects")


@project_bp.route("/")
def list_projects():
    keyword = (request.args.get("keyword") or "").strip()
    status = (request.args.get("status") or "").strip()

    projects = ProjectService.list_all()
    if keyword:
        projects = [p for p in projects if keyword.lower() in p.name.lower()]
    if status:
        projects = [p for p in projects if p.status == status]

    return render_template(
        "projects/list.html",
        projects=projects,
        keyword=keyword,
        selected_status=status,
    )


@project_bp.route("/create", methods=["POST"])
def create_project():
    try:
        ProjectService.create(
            name=request.form.get("name"),
            description=request.form.get("description", ""),
        )
        return handle_success("项目创建成功。", "project.list_projects")
    except ServiceError as exc:
        return handle_page_error(str(exc), "project.list_projects")


@project_bp.route("/<int:project_id>/edit", methods=["POST"])
def edit_project(project_id):
    try:
        ProjectService.update(
            project_id=project_id,
            name=request.form.get("name"),
            description=request.form.get("description", ""),
            status=request.form.get("status", "active"),
        )
        return handle_success("项目更新成功。", "project.list_projects")
    except ServiceError as exc:
        return handle_page_error(str(exc), "project.list_projects")


@project_bp.route("/<int:project_id>/delete", methods=["POST"])
def delete_project(project_id):
    try:
        ProjectService.delete(project_id)
        return handle_success("项目删除成功。", "project.list_projects")
    except ServiceError as exc:
        return handle_page_error(str(exc), "project.list_projects")
