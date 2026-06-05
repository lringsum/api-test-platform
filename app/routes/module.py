from flask import Blueprint, render_template, request

from app.routes import handle_page_error, handle_success
from app.services.base_service import ServiceError
from app.services.module_service import ModuleService
from app.services.project_service import ProjectService
from app.project_context import resolve_project_id

module_bp = Blueprint("module", __name__, url_prefix="/modules")


@module_bp.route("/")
def list_modules():
    project_id = resolve_project_id()
    modules = ModuleService.list_all(project_id=project_id)
    projects = ProjectService.list_all()
    return render_template(
        "modules/list.html",
        modules=modules,
        projects=projects,
        selected_project_id=project_id,
    )


@module_bp.route("/create", methods=["POST"])
def create_module():
    try:
        ModuleService.create(
            project_id=request.form.get("project_id", type=int),
            name=request.form.get("name"),
            description=request.form.get("description", ""),
        )
        return handle_success("模块创建成功。", "module.list_modules")
    except ServiceError as exc:
        return handle_page_error(str(exc), "module.list_modules")


@module_bp.route("/<int:module_id>/edit", methods=["POST"])
def edit_module(module_id):
    try:
        ModuleService.update(
            module_id=module_id,
            name=request.form.get("name"),
            description=request.form.get("description", ""),
        )
        return handle_success("模块更新成功。", "module.list_modules")
    except ServiceError as exc:
        return handle_page_error(str(exc), "module.list_modules")


@module_bp.route("/<int:module_id>/delete", methods=["POST"])
def delete_module(module_id):
    try:
        ModuleService.delete(module_id)
        return handle_success("模块删除成功。", "module.list_modules")
    except ServiceError as exc:
        return handle_page_error(str(exc), "module.list_modules")
