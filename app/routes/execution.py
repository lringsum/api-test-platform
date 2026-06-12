from flask import Blueprint, redirect, render_template, request, url_for

from app import db
from app.models import ExecutionDetail
from app.project_context import resolve_project_id
from app.routes import catch_service_error_json, json_success
from app.services.base_service import ServiceError
from app.services.environment_service import EnvironmentService
from app.services.execution_service import ExecutionService
from app.services.module_service import ModuleService
from app.services.project_service import ProjectService
from app.services.report_service import ReportService
from app.services.testcase_service import TestCaseService
from app.utils.helpers import build_text_preview
from app.security import require_permission

execution_bp = Blueprint("execution", __name__, url_prefix="/executions")

DETAIL_SECTION_MAP = {
    "request": "request_snapshot",
    "response": "response_snapshot",
    "assertion": "assertion_results",
    "extract": "extract_results",
}


def build_run_options(project_id):
    if not project_id:
        return {"environments": [], "modules": [], "testcases": []}

    environments = EnvironmentService.list_all(project_id=project_id)
    modules = ModuleService.list_all(project_id=project_id)
    testcases = TestCaseService.list_all(project_id=project_id)

    return {
        "environments": [
            {"id": env.id, "name": env.name, "base_url": env.base_url}
            for env in environments
        ],
        "modules": [
            {"id": module.id, "name": module.name}
            for module in modules
        ],
        "testcases": [
            {
                "id": testcase.id,
                "name": testcase.name,
                "method": (testcase.data or {}).get("method", ""),
                "url": (testcase.data or {}).get("url", ""),
                "module_id": testcase.module_id,
            }
            for testcase in testcases
        ],
    }


@execution_bp.route("/run")
def run_page():
    projects = ProjectService.list_all()
    project_id = resolve_project_id()
    environments = EnvironmentService.list_all(project_id=project_id) if project_id else []
    testcases = TestCaseService.list_all(project_id=project_id) if project_id else []
    modules = ModuleService.list_all(project_id=project_id) if project_id else []

    return render_template(
        "execution/run.html",
        projects=projects,
        environments=environments,
        testcases=testcases,
        modules=modules,
        selected_project_id=project_id,
    )


@execution_bp.route("/history")
def history_page():
    project_id = resolve_project_id()
    page = request.args.get("page", 1, type=int)

    pagination = ExecutionService.list_all(project_id=project_id, page=page, per_page=20)
    projects = ProjectService.list_all()
    return render_template(
        "execution/history.html",
        pagination=pagination,
        projects=projects,
        selected_project_id=project_id,
    )


@execution_bp.route("/<int:execution_id>")
def detail_page(execution_id):
    execution = ExecutionService.get_by_id(execution_id)
    return render_template("execution/detail.html", execution=execution)


@execution_bp.route("/<int:execution_id>/report")
@require_permission("report:view")
def execution_report_page(execution_id):
    execution = ExecutionService.get_by_id(execution_id)
    report = ReportService.generate(execution.id)
    return redirect(url_for("report.detail_report", report_id=report.id))


@execution_bp.route("/api/details/<int:detail_id>")
@catch_service_error_json
def detail_snapshot(detail_id):
    detail = db.session.get(ExecutionDetail, detail_id)
    if not detail:
        raise ServiceError("执行明细不存在。")

    section = (request.args.get("section") or "").strip()
    full = request.args.get("full", "").lower() in {"1", "true", "yes"}
    preview_length = 4000

    if section and section not in DETAIL_SECTION_MAP:
        raise ServiceError("不支持的明细分区。")

    sections = {}
    target_sections = [section] if section else list(DETAIL_SECTION_MAP.keys())
    for key in target_sections:
        raw_value = getattr(detail, DETAIL_SECTION_MAP[key], "")
        section_payload = build_text_preview(
            raw_value,
            max_length=len(str(raw_value or "")) if full else preview_length,
        )
        section_payload["full"] = full
        sections[key] = section_payload

    return json_success(
        "执行明细加载成功。",
        {
            "detail_id": detail.id,
            "status": detail.status,
            "error_message": detail.error_message or "",
            "sections": sections,
        },
    )


@execution_bp.route("/api/run/options")
@catch_service_error_json
def run_options():
    project_id = resolve_project_id()
    return json_success("执行选项加载成功。", build_run_options(project_id))


@execution_bp.route("/api/run/testcase/<int:testcase_id>", methods=["POST"])
@catch_service_error_json
def run_testcase(testcase_id):
    payload = request.get_json(silent=True) or {}
    environment_id = payload.get("environment_id")
    execution = ExecutionService.run_testcase(
        testcase_id=testcase_id,
        environment_id=environment_id,
    )

    return json_success(
        "用例执行完成。",
        {
            "execution_id": execution.id,
            "status": execution.status,
            "total_count": execution.total_count,
            "passed_count": execution.passed_count,
            "failed_count": execution.failed_count,
            "pass_rate": execution.pass_rate,
            "detail_url": f"/executions/{execution.id}",
        },
    )


@execution_bp.route("/api/run/module/<int:module_id>", methods=["POST"])
@catch_service_error_json
def run_module(module_id):
    payload = request.get_json(silent=True) or {}
    environment_id = payload.get("environment_id")
    execution = ExecutionService.run_module(
        module_id=module_id,
        environment_id=environment_id,
    )
    return json_success(
        "模块执行完成。",
        {
            "execution_id": execution.id,
            "status": execution.status,
            "total_count": execution.total_count,
            "passed_count": execution.passed_count,
            "failed_count": execution.failed_count,
            "pass_rate": execution.pass_rate,
            "detail_url": f"/executions/{execution.id}",
        },
    )


@execution_bp.route("/api/run/selection", methods=["POST"])
@catch_service_error_json
def run_selection():
    payload = request.get_json(silent=True) or {}
    environment_id = payload.get("environment_id")
    testcase_ids = payload.get("testcase_ids") or []
    execution = ExecutionService.run_selected_testcases(
        testcase_ids=testcase_ids,
        environment_id=environment_id,
    )
    return json_success(
        "选中用例批量执行完成。",
        {
            "execution_id": execution.id,
            "status": execution.status,
            "total_count": execution.total_count,
            "passed_count": execution.passed_count,
            "failed_count": execution.failed_count,
            "pass_rate": execution.pass_rate,
            "detail_url": f"/executions/{execution.id}",
        },
    )


@execution_bp.route("/api/run/project/<int:project_id>", methods=["POST"])
@catch_service_error_json
def run_project(project_id):
    payload = request.get_json(silent=True) or {}
    environment_id = payload.get("environment_id")
    execution = ExecutionService.run_project(
        project_id=project_id,
        environment_id=environment_id,
    )
    return json_success(
        "项目执行完成。",
        {
            "execution_id": execution.id,
            "status": execution.status,
            "total_count": execution.total_count,
            "passed_count": execution.passed_count,
            "failed_count": execution.failed_count,
            "pass_rate": execution.pass_rate,
            "detail_url": f"/executions/{execution.id}",
        },
    )
