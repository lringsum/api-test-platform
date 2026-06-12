from flask import Blueprint, render_template, request

from app.routes import handle_page_error, handle_success
from app.security import require_permission
from app.services.base_service import ServiceError
from app.services.prompt_service import PromptService

prompt_bp = Blueprint("prompt", __name__, url_prefix="/prompts")


@prompt_bp.route("/")
@require_permission("prompt:view")
def list_prompts():
    keyword = (request.args.get("keyword") or "").strip()
    status = (request.args.get("status") or "").strip()

    templates = PromptService.list_all()
    if keyword:
        templates = [t for t in templates if keyword.lower() in t.name.lower()]
    if status:
        is_active = status == "active"
        templates = [t for t in templates if t.is_active == is_active]

    return render_template(
        "prompts/list.html",
        templates=templates,
        keyword=keyword,
        selected_status=status,
    )


@prompt_bp.route("/create", methods=["POST"])
@require_permission("prompt:create")
def create_prompt():
    try:
        PromptService.create(
            name=request.form.get("name"),
            content=request.form.get("content"),
            description=request.form.get("description", ""),
            is_active=request.form.get("is_active") == "1",
        )
        return handle_success("Prompt 模板创建成功。", "prompt.list_prompts")
    except ServiceError as exc:
        return handle_page_error(str(exc), "prompt.list_prompts")


@prompt_bp.route("/<int:template_id>/edit", methods=["POST"])
@require_permission("prompt:edit")
def edit_prompt(template_id):
    try:
        PromptService.update(
            template_id=template_id,
            name=request.form.get("name"),
            content=request.form.get("content"),
            description=request.form.get("description", ""),
            is_active=request.form.get("is_active") == "1",
        )
        return handle_success("Prompt 模板更新成功。", "prompt.list_prompts")
    except ServiceError as exc:
        return handle_page_error(str(exc), "prompt.list_prompts")


@prompt_bp.route("/<int:template_id>/delete", methods=["POST"])
@require_permission("prompt:delete")
def delete_prompt(template_id):
    try:
        PromptService.delete(template_id)
        return handle_success("Prompt 模板删除成功。", "prompt.list_prompts")
    except ServiceError as exc:
        return handle_page_error(str(exc), "prompt.list_prompts")
