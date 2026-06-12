from flask import Blueprint, render_template, request

from app.routes import catch_service_error_json, json_success
from app.services.ai_service import AIService
from app.services.module_service import ModuleService
from app.services.project_service import ProjectService
from app.services.prompt_service import PromptService
from app.security import accessible_project_ids, accessible_projects, require_permission

ai_bp = Blueprint("ai", __name__, url_prefix="/ai")


@ai_bp.route("/parser")
@require_permission("ai:use")
def parser_page():
    templates = PromptService.list_all()
    projects = accessible_projects()
    project_ids = accessible_project_ids()
    modules = [module for module in ModuleService.list_all() if module.project_id in project_ids] if project_ids else []
    return render_template(
        "ai/parser.html",
        templates=templates,
        projects=projects,
        modules=modules,
    )


@ai_bp.route("/api/parse", methods=["POST"])
@require_permission("ai:use")
@catch_service_error_json
def parse_document():
    payload = request.get_json(silent=True) or {}
    document_text = payload.get("document_text", "")
    template_id = payload.get("template_id")
    result = AIService.parse_document(document_text, template_id=template_id)
    return json_success("AI 解析成功。", result)


@ai_bp.route("/api/validate", methods=["POST"])
@require_permission("ai:use")
@catch_service_error_json
def validate_ai_result():
    payload = request.get_json(silent=True) or {}
    case_data = payload.get("case_data")
    validated = AIService.validate_ai_output(case_data)
    return json_success("AI 结果校验通过。", validated)


@ai_bp.route("/api/save-testcase", methods=["POST"])
@require_permission("ai:use")
@catch_service_error_json
def save_ai_testcase():
    payload = request.get_json(silent=True) or {}
    project_id = payload.get("project_id")
    module_id = payload.get("module_id")
    case_data = payload.get("case_data")
    description = payload.get("description", "AI 解析生成")

    testcase = AIService.save_as_testcase(
        project_id=project_id,
        module_id=module_id,
        case_data=case_data,
        description=description,
    )
    return json_success(
        "AI 生成用例已保存。",
        {
            "testcase_id": testcase.id,
            "name": testcase.name,
        },
    )
