from datetime import datetime, timedelta

from flask import Blueprint, redirect, render_template, request, url_for

from app import db
from app.models import Execution, ExecutionDetail
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
from app.security import get_current_user, require_permission

execution_bp = Blueprint("execution", __name__, url_prefix="/executions")

DETAIL_SECTION_MAP = {
    "request": "request_snapshot",
    "response": "response_snapshot",
    "assertion": "assertion_results",
    "extract": "extract_results",
}


def _manual_trigger_context():
    user = get_current_user()
    return {
        "trigger_type": "manual",
        "trigger_user_id": user.id if user else None,
    }


def build_run_options(project_id):
    if not project_id:
        return {"environments": [], "modules": [], "testcases": []}

    environments = EnvironmentService.list_all(project_id=project_id)
    modules = ModuleService.list_all(project_id=project_id)
    testcases = TestCaseService.list_all_records(project_id=project_id)

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
    testcases = TestCaseService.list_all_records(project_id=project_id) if project_id else []
    modules = ModuleService.list_all(project_id=project_id) if project_id else []
    selected_testcase_id = request.args.get("testcase_id", type=int)
    initial_execution_context = None

    if selected_testcase_id:
        try:
            testcase = TestCaseService.get_by_id(selected_testcase_id)
        except ServiceError:
            testcase = None

        if testcase and (not project_id or testcase.project_id == project_id):
            testcase_data = testcase.data or {}
            initial_execution_context = {
                "project_id": testcase.project_id,
                "project_name": testcase.project.name if testcase.project else "",
                "testcase_id": testcase.id,
                "testcase_name": testcase.name,
                "module_id": testcase.module_id,
                "module_name": testcase.module.name if testcase.module else "",
                "method": str(testcase_data.get("method") or "").upper(),
                "url": str(testcase_data.get("url") or "").strip(),
                "feature_name": TestCaseService._resolve_feature_name(
                    str(testcase_data.get("url") or "").strip()
                ),
            }

    return render_template(
        "execution/run.html",
        projects=projects,
        environments=environments,
        testcases=testcases,
        modules=modules,
        selected_project_id=project_id,
        initial_execution_context=initial_execution_context,
    )


@execution_bp.route("/history")
def history_page():
    project_id = resolve_project_id()
    page = request.args.get("page", 1, type=int)
    selected_status = request.args.get("status", "").strip()
    selected_execution_type = request.args.get("execution_type", "").strip()

    query = Execution.query
    if project_id:
        query = query.filter_by(project_id=project_id)
    if selected_status:
        query = query.filter_by(status=selected_status)
    if selected_execution_type:
        query = query.filter_by(execution_type=selected_execution_type)

    all_executions = query.order_by(Execution.created_at.desc()).all()
    pagination = query.order_by(Execution.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    execution_total = len(all_executions)
    passed_total = sum(1 for item in all_executions if item.status == "passed")
    failed_total = sum(1 for item in all_executions if item.status == "failed")
    avg_duration = (
        round(sum(item.total_duration_ms for item in all_executions) / execution_total, 2)
        if execution_total
        else 0
    )
    recent_cutoff = datetime.utcnow() - timedelta(days=7)
    recent_total = sum(
        1
        for item in all_executions
        if item.created_at and item.created_at >= recent_cutoff
    )
    projects = ProjectService.list_all()
    return render_template(
        "execution/history.html",
        pagination=pagination,
        projects=projects,
        selected_project_id=project_id,
        selected_status=selected_status,
        selected_execution_type=selected_execution_type,
        execution_total=execution_total,
        passed_total=passed_total,
        failed_total=failed_total,
        avg_duration=avg_duration,
        recent_total=recent_total,
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
        **_manual_trigger_context(),
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
        **_manual_trigger_context(),
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
        **_manual_trigger_context(),
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
        **_manual_trigger_context(),
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
