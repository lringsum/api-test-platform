import json
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request
from sqlalchemy.orm import joinedload

from app import db
from app.models import ExecutionDetail, TestCase
from app.project_context import resolve_project_id
from app.routes import catch_service_error_json, handle_page_error, handle_success, json_success
from app.services.base_service import ServiceError
from app.services.module_service import ModuleService
from app.services.project_service import ProjectService
from app.services.testcase_service import TestCaseService

testcase_bp = Blueprint("testcase", __name__, url_prefix="/testcases")


@testcase_bp.route("/")
def list_testcases():
    projects = ProjectService.list_all()
    project_id = resolve_project_id()
    if project_id is None and projects:
        project_id = projects[0].id
    module_id = request.args.get("module_id", type=int)
    interface_name = request.args.get("interface_name", "").strip()
    interface_url = request.args.get("interface_url", "").strip()
    page = request.args.get("page", 1, type=int)

    pagination = TestCaseService.list_grouped(
        project_id=project_id,
        module_id=module_id,
        interface_name=interface_name,
        interface_url=interface_url,
        page=page,
        per_page=10,
    )
    modules = ModuleService.list_all(project_id=project_id) if project_id else []
    testcase_total = sum(len(module.testcases) for module in modules)
    active_module_total = sum(1 for module in modules if module.testcases)
    pending_module_total = max(len(modules) - active_module_total, 0)
    recent_module_total = sum(
        1
        for module in modules
        if module.updated_at and module.updated_at >= datetime.utcnow() - timedelta(days=7)
    )

    return render_template(
        "testcases/list.html",
        pagination=pagination,
        projects=projects,
        modules=modules,
        testcase_total=testcase_total,
        module_total=len(modules),
        active_module_total=active_module_total,
        pending_module_total=pending_module_total,
        recent_module_total=recent_module_total,
        selected_project_id=project_id,
        selected_module_id=module_id,
        selected_interface_name=interface_name,
        selected_interface_url=interface_url,
        recent_cutoff=datetime.utcnow() - timedelta(days=7),
    )


@testcase_bp.route("/create")
def create_testcase_page():
    projects = ProjectService.list_all()
    selected_project_id = resolve_project_id()
    if selected_project_id is None and projects:
        selected_project_id = projects[0].id
    modules = ModuleService.list_all(project_id=selected_project_id) if selected_project_id else []
    default_case = {
        "name": "登录成功",
        "method": "POST",
        "url": "/api/login",
        "headers": {},
        "params": {},
        "body": {},
        "extract": {"token": "data.token"},
        "assertions": [
            {"type": "status_code", "expected": 200},
            {"type": "json_path", "path": "code", "expected": 0},
        ],
        "pre_script": {
            "enabled": False,
            "language": "python",
            "template_id": None,
            "content": "",
        },
    }
    return render_template(
        "testcases/edit.html",
        testcase=None,
        projects=projects,
        modules=modules,
        selected_project_id=selected_project_id,
        selected_module_id=modules[0].id if modules else None,
        case_json=json.dumps(default_case, ensure_ascii=False, indent=2),
    )


@testcase_bp.route("/create", methods=["POST"])
def create_testcase():
    try:
        TestCaseService.create(
            project_id=request.form.get("project_id", type=int),
            module_id=request.form.get("module_id", type=int),
            name=request.form.get("name"),
            description=request.form.get("description", ""),
            case_data=request.form.get("case_data"),
            source=request.form.get("source", "manual"),
            is_active=request.form.get("is_active") == "1",
        )
        return handle_success("用例创建成功。", "testcase.list_testcases")
    except ServiceError as exc:
        return handle_page_error(str(exc), "testcase.create_testcase_page")


@testcase_bp.route("/<int:testcase_id>")
def detail_testcase_page(testcase_id):
    try:
        testcase = TestCaseService.get_by_id(testcase_id)
    except ServiceError as exc:
        return handle_page_error(str(exc), "testcase.list_testcases")

    case_data = testcase.data or {}
    recent_executions = (
        ExecutionDetail.query.options(joinedload(ExecutionDetail.execution))
        .filter_by(testcase_id=testcase.id)
        .order_by(ExecutionDetail.created_at.desc(), ExecutionDetail.id.desc())
        .limit(5)
        .all()
    )
    execution_count = ExecutionDetail.query.filter_by(testcase_id=testcase.id).count()
    success_count = sum(1 for detail in recent_executions if detail.status == "passed")
    failed_count = sum(1 for detail in recent_executions if detail.status == "failed")
    section_labels = [
        ("headers", "请求头"),
        ("params", "查询参数"),
        ("body", "请求体"),
        ("extract", "提取规则"),
        ("assertions", "断言配置"),
        ("pre_script", "前置脚本"),
    ]
    structure_sections = []
    for key, label in section_labels:
        value = case_data.get(key)
        configured = bool(value)
        if isinstance(value, dict):
            preview = json.dumps(value, ensure_ascii=False, indent=2)
            summary = f"{len(value)} 个字段"
        elif isinstance(value, list):
            preview = json.dumps(value, ensure_ascii=False, indent=2)
            summary = f"{len(value)} 条配置"
        elif value:
            preview = json.dumps(value, ensure_ascii=False, indent=2) if not isinstance(value, str) else value
            summary = "已配置"
        else:
            preview = "{}" if key != "assertions" else "[]"
            summary = "未配置"
        structure_sections.append(
            {
                "key": key,
                "label": label,
                "summary": summary,
                "preview": preview,
                "configured": configured,
            }
        )

    return render_template(
        "testcases/detail.html",
        testcase=testcase,
        case_data=case_data,
        case_json=json.dumps(case_data, ensure_ascii=False, indent=2),
        recent_executions=recent_executions,
        execution_count=execution_count,
        success_count=success_count,
        failed_count=failed_count,
        section_count=sum(1 for section in structure_sections if section["configured"]),
        structure_sections=structure_sections,
    )


@testcase_bp.route("/<int:testcase_id>/edit")
def edit_testcase_page(testcase_id):
    testcase = TestCaseService.get_by_id(testcase_id)
    projects = ProjectService.list_all()
    modules = ModuleService.list_all(project_id=testcase.project_id)

    return render_template(
        "testcases/edit.html",
        testcase=testcase,
        projects=projects,
        modules=modules,
        selected_project_id=testcase.project_id,
        selected_module_id=testcase.module_id,
        case_json=testcase.case_data,
    )


@testcase_bp.route("/<int:testcase_id>/edit", methods=["POST"])
def edit_testcase(testcase_id):
    try:
        TestCaseService.update(
            testcase_id=testcase_id,
            module_id=request.form.get("module_id", type=int),
            name=request.form.get("name"),
            description=request.form.get("description", ""),
            case_data=request.form.get("case_data"),
            source=request.form.get("source", "manual"),
            is_active=request.form.get("is_active") == "1",
        )
        return handle_success("用例更新成功。", "testcase.list_testcases")
    except ServiceError as exc:
        return handle_page_error(str(exc), "testcase.edit_testcase_page")


@testcase_bp.route("/<int:testcase_id>/delete", methods=["POST"])
def delete_testcase(testcase_id):
    try:
        TestCaseService.delete(testcase_id)
        return handle_success("用例删除成功。", "testcase.list_testcases")
    except ServiceError as exc:
        return handle_page_error(str(exc), "testcase.list_testcases")


@testcase_bp.route("/api/validate-json", methods=["POST"])
@catch_service_error_json
def validate_case_json():
    payload = request.get_json(silent=True) or {}
    case_data = payload.get("case_data")
    validated = TestCaseService.validate_case_json(case_data)
    return json_success("用例 JSON 校验通过。", validated)


@testcase_bp.route("/api/maintenance/batch-rename", methods=["POST"])
@catch_service_error_json
def batch_rename_testcases():
    payload = request.get_json(silent=True) or {}
    items = payload.get("items") or []
    if not isinstance(items, list) or not items:
        raise ServiceError("请提供要重命名的用例列表。")

    changed = []
    for item in items:
        testcase_id = item.get("id")
        new_name = str(item.get("name") or "").strip()
        if not testcase_id or not new_name:
            continue

        testcase = db.session.get(TestCase, testcase_id)
        if not testcase:
            continue

        old_name = testcase.name
        if old_name == new_name:
            continue

        # 同模块下名称唯一，若冲突则自动补 ID
        exists = TestCase.query.filter(
            TestCase.module_id == testcase.module_id,
            TestCase.name == new_name,
            TestCase.id != testcase.id,
        ).first()
        if exists:
            new_name = f"{new_name}#{testcase.id}"

        testcase.name = new_name
        # 同步历史执行明细中的名称，避免详情页仍显示旧名
        for detail in testcase.execution_details:
            detail.testcase_name = new_name

        changed.append(
            {"id": testcase.id, "old_name": old_name, "new_name": new_name}
        )

    if changed:
        db.session.commit()

    return json_success("批量重命名完成。", {"changed_count": len(changed), "changed": changed})
