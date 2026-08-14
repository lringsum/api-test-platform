import difflib
import json
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

from app import db
from app.models import AndroidUiProjectFlow, AndroidUiProjectFlowStep, AndroidUiRunStepArtifact, AndroidUiTestRun, AndroidUiTestTask, AuditLog, Environment, Execution, ExecutionDetail, Module, Permission, Project, ProjectMember, Role, Scenario, ScenarioExecution, ScenarioStep, TestCase, UiAutomationArtifact, UiAutomationEnvironment, UiAutomationLocator, UiAutomationRun, UiAutomationRunStep, UiAutomationScript, UiAutomationScriptVersion, User, Variable
from app.project_context import ALL_PROJECTS_VALUE, get_active_project_id, set_active_project
from app.security import accessible_project_ids, accessible_projects, get_current_user, get_user_permissions, has_permission, login_user, logout_user
from app.services.base_service import ServiceError
from app.services.android_ui_automation_service import AndroidUiAutomationService
from app.services.android_ui_automation_worker import AndroidUiAutomationWorker
from app.services.environment_service import EnvironmentService
from app.services.execution_service import ExecutionService
from app.services.module_service import ModuleService
from app.services.project_service import ProjectService
from app.services.report_service import ReportService
from app.services.scenario_execution_service import ScenarioExecutionService
from app.services.scenario_service import ScenarioService
from app.services.security_service import PROJECT_ACCESS_LEVELS, SecurityService
from app.services.testcase_service import TestCaseService
from app.services.ui_automation_service import UiAutomationService
from app.services.ui_automation_worker import UiAutomationWorker
from app.services.variable_service import VariableService


api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")


def _ok(data=None, message=""):
    return jsonify({"success": True, "message": message, "data": data if data is not None else {}})


def _error(message, status=400):
    return jsonify({"success": False, "message": message, "data": {}}), status


def _require_permission(permission_code):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not get_current_user():
                return _error("Authentication required.", 401)
            if not has_permission(permission_code):
                return _error("Permission denied.", 403)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def _iso(value):
    return value.isoformat() if value else None


def _scoped_project_id():
    raw_value = request.args.get("project_id")
    if raw_value in (None, "", ALL_PROJECTS_VALUE):
        return get_active_project_id()
    try:
        candidate = int(raw_value)
    except (TypeError, ValueError):
        return get_active_project_id()
    return candidate if candidate in accessible_project_ids() else None


def _project_payload(project):
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "modules": len(project.modules),
        "environments": len(project.environments),
        "updatedAt": _iso(project.updated_at),
    }


def _execution_payload(execution):
    summary = execution.summary
    type_label = "UI 自动化" if "ui" in (execution.execution_type or "").lower() else "接口测试"
    name = summary.get("name") or f"{execution.target_type or execution.execution_type} #{execution.id}"
    return {
        "id": execution.id,
        "name": name,
        "project": execution.project.name if execution.project else "-",
        "executionType": type_label,
        "status": execution.status,
        "duration": round((execution.total_duration_ms or 0) / 1000),
        "startedAt": _iso(execution.started_at or execution.created_at),
        "passRate": round(execution.pass_rate or 0, 2),
        "total": execution.total_count,
        "passed": execution.passed_count,
        "failed": execution.failed_count,
        "reportId": execution.report.id if execution.report else None,
    }


def _execution_detail_payload(execution):
    return {
        **_execution_payload(execution),
        "environment": execution.environment.name if execution.environment else None,
        "summary": execution.summary,
        "details": [{
            "id": item.id,
            "testcaseId": item.testcase_id,
            "testcaseName": item.testcase_name,
            "status": item.status,
            "durationMs": item.duration_ms,
            "request": item.request_data,
            "response": item.response_data,
            "assertions": item.assertion_data,
            "extracts": item.extract_data,
            "errorMessage": item.error_message,
        } for item in execution.details],
    }


def _execution_run_options(project_id):
    if not project_id:
        return {"environments": [], "modules": [], "testcases": []}
    return {
        "environments": [{"id": item.id, "name": item.name, "baseUrl": item.base_url} for item in EnvironmentService.list_all(project_id=project_id) if item.is_active],
        "modules": [{"id": item.id, "name": item.name} for item in ModuleService.list_all(project_id=project_id)],
        "testcases": [{"id": item.id, "name": item.name, "moduleId": item.module_id, "module": item.module.name, "method": str((item.data or {}).get("method") or "GET").upper(), "endpoint": (item.data or {}).get("url") or ""} for item in TestCase.query.filter(TestCase.project_id == project_id, TestCase.is_active.is_(True)).order_by(TestCase.name.asc()).all()],
    }


def _module_payload(module):
    return {
        "id": module.id,
        "projectId": module.project_id,
        "project": module.project.name,
        "name": module.name,
        "description": module.description,
        "testcaseCount": len(module.testcases),
        "scenarioCount": len(module.scenarios),
        "updatedAt": _iso(module.updated_at),
    }


def _testcase_payload(testcase):
    case_data = testcase.data or {}
    return {
        "id": testcase.id,
        "projectId": testcase.project_id,
        "project": testcase.project.name,
        "moduleId": testcase.module_id,
        "module": testcase.module.name,
        "name": testcase.name,
        "description": testcase.description,
        "method": str(case_data.get("method") or "GET").upper(),
        "endpoint": case_data.get("url") or "",
        "source": "manual",
        "enabled": testcase.is_active,
        "caseData": case_data,
        "request": json.dumps(case_data, ensure_ascii=False, indent=2),
        "updatedAt": _iso(testcase.updated_at),
    }


def _case_data_text(value):
    if isinstance(value, str):
        return value
    return json.dumps(value or {}, ensure_ascii=False)


def _environment_payload(environment):
    return {
        "id": environment.id,
        "projectId": environment.project_id,
        "project": environment.project.name,
        "name": environment.name,
        "baseUrl": environment.base_url,
        "description": environment.description,
        "isActive": environment.is_active,
        "headers": environment.headers,
        "variables": environment.variables_data,
        "updatedAt": _iso(environment.updated_at),
    }


def _variable_payload(variable):
    return {
        "id": variable.id,
        "projectId": variable.project_id,
        "project": variable.project.name,
        "environmentId": variable.environment_id,
        "environment": variable.environment.name if variable.environment else None,
        "name": variable.name,
        "value": variable.value,
        "scope": variable.scope,
        "description": variable.description,
        "updatedAt": _iso(variable.updated_at),
    }


def _user_payload(user):
    return {"id": user.id, "username": user.username, "displayName": user.display_name, "email": user.email, "isActive": user.is_active, "isSuperuser": user.is_superuser, "roles": [{"code": item.code, "name": item.name} for item in user.roles], "lastLoginAt": _iso(user.last_login_at), "updatedAt": _iso(user.updated_at)}


def _permission_payload(permission):
    return {"id": permission.id, "code": permission.code, "name": permission.name, "category": permission.category, "groupName": permission.group_name, "description": permission.description, "sortOrder": permission.sort_order}


def _role_payload(role):
    return {"id": role.id, "code": role.code, "name": role.name, "description": role.description, "isSystem": role.is_system, "sortOrder": role.sort_order, "permissionCodes": [item.code for item in role.permissions], "updatedAt": _iso(role.updated_at)}


def _project_member_payload(member):
    return {"id": member.id, "projectId": member.project_id, "project": member.project.name, "userId": member.user_id, "username": member.user.username, "displayName": member.user.display_name, "accessLevel": member.access_level, "remark": member.remark, "updatedAt": _iso(member.updated_at)}


def _audit_payload(item):
    return {"id": item.id, "username": item.username, "action": item.action, "resourceType": item.resource_type, "resourceId": item.resource_id, "projectId": item.project_id, "ipAddress": item.ip_address, "detail": item.detail, "createdAt": _iso(item.created_at)}


def _ui_script_payload(item):
    version = next((v for v in item.versions if v.id == item.current_version_id), item.versions[0] if item.versions else None)
    project = db.session.get(Project, item.project_id)
    return {"id": item.id, "projectId": item.project_id, "project": project.name if project else "-", "name": item.name, "code": item.code, "description": item.description, "status": item.status, "tags": item.tags, "version": version.version_no if version else 0, "content": version.script_content if version else "", "dependencies": version.dependencies if version else [], "updatedAt": _iso(item.updated_at)}


def _ui_locator_payload(item):
    project = db.session.get(Project, item.project_id)
    return {"id": item.id, "projectId": item.project_id, "project": project.name if project else "-", "pageName": item.page_name, "code": item.locator_code, "name": item.locator_name, "type": item.locator_type, "value": item.locator_value, "status": item.status, "stable": item.is_stable, "updatedAt": _iso(item.updated_at)}


def _ui_run_payload(item):
    project = db.session.get(Project, item.project_id); script = db.session.get(UiAutomationScript, item.script_id)
    return {"id": item.id, "projectId": item.project_id, "project": project.name if project else "-", "scriptId": item.script_id, "script": script.name if script else "", "environment": item.environment.name if item.environment else None, "status": item.status, "browser": item.browser_type, "startedAt": _iso(item.started_at or item.created_at), "durationMs": item.duration_ms, "error": item.error_message}


def _ui_environment_payload(item):
    project = db.session.get(Project, item.project_id)
    return {"id": item.id, "projectId": item.project_id, "project": project.name if project else "-", "name": item.name, "baseUrl": item.base_url, "browserDefault": item.browser_default, "headlessDefault": item.headless_default, "timeoutMs": item.timeout_ms, "retryTimes": item.retry_times, "viewportWidth": item.viewport_width, "viewportHeight": item.viewport_height, "storageStatePath": item.storage_state_path, "proxyConfig": item.proxy_config, "runtimeVariables": item.runtime_variables, "status": item.status, "description": item.description, "updatedAt": _iso(item.updated_at)}


def _ui_artifact_payload(run, item):
    return {"id": item.id, "type": item.artifact_type, "fileName": item.file_name, "fileSize": item.file_size, "mimeType": item.mime_type, "createdAt": _iso(item.created_at), "previewUrl": f"/api/v1/ui-automation/runs/{run.id}/artifacts/{item.id}/preview", "downloadUrl": f"/api/v1/ui-automation/runs/{run.id}/artifacts/{item.id}/download"}


def _ui_replay_step_payload(run, item, artifacts_by_file_name):
    screenshot_url = ""
    raw_log = item.raw_log if isinstance(item.raw_log, list) else []
    for entry in reversed(raw_log):
        if not isinstance(entry, dict):
            continue
        screenshot_file = str(entry.get("screenshot_file") or "").strip()
        artifact = artifacts_by_file_name.get(Path(screenshot_file).name) if screenshot_file else None
        if artifact:
            screenshot_url = f"/api/v1/ui-automation/runs/{run.id}/artifacts/{artifact.id}/preview"
            break
    failure_analysis = (
        UiAutomationService.analyze_step_failure(item)
        if item.status == "failed"
        else None
    )
    return {"id": item.id, "index": item.step_index, "type": item.step_type, "title": item.step_title, "locator": item.locator, "status": item.status, "durationMs": item.duration_ms, "error": item.error_message, "rawLog": raw_log, "screenshotUrl": screenshot_url, "failureAnalysis": failure_analysis}


def _ui_version_payload(item):
    return {"id": item.id, "version": item.version_no, "summary": item.change_summary, "content": item.script_content, "dependencies": item.dependencies, "createdAt": _iso(item.created_at)}


def _android_flow_payload(item):
    project = db.session.get(Project, item.project_id)
    return {"id": item.id, "projectId": item.project_id, "project": project.name if project else "-", "name": item.name, "code": item.code, "description": item.description, "isDefault": item.is_default, "status": item.status, "steps": [{"id": step.id, "stepNo": step.step_no, "name": step.step_name, "type": step.step_type, "selectorType": step.selector_type, "selectorValue": step.selector_value, "inputValue": step.input_value, "waitTimeoutSec": step.wait_timeout_sec, "retryTimes": step.retry_times, "continueOnFailure": step.continue_on_failure, "captureOnSuccess": step.capture_on_success, "captureOnFailure": step.capture_on_failure, "remark": step.remark} for step in item.steps], "updatedAt": _iso(item.updated_at)}


def _android_task_payload(item):
    project = db.session.get(Project, item.project_id)
    return {"id": item.id, "projectId": item.project_id, "project": project.name if project else "-", "name": item.name, "packageKey": item.package_key, "packageName": item.package_name, "apkUrl": item.apk_url, "channelTag": item.channel_tag, "deviceSerial": item.device_serial, "flowMode": item.flow_mode, "flowId": item.flow_id, "isActive": item.is_active, "remark": item.remark, "updatedAt": _iso(item.updated_at)}


def _android_run_payload(item):
    project = db.session.get(Project, item.project_id); task = db.session.get(AndroidUiTestTask, item.task_id)
    return {"id": item.id, "projectId": item.project_id, "project": project.name if project else "-", "taskId": item.task_id, "task": task.name if task else "", "executionNo": item.execution_no, "status": item.status, "stage": item.stage, "deviceSerial": item.device_serial, "deviceName": item.device_name, "errorType": item.error_type, "error": item.error_message, "durationMs": item.duration_ms, "startedAt": _iso(item.started_at or item.created_at), "finishedAt": _iso(item.finished_at)}


def _android_run_detail_payload(item):
    payload = _android_run_payload(item)
    payload.update({
        "packageName": item.package_name,
        "launchableActivity": item.launchable_activity,
        "downloadStatus": item.download_status,
        "aaptStatus": item.aapt_status,
        "installStatus": item.install_status,
        "launchStatus": item.launch_status,
        "crashStatus": item.crash_status,
        "currentFocus": item.current_focus,
        "pid": item.pid,
        "flowSnapshot": item.flow_snapshot,
        "screenshotUrl": f"/api/v1/android-automation/runs/{item.id}/artifacts/screenshot" if item.screenshot_path else "",
        "logUrl": f"/api/v1/android-automation/runs/{item.id}/artifacts/log" if item.log_path else "",
        "steps": [{
            "id": step.id, "stepNo": step.step_no, "name": step.step_name, "type": step.step_type,
            "selectorType": step.selector_type, "selectorValue": step.selector_value, "status": step.status,
            "error": step.error_message, "durationMs": step.duration_ms, "startedAt": _iso(step.started_at),
            "finishedAt": _iso(step.finished_at), "screenshotUrl": f"/api/v1/android-automation/runs/{item.id}/artifacts/step/{step.id}/screenshot" if step.screenshot_path else "",
            "artifacts": [{"id": artifact.id, "type": artifact.artifact_type, "fileName": artifact.file_name, "fileSize": artifact.file_size, "previewUrl": f"/api/v1/android-automation/runs/{item.id}/artifacts/step/{step.id}/{artifact.id}"} for artifact in step.artifacts],
        } for step in item.run_steps],
    })
    return payload


def _scenario_step_payload(step):
    return {
        "id": step.id,
        "scenarioId": step.scenario_id,
        "testcaseId": step.testcase_id,
        "testcaseName": step.testcase.name if step.testcase else "",
        "orderNo": step.order_no,
        "name": step.name,
        "isEnabled": step.is_enabled,
        "continueOnFailure": step.continue_on_failure,
        "setupVariables": step.setup_variables,
        "requestOverrides": step.request_overrides,
        "extractOverrides": step.extract_overrides,
        "assertionOverrides": step.assertion_overrides,
    }


def _scenario_payload(scenario, include_steps=False):
    payload = {
        "id": scenario.id,
        "projectId": scenario.project_id,
        "project": scenario.project.name,
        "moduleId": scenario.module_id,
        "module": scenario.module.name if scenario.module else None,
        "name": scenario.name,
        "description": scenario.description,
        "status": scenario.status,
        "tags": scenario.tags,
        "stepCount": len(scenario.steps),
        "updatedAt": _iso(scenario.updated_at),
    }
    if include_steps:
        payload["steps"] = [_scenario_step_payload(step) for step in scenario.steps]
    return payload


def _scenario_execution_payload(execution, include_details=False):
    payload = {
        "id": execution.id,
        "scenarioId": execution.scenario_id,
        "scenario": execution.scenario.name if execution.scenario else "-",
        "projectId": execution.scenario.project_id if execution.scenario else None,
        "project": execution.scenario.project.name if execution.scenario and execution.scenario.project else "-",
        "environment": execution.environment.name if execution.environment else None,
        "status": execution.status,
        "totalSteps": execution.total_steps,
        "passedSteps": execution.passed_steps,
        "failedSteps": execution.failed_steps,
        "durationMs": execution.duration_ms,
        "startedAt": _iso(execution.started_at or execution.created_at),
        "runtimeVariables": execution.runtime_variables,
    }
    if include_details:
        payload["details"] = [{"id": item.id, "stepName": item.step_name, "testcaseName": item.testcase_name, "status": item.status, "durationMs": item.duration_ms, "request": item.request_data, "response": item.response_data, "extracts": item.extract_data, "assertions": item.assertion_data, "errorMessage": item.error_message} for item in execution.details]
    return payload


@api_v1_bp.route("/session")
def session_info():
    user = get_current_user()
    if not user:
        return _error("Authentication required.", 401)
    return _ok({
        "user": {
            "id": user.id,
            "username": user.username,
            "displayName": user.display_name or user.username,
            "isSuperuser": user.is_superuser,
        },
        "permissions": sorted(get_user_permissions(user)),
        "projects": [_project_payload(project) for project in accessible_projects(user)],
        "activeProjectId": get_active_project_id(),
    })


@api_v1_bp.route("/session/login", methods=["POST"])
def session_login():
    payload = request.get_json(silent=True) or {}
    try:
        user = SecurityService.authenticate(username=payload.get("username"), password=payload.get("password"))
        login_user(user)
        SecurityService.record_audit("login", resource_type="auth")
    except ServiceError as exc:
        return _error(str(exc), 401)
    return _ok({"user": {"id": user.id, "username": user.username, "displayName": user.display_name or user.username, "isSuperuser": user.is_superuser}, "permissions": sorted(get_user_permissions(user)), "projects": [_project_payload(project) for project in accessible_projects(user)], "activeProjectId": get_active_project_id()}, "Login succeeded.")


@api_v1_bp.route("/session/logout", methods=["POST"])
def session_logout():
    logout_user()
    return _ok(message="Signed out.")


@api_v1_bp.route("/context/project", methods=["PUT"])
def update_project_context():
    if not get_current_user():
        return _error("Authentication required.", 401)
    payload = request.get_json(silent=True) or {}
    project_id = payload.get("projectId")
    if project_id in (None, "", ALL_PROJECTS_VALUE):
        set_active_project(None)
        return _ok({"activeProjectId": None})
    try:
        project_id = int(project_id)
    except (TypeError, ValueError):
        return _error("Invalid project id.")
    if not db.session.get(Project, project_id):
        return _error("Project access denied.", 403)
    if set_active_project(project_id) is None:
        return _error("Project access denied.", 403)
    return _ok({"activeProjectId": project_id})


@api_v1_bp.route("/dashboard")
@_require_permission("dashboard:view")
def dashboard():
    project_id = _scoped_project_id()
    project_ids = [project_id] if project_id else accessible_project_ids()
    if not project_ids:
        return _ok({"stats": [], "executions": [], "trend": {"dates": [], "passed": [], "failed": []}})

    execution_query = Execution.query.filter(Execution.project_id.in_(project_ids))
    today = datetime.utcnow().date()
    days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    trend = {day: {"passed": 0, "failed": 0} for day in days}
    for execution in execution_query.filter(Execution.created_at >= datetime.combine(days[0], datetime.min.time())).all():
        day = execution.created_at.date()
        if day in trend and execution.status in trend[day]:
            trend[day][execution.status] += 1

    return _ok({
        "stats": [
            {"label": "项目", "value": Project.query.filter(Project.id.in_(project_ids)).count(), "hint": "当前可访问的项目总数", "tone": "blue"},
            {"label": "用例", "value": TestCase.query.filter(TestCase.project_id.in_(project_ids)).count(), "hint": "当前范围的用例总数", "tone": "green"},
            {"label": "场景", "value": Scenario.query.filter(Scenario.project_id.in_(project_ids)).count(), "hint": "当前范围的场景总数", "tone": "purple"},
            {"label": "最近执行", "value": execution_query.filter(Execution.created_at >= datetime.combine(today - timedelta(days=6), datetime.min.time())).count(), "hint": "近 7 天执行的总次数", "tone": "red"},
        ],
        "executions": [_execution_payload(item) for item in execution_query.order_by(Execution.created_at.desc()).limit(5).all()],
        "trend": {
            "dates": [day.strftime("%m-%d") for day in days],
            "passed": [trend[day]["passed"] for day in days],
            "failed": [trend[day]["failed"] for day in days],
        },
    })


@api_v1_bp.route("/projects", methods=["GET", "POST"])
@_require_permission("project:view")
def projects():
    if request.method == "POST":
        if not has_permission("project:create"):
            return _error("Permission denied.", 403)
        payload = request.get_json(silent=True) or {}
        try:
            project = ProjectService.create(payload.get("name"), payload.get("description", ""))
        except ServiceError as exc:
            return _error(str(exc))
        return _ok(_project_payload(project), "Project created.")
    return _ok([_project_payload(project) for project in accessible_projects()])


@api_v1_bp.route("/projects/<int:project_id>", methods=["PATCH", "DELETE"])
@_require_permission("project:view")
def project_detail(project_id):
    if project_id not in accessible_project_ids():
        return _error("Project access denied.", 403)
    if request.method == "DELETE":
        if not has_permission("project:delete"):
            return _error("Permission denied.", 403)
        try:
            ProjectService.delete(project_id)
        except ServiceError as exc:
            return _error(str(exc))
        return _ok(message="Project deleted.")

    if not has_permission("project:edit"):
        return _error("Permission denied.", 403)
    payload = request.get_json(silent=True) or {}
    try:
        project = ProjectService.update(
            project_id,
            payload.get("name"),
            payload.get("description", ""),
            payload.get("status", "active"),
        )
    except ServiceError as exc:
        return _error(str(exc))
    return _ok(_project_payload(project), "Project updated.")


@api_v1_bp.route("/modules", methods=["GET", "POST"])
@_require_permission("module:view")
def modules():
    if request.method == "POST":
        if not has_permission("module:create"):
            return _error("Permission denied.", 403)
        payload = request.get_json(silent=True) or {}
        project_id = payload.get("projectId") or get_active_project_id()
        try:
            project_id = int(project_id)
        except (TypeError, ValueError):
            return _error("A project is required.")
        if project_id not in accessible_project_ids():
            return _error("Project access denied.", 403)
        try:
            module = ModuleService.create(project_id, payload.get("name"), payload.get("description", ""))
        except ServiceError as exc:
            return _error(str(exc))
        return _ok(_module_payload(module), "Module created.")
    project_id = _scoped_project_id()
    query = Module.query
    if project_id:
        query = query.filter(Module.project_id == project_id)
    else:
        query = query.filter(Module.project_id.in_(accessible_project_ids()))
    return _ok([_module_payload(item) for item in query.order_by(Module.updated_at.desc()).all()])


@api_v1_bp.route("/modules/<int:module_id>", methods=["PATCH", "DELETE"])
@_require_permission("module:view")
def module_detail(module_id):
    module = db.session.get(Module, module_id)
    if not module or module.project_id not in accessible_project_ids():
        return _error("Module not found.", 404)
    if request.method == "DELETE":
        if not has_permission("module:delete"):
            return _error("Permission denied.", 403)
        ModuleService.delete(module_id)
        return _ok(message="Module deleted.")
    if not has_permission("module:edit"):
        return _error("Permission denied.", 403)
    payload = request.get_json(silent=True) or {}
    try:
        updated = ModuleService.update(module_id, payload.get("name"), payload.get("description", ""))
    except ServiceError as exc:
        return _error(str(exc))
    return _ok(_module_payload(updated), "Module updated.")


@api_v1_bp.route("/environments", methods=["GET", "POST"])
@_require_permission("environment:view")
def environments():
    if request.method == "POST":
        if not has_permission("environment:create"):
            return _error("Permission denied.", 403)
        payload = request.get_json(silent=True) or {}
        try:
            project_id = int(payload.get("projectId"))
        except (TypeError, ValueError):
            return _error("A project is required.")
        if project_id not in accessible_project_ids():
            return _error("Project access denied.", 403)
        try:
            environment = EnvironmentService.create(
                project_id=project_id,
                name=payload.get("name"),
                base_url=payload.get("baseUrl"),
                headers_json=_case_data_text(payload.get("headers")),
                variables_json=_case_data_text(payload.get("variables")),
                description=payload.get("description", ""),
            )
        except ServiceError as exc:
            return _error(str(exc))
        return _ok(_environment_payload(environment), "Environment created.")
    project_id = _scoped_project_id()
    query = Environment.query
    if project_id:
        query = query.filter(Environment.project_id == project_id)
    else:
        query = query.filter(Environment.project_id.in_(accessible_project_ids()))
    return _ok([_environment_payload(item) for item in query.order_by(Environment.updated_at.desc()).all()])


@api_v1_bp.route("/environments/<int:environment_id>", methods=["PATCH", "DELETE"])
@_require_permission("environment:view")
def environment_detail(environment_id):
    environment = db.session.get(Environment, environment_id)
    if not environment or environment.project_id not in accessible_project_ids():
        return _error("Environment not found.", 404)
    if request.method == "DELETE":
        if not has_permission("environment:delete"):
            return _error("Permission denied.", 403)
        try:
            EnvironmentService.delete(environment_id)
        except ServiceError as exc:
            return _error(str(exc))
        return _ok(message="Environment deleted.")
    if not has_permission("environment:edit"):
        return _error("Permission denied.", 403)
    payload = request.get_json(silent=True) or {}
    try:
        updated = EnvironmentService.update(
            environment_id=environment_id,
            name=payload.get("name"),
            base_url=payload.get("baseUrl"),
            headers_json=_case_data_text(payload.get("headers")),
            variables_json=_case_data_text(payload.get("variables")),
            description=payload.get("description", ""),
            is_active=payload.get("isActive", True),
        )
    except ServiceError as exc:
        return _error(str(exc))
    return _ok(_environment_payload(updated), "Environment updated.")


@api_v1_bp.route("/variables", methods=["GET", "POST"])
@_require_permission("variable:view")
def variables():
    if request.method == "POST":
        if not has_permission("variable:create"):
            return _error("Permission denied.", 403)
        payload = request.get_json(silent=True) or {}
        try:
            project_id = int(payload.get("projectId"))
        except (TypeError, ValueError):
            return _error("A project is required.")
        if project_id not in accessible_project_ids():
            return _error("Project access denied.", 403)
        try:
            variable = VariableService.create(
                project_id=project_id,
                name=payload.get("name"),
                value=payload.get("value", ""),
                scope=payload.get("scope", "project"),
                environment_id=payload.get("environmentId"),
                description=payload.get("description", ""),
            )
        except ServiceError as exc:
            return _error(str(exc))
        return _ok(_variable_payload(variable), "Variable created.")
    project_id = _scoped_project_id()
    query = Variable.query
    if project_id:
        query = query.filter(Variable.project_id == project_id)
    else:
        query = query.filter(Variable.project_id.in_(accessible_project_ids()))
    return _ok([_variable_payload(item) for item in query.order_by(Variable.updated_at.desc()).all()])


@api_v1_bp.route("/variables/<int:variable_id>", methods=["PATCH", "DELETE"])
@_require_permission("variable:view")
def variable_detail(variable_id):
    variable = db.session.get(Variable, variable_id)
    if not variable or variable.project_id not in accessible_project_ids():
        return _error("Variable not found.", 404)
    if request.method == "DELETE":
        if not has_permission("variable:delete"):
            return _error("Permission denied.", 403)
        try:
            VariableService.delete(variable_id)
        except ServiceError as exc:
            return _error(str(exc))
        return _ok(message="Variable deleted.")
    if not has_permission("variable:edit"):
        return _error("Permission denied.", 403)
    payload = request.get_json(silent=True) or {}
    try:
        updated = VariableService.update(
            variable_id=variable_id,
            name=payload.get("name"),
            value=payload.get("value", ""),
            scope=payload.get("scope", "project"),
            environment_id=payload.get("environmentId"),
            description=payload.get("description", ""),
        )
    except ServiceError as exc:
        return _error(str(exc))
    return _ok(_variable_payload(updated), "Variable updated.")


@api_v1_bp.route("/scenarios", methods=["GET", "POST"])
@_require_permission("scenario:view")
def scenarios():
    if request.method == "POST":
        if not has_permission("scenario:create"):
            return _error("Permission denied.", 403)
        payload = request.get_json(silent=True) or {}
        try:
            project_id = int(payload.get("projectId"))
        except (TypeError, ValueError):
            return _error("A project is required.")
        if project_id not in accessible_project_ids():
            return _error("Project access denied.", 403)
        try:
            scenario = ScenarioService.create(project_id, payload.get("moduleId"), payload.get("name"), payload.get("description", ""), payload.get("status", "active"), ",".join(payload.get("tags") or []))
        except ServiceError as exc:
            return _error(str(exc))
        return _ok(_scenario_payload(scenario, include_steps=True), "Scenario created.")
    project_id = _scoped_project_id()
    query = Scenario.query
    if project_id:
        query = query.filter(Scenario.project_id == project_id)
    else:
        query = query.filter(Scenario.project_id.in_(accessible_project_ids()))
    return _ok([_scenario_payload(item) for item in query.order_by(Scenario.updated_at.desc()).all()])


@api_v1_bp.route("/scenarios/<int:scenario_id>", methods=["GET", "PATCH", "DELETE"])
@_require_permission("scenario:view")
def scenario_detail(scenario_id):
    scenario = db.session.get(Scenario, scenario_id)
    if not scenario or scenario.project_id not in accessible_project_ids():
        return _error("Scenario not found.", 404)
    if request.method == "GET":
        return _ok(_scenario_payload(scenario, include_steps=True))
    if request.method == "DELETE":
        if not has_permission("scenario:delete"):
            return _error("Permission denied.", 403)
        try:
            ScenarioService.delete(scenario_id)
        except ServiceError as exc:
            return _error(str(exc))
        return _ok(message="Scenario deleted.")
    if not has_permission("scenario:edit"):
        return _error("Permission denied.", 403)
    payload = request.get_json(silent=True) or {}
    try:
        updated = ScenarioService.update(scenario_id, payload.get("moduleId"), payload.get("name"), payload.get("description", ""), payload.get("status", "active"), ",".join(payload.get("tags") or []))
    except ServiceError as exc:
        return _error(str(exc))
    return _ok(_scenario_payload(updated, include_steps=True), "Scenario updated.")


@api_v1_bp.route("/scenarios/<int:scenario_id>/steps", methods=["POST"])
@_require_permission("scenario:edit")
def create_scenario_step(scenario_id):
    scenario = db.session.get(Scenario, scenario_id)
    if not scenario or scenario.project_id not in accessible_project_ids():
        return _error("Scenario not found.", 404)
    payload = request.get_json(silent=True) or {}
    try:
        step = ScenarioService.add_step(scenario_id, payload.get("testcaseId"), payload.get("name", ""), payload.get("continueOnFailure", False), payload.get("isEnabled", True), _case_data_text(payload.get("setupVariables")), _case_data_text(payload.get("requestOverrides")), _case_data_text(payload.get("extractOverrides")), _case_data_text(payload.get("assertionOverrides") or []))
    except ServiceError as exc:
        return _error(str(exc))
    return _ok(_scenario_step_payload(step), "Scenario step created.")


@api_v1_bp.route("/scenario-steps/<int:step_id>", methods=["PATCH", "DELETE"])
@_require_permission("scenario:edit")
def scenario_step_detail(step_id):
    step = db.session.get(ScenarioStep, step_id)
    if not step or step.scenario.project_id not in accessible_project_ids():
        return _error("Scenario step not found.", 404)
    if request.method == "DELETE":
        try:
            ScenarioService.delete_step(step_id)
        except ServiceError as exc:
            return _error(str(exc))
        return _ok(message="Scenario step deleted.")
    payload = request.get_json(silent=True) or {}
    try:
        updated = ScenarioService.update_step(step_id, payload.get("testcaseId"), payload.get("name", ""), payload.get("continueOnFailure", False), payload.get("isEnabled", True), _case_data_text(payload.get("setupVariables")), _case_data_text(payload.get("requestOverrides")), _case_data_text(payload.get("extractOverrides")), _case_data_text(payload.get("assertionOverrides") or []))
    except ServiceError as exc:
        return _error(str(exc))
    return _ok(_scenario_step_payload(updated), "Scenario step updated.")


@api_v1_bp.route("/scenario-steps/<int:step_id>/move", methods=["POST"])
@_require_permission("scenario:edit")
def move_scenario_step(step_id):
    step = db.session.get(ScenarioStep, step_id)
    if not step or step.scenario.project_id not in accessible_project_ids():
        return _error("Scenario step not found.", 404)
    direction = (request.get_json(silent=True) or {}).get("direction")
    if direction == "up":
        ScenarioService.move_step_up(step_id)
    elif direction == "down":
        ScenarioService.move_step_down(step_id)
    else:
        return _error("Unsupported move direction.")
    return _ok(_scenario_payload(step.scenario, include_steps=True))


@api_v1_bp.route("/scenario-executions")
@_require_permission("scenario:view")
def scenario_executions():
    project_id = _scoped_project_id()
    query = ScenarioExecution.query.join(Scenario)
    if project_id:
        query = query.filter(Scenario.project_id == project_id)
    else:
        query = query.filter(Scenario.project_id.in_(accessible_project_ids()))
    return _ok([_scenario_execution_payload(item) for item in query.order_by(ScenarioExecution.created_at.desc()).limit(100).all()])


@api_v1_bp.route("/scenario-executions/<int:execution_id>")
@_require_permission("scenario:view")
def scenario_execution_detail(execution_id):
    execution = db.session.get(ScenarioExecution, execution_id)
    if not execution or execution.scenario.project_id not in accessible_project_ids():
        return _error("Scenario execution not found.", 404)
    return _ok(_scenario_execution_payload(execution, include_details=True))


@api_v1_bp.route("/scenario-runs", methods=["POST"])
@_require_permission("scenario:run")
def run_scenario():
    payload = request.get_json(silent=True) or {}
    scenario = db.session.get(Scenario, payload.get("scenarioId"))
    if not scenario or scenario.project_id not in accessible_project_ids():
        return _error("Scenario not found.", 404)
    user = get_current_user()
    try:
        execution = ScenarioExecutionService.run_scenario(scenario.id, payload.get("environmentId"), trigger_type="manual", trigger_user_id=user.id if user else None, persist_extracted_to_environment=payload.get("persistExtracted", False), runtime_injections=payload.get("runtimeInjections") or {})
    except ServiceError as exc:
        return _error(str(exc))
    return _ok(_scenario_execution_payload(execution, include_details=True), "Scenario execution completed.")


@api_v1_bp.route("/security/options")
def security_options():
    if not get_current_user():
        return _error("Authentication required.", 401)
    if not any(has_permission(code) for code in ("user:manage", "role:manage", "project_member:manage", "audit:view")):
        return _error("Permission denied.", 403)
    return _ok({"roles": [_role_payload(item) for item in SecurityService.list_roles()], "permissions": [_permission_payload(item) for item in SecurityService.list_permissions()], "memberCandidates": [{"id": item.id, "username": item.username, "displayName": item.display_name} for item in User.query.order_by(User.username.asc()).all()], "projects": [_project_payload(item) for item in Project.query.order_by(Project.created_at.desc()).all()], "accessLevels": PROJECT_ACCESS_LEVELS})


@api_v1_bp.route("/security/users", methods=["GET", "POST"])
@_require_permission("user:manage")
def security_users():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        try:
            user = SecurityService.create_user(payload.get("username"), payload.get("displayName", ""), payload.get("email", ""), payload.get("password", ""), payload.get("isActive", True), payload.get("isSuperuser", False), payload.get("roleCodes") or [])
        except ServiceError as exc:
            return _error(str(exc))
        return _ok(_user_payload(user), "User created.")
    return _ok([_user_payload(item) for item in SecurityService.list_users()])


@api_v1_bp.route("/security/users/<int:user_id>", methods=["PATCH", "DELETE"])
@_require_permission("user:manage")
def security_user_detail(user_id):
    try:
        user = SecurityService.get_user_by_id(user_id)
    except ServiceError as exc:
        return _error(str(exc), 404)
    if request.method == "DELETE":
        if user.is_superuser:
            return _error("Superusers cannot be deleted.")
        db.session.delete(user)
        db.session.commit()
        return _ok(message="User deleted.")
    payload = request.get_json(silent=True) or {}
    try:
        updated = SecurityService.update_user(user_id, payload.get("username"), payload.get("displayName", ""), payload.get("email", ""), payload.get("password", ""), payload.get("isActive", True), payload.get("isSuperuser", False), payload.get("roleCodes") or [])
    except ServiceError as exc:
        return _error(str(exc))
    return _ok(_user_payload(updated), "User updated.")


@api_v1_bp.route("/security/roles", methods=["GET", "POST"])
@_require_permission("role:manage")
def security_roles():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        try:
            role = SecurityService.create_role(payload.get("code"), payload.get("name"), payload.get("description", ""), payload.get("isSystem", False), payload.get("sortOrder", 0), payload.get("permissionCodes") or [])
        except ServiceError as exc:
            return _error(str(exc))
        return _ok(_role_payload(role), "Role created.")
    return _ok([_role_payload(item) for item in SecurityService.list_roles()])


@api_v1_bp.route("/security/roles/<int:role_id>", methods=["PATCH", "DELETE"])
@_require_permission("role:manage")
def security_role_detail(role_id):
    try:
        role = SecurityService.get_role_by_id(role_id)
    except ServiceError as exc:
        return _error(str(exc), 404)
    if request.method == "DELETE":
        if role.is_system:
            return _error("System roles cannot be deleted.")
        db.session.delete(role)
        db.session.commit()
        return _ok(message="Role deleted.")
    payload = request.get_json(silent=True) or {}
    try:
        updated = SecurityService.update_role(role_id, payload.get("code"), payload.get("name"), payload.get("description", ""), payload.get("isSystem", False), payload.get("sortOrder", 0), payload.get("permissionCodes") or [])
    except ServiceError as exc:
        return _error(str(exc))
    return _ok(_role_payload(updated), "Role updated.")


@api_v1_bp.route("/security/project-members", methods=["GET", "POST"])
@_require_permission("project_member:manage")
def security_project_members():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        try:
            member = SecurityService.update_project_member(payload.get("projectId"), payload.get("userId"), payload.get("accessLevel", "viewer"), payload.get("remark", ""))
        except ServiceError as exc:
            return _error(str(exc))
        return _ok(_project_member_payload(member), "Project member saved.")
    raw_project_id = request.args.get("project_id")
    try:
        project_id = int(raw_project_id) if raw_project_id else None
    except ValueError:
        return _error("Invalid project id.")
    return _ok([_project_member_payload(item) for item in SecurityService.list_project_members(project_id)])


@api_v1_bp.route("/security/project-members/<int:project_id>/<int:user_id>", methods=["DELETE"])
@_require_permission("project_member:manage")
def security_project_member_detail(project_id, user_id):
    try:
        SecurityService.remove_project_member(project_id, user_id)
    except ServiceError as exc:
        return _error(str(exc), 404)
    return _ok(message="Project member removed.")


@api_v1_bp.route("/security/audit")
@_require_permission("audit:view")
def security_audit():
    raw_project_id = request.args.get("project_id")
    try:
        project_id = int(raw_project_id) if raw_project_id else None
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        return _error("Invalid audit query.")
    pagination = SecurityService.list_audit_logs(page=page, per_page=30, project_id=project_id)
    return _ok({"items": [_audit_payload(item) for item in pagination.items], "page": pagination.page, "pages": pagination.pages, "total": pagination.total})


@api_v1_bp.route("/ui-automation/overview")
@_require_permission("uiauto:view")
def ui_automation_overview():
    project_id = _scoped_project_id()
    project_ids = [project_id] if project_id else accessible_project_ids()
    if not project_ids:
        return _ok({"scripts": [], "locators": [], "environments": [], "runs": []})
    return _ok({
        "scripts": [_ui_script_payload(item) for item in UiAutomationService.list_scripts(project_ids=project_ids)],
        "locators": [_ui_locator_payload(item) for item in UiAutomationService.list_locators(project_ids=project_ids)],
        "environments": [_ui_environment_payload(item) for item in UiAutomationService.list_environments(project_ids=project_ids)],
        "runs": [_ui_run_payload(item) for item in UiAutomationService.list_runs(project_ids=project_ids)[:100]],
    })


@api_v1_bp.route("/ui-automation/environments", methods=["GET", "POST"])
@_require_permission("uiauto:view")
def ui_automation_environments():
    if request.method == "GET":
        project_id = _scoped_project_id()
        project_ids = [project_id] if project_id else accessible_project_ids()
        if not project_ids:
            return _ok([])
        return _ok([_ui_environment_payload(item) for item in UiAutomationService.list_environments(project_ids=project_ids)])
    if not has_permission("uiauto:script:edit"):
        return _error("Permission denied.", 403)
    payload = request.get_json(silent=True) or {}
    try:
        project_id = int(payload.get("projectId"))
        if project_id not in accessible_project_ids():
            return _error("Project access denied.", 403)
        item = UiAutomationService.create_environment(project_id=project_id, name=payload.get("name"), base_url=payload.get("baseUrl"), browser_default=payload.get("browserDefault", "chromium"), headless_default=payload.get("headlessDefault", True), timeout_ms=payload.get("timeoutMs", 30000), retry_times=payload.get("retryTimes", 0), viewport_width=payload.get("viewportWidth", 1440), viewport_height=payload.get("viewportHeight", 900), storage_state_path=payload.get("storageStatePath", ""), proxy_config=payload.get("proxyConfig", {}), runtime_variables=payload.get("runtimeVariables", {}), status=payload.get("status", "active"), description=payload.get("description", ""))
    except (TypeError, ValueError, ServiceError) as exc:
        return _error(str(exc))
    return _ok(_ui_environment_payload(item), "Environment created.")


@api_v1_bp.route("/ui-automation/environments/<int:environment_id>", methods=["PATCH", "DELETE"])
@_require_permission("uiauto:script:edit")
def ui_automation_environment_detail(environment_id):
    item = db.session.get(UiAutomationEnvironment, environment_id)
    if not item or item.project_id not in accessible_project_ids():
        return _error("Environment not found.", 404)
    if request.method == "DELETE":
        UiAutomationService.delete_environment(environment_id)
        return _ok(message="Environment deleted.")
    payload = request.get_json(silent=True) or {}
    try:
        updated = UiAutomationService.update_environment(environment_id, name=payload.get("name"), base_url=payload.get("baseUrl"), browser_default=payload.get("browserDefault", item.browser_default), headless_default=payload.get("headlessDefault", item.headless_default), timeout_ms=payload.get("timeoutMs", item.timeout_ms), retry_times=payload.get("retryTimes", item.retry_times), viewport_width=payload.get("viewportWidth", item.viewport_width), viewport_height=payload.get("viewportHeight", item.viewport_height), storage_state_path=payload.get("storageStatePath", item.storage_state_path), proxy_config=payload.get("proxyConfig", item.proxy_config), runtime_variables=payload.get("runtimeVariables", item.runtime_variables), status=payload.get("status", item.status), description=payload.get("description", item.description))
    except (TypeError, ValueError, ServiceError) as exc:
        return _error(str(exc))
    return _ok(_ui_environment_payload(updated), "Environment updated.")


@api_v1_bp.route("/ui-automation/scripts/export")
@_require_permission("uiauto:script:view")
def ui_automation_export_scripts():
    project_id = _scoped_project_id()
    project_ids = [project_id] if project_id else accessible_project_ids()
    if not project_ids:
        return _ok({"items": []})
    return _ok({"items": [{**_ui_script_payload(item), "entryFile": item.entry_file, "language": item.language, "framework": item.framework} for item in UiAutomationService.list_scripts(project_ids=project_ids)]})


@api_v1_bp.route("/ui-automation/scripts/import", methods=["POST"])
@_require_permission("uiauto:script:create")
def ui_automation_import_scripts():
    payload = request.get_json(silent=True) or {}
    try:
        project_id = int(payload.get("projectId"))
        if project_id not in accessible_project_ids():
            return _error("Project access denied.", 403)
        items = payload.get("items") or []
        if not isinstance(items, list) or not items:
            return _error("A non-empty items list is required.")
        user = get_current_user(); created = []; errors = []
        for index, item in enumerate(items, start=1):
            try:
                if not isinstance(item, dict):
                    raise ServiceError("Item must be an object.")
                created.append(UiAutomationService.create_script(project_id, item.get("name"), item.get("code") or f"imported_{index}", item.get("description", ""), item.get("language", "python"), item.get("framework", "playwright"), item.get("status", "draft"), ",".join(item.get("tags", [])) if isinstance(item.get("tags"), list) else item.get("tags", ""), item.get("entryFile", ""), item.get("content") or item.get("scriptContent", ""), created_by=user.id if user else None, dependencies=item.get("dependencies"), require_login=item.get("needLogin", True)))
            except (TypeError, ValueError, ServiceError) as exc:
                errors.append({"index": index, "message": str(exc)})
    except (TypeError, ValueError) as exc:
        return _error(str(exc))
    return _ok({"created": [_ui_script_payload(item) for item in created], "errors": errors}, "Script import completed.")


@api_v1_bp.route("/ui-automation/scripts/<int:script_id>/detail")
@_require_permission("uiauto:script:view")
def ui_automation_script_full_detail(script_id):
    script = db.session.get(UiAutomationScript, script_id)
    if not script or script.project_id not in accessible_project_ids():
        return _error("Script not found.", 404)
    runs = UiAutomationRun.query.filter_by(script_id=script.id).order_by(UiAutomationRun.created_at.desc()).limit(20).all()
    return _ok({"script": {**_ui_script_payload(script), "language": script.language, "framework": script.framework, "entryFile": script.entry_file, "ownerId": script.owner_id}, "versions": [_ui_version_payload(item) for item in UiAutomationService.list_script_versions(script.id)], "recentRuns": [_ui_run_payload(item) for item in runs], "locatorContext": UiAutomationService.build_locator_context(project_id=script.project_id)})


@api_v1_bp.route("/ui-automation/scripts", methods=["POST"])
@_require_permission("uiauto:script:create")
def ui_automation_create_script():
    payload = request.get_json(silent=True) or {}; user = get_current_user()
    try:
        project_id = int(payload.get("projectId"))
        if project_id not in accessible_project_ids(): return _error("Project access denied.", 403)
        item = UiAutomationService.create_script(project_id, payload.get("name"), payload.get("code"), payload.get("description", ""), payload.get("language", "python"), payload.get("framework", "playwright"), payload.get("status", "draft"), payload.get("tags", []), payload.get("entryFile", ""), payload.get("content", ""), created_by=user.id if user else None, dependencies=payload.get("dependencies"), require_login=payload.get("needLogin", True))
    except (TypeError, ValueError, ServiceError) as exc: return _error(str(exc))
    return _ok(_ui_script_payload(item), "Script created.")


@api_v1_bp.route("/ui-automation/scripts/<int:script_id>", methods=["PATCH", "DELETE"])
@_require_permission("uiauto:script:edit")
def ui_automation_script_detail(script_id):
    item = db.session.get(UiAutomationScript, script_id)
    if not item or item.project_id not in accessible_project_ids(): return _error("Script not found.", 404)
    if request.method == "DELETE":
        if not has_permission("uiauto:script:delete"): return _error("Permission denied.", 403)
        UiAutomationService.delete_script(script_id); return _ok(message="Script deleted.")
    payload = request.get_json(silent=True) or {}; user = get_current_user()
    try: updated = UiAutomationService.update_script(script_id, payload.get("name"), payload.get("code"), payload.get("description", ""), payload.get("language", "python"), payload.get("framework", "playwright"), payload.get("status", "draft"), payload.get("tags", []), payload.get("entryFile", ""), payload.get("content", ""), created_by=user.id if user else None, change_summary=payload.get("changeSummary", "SPA update"), dependencies=payload.get("dependencies"), require_login=payload.get("needLogin"))
    except ServiceError as exc: return _error(str(exc))
    return _ok(_ui_script_payload(updated), "Script updated.")


@api_v1_bp.route("/ui-automation/scripts/<int:script_id>/versions")
@_require_permission("uiauto:script:view")
def ui_automation_script_versions(script_id):
    script = db.session.get(UiAutomationScript, script_id)
    if not script or script.project_id not in accessible_project_ids(): return _error("Script not found.", 404)
    return _ok([_ui_version_payload(item) for item in UiAutomationService.list_script_versions(script_id)])


@api_v1_bp.route("/ui-automation/scripts/<int:script_id>/versions/compare")
@_require_permission("uiauto:script:view")
def ui_automation_compare_versions(script_id):
    script = db.session.get(UiAutomationScript, script_id)
    if not script or script.project_id not in accessible_project_ids(): return _error("Script not found.", 404)
    try: from_id, to_id = int(request.args.get("from")), int(request.args.get("to"))
    except (TypeError, ValueError): return _error("Two versions are required.")
    versions = {item.id: item for item in UiAutomationService.list_script_versions(script_id)}; before, after = versions.get(from_id), versions.get(to_id)
    if not before or not after or before.id == after.id: return _error("Invalid versions.", 404)
    diff = list(difflib.unified_diff((before.script_content or "").splitlines(), (after.script_content or "").splitlines(), fromfile=f"v{before.version_no}", tofile=f"v{after.version_no}", lineterm=""))
    return _ok({"from": _ui_version_payload(before), "to": _ui_version_payload(after), "diff": "\n".join(diff)})


@api_v1_bp.route("/ui-automation/scripts/<int:script_id>/versions/<int:version_id>/restore", methods=["POST"])
@_require_permission("uiauto:script:edit")
def ui_automation_restore_version(script_id, version_id):
    script = db.session.get(UiAutomationScript, script_id)
    if not script or script.project_id not in accessible_project_ids(): return _error("Script not found.", 404)
    payload = request.get_json(silent=True) or {}; user = get_current_user()
    try: version = UiAutomationService.restore_script_version(script_id, version_id, created_by=user.id if user else None, change_summary=payload.get("changeSummary", "SPA restore"))
    except ServiceError as exc: return _error(str(exc))
    return _ok(_ui_version_payload(version), "Version restored.")


@api_v1_bp.route("/ui-automation/runs", methods=["POST"])
@_require_permission("uiauto:script:run")
def ui_automation_create_run():
    payload = request.get_json(silent=True) or {}; user = get_current_user()
    try:
        project_id = int(payload.get("projectId"))
        if project_id not in accessible_project_ids(): return _error("Project access denied.", 403)
        run = UiAutomationService.create_run(project_id, payload.get("scriptId"), payload.get("environmentId"), payload.get("browser", "chromium"), payload.get("runMode", "manual"), trigger_type="manual", trigger_user_id=user.id if user else None)
    except (TypeError, ValueError, ServiceError) as exc: return _error(str(exc))
    return _ok(_ui_run_payload(run), "Run queued.")


@api_v1_bp.route("/ui-automation/locators", methods=["POST"])
@_require_permission("uiauto:locator:manage")
def ui_automation_create_locator():
    payload = request.get_json(silent=True) or {}; user = get_current_user()
    try:
        project_id = int(payload.get("projectId"))
        if project_id not in accessible_project_ids(): return _error("Project access denied.", 403)
        item = UiAutomationService.create_locator(project_id, payload.get("name"), payload.get("code"), payload.get("type", "css"), payload.get("value"), payload.get("pageName", ""), payload.get("pageUrlPattern", ""), payload.get("description", ""), payload.get("usageScene", ""), payload.get("stable", True), payload.get("status", "active"), created_by=user.id if user else None)
    except (TypeError, ValueError, ServiceError) as exc: return _error(str(exc))
    return _ok(_ui_locator_payload(item), "Locator created.")


@api_v1_bp.route("/ui-automation/locators/<int:locator_id>", methods=["PATCH", "DELETE"])
@_require_permission("uiauto:locator:manage")
def ui_automation_locator_detail(locator_id):
    item = db.session.get(UiAutomationLocator, locator_id)
    if not item or item.project_id not in accessible_project_ids(): return _error("Locator not found.", 404)
    if request.method == "DELETE": UiAutomationService.delete_locator(locator_id); return _ok(message="Locator deleted.")
    payload = request.get_json(silent=True) or {}; user = get_current_user()
    try: updated = UiAutomationService.update_locator(locator_id, payload.get("name"), payload.get("code"), payload.get("type", "css"), payload.get("value"), payload.get("pageName", ""), payload.get("pageUrlPattern", ""), payload.get("description", ""), payload.get("usageScene", ""), payload.get("stable", True), payload.get("status", "active"), updated_by=user.id if user else None)
    except ServiceError as exc: return _error(str(exc))
    return _ok(_ui_locator_payload(updated), "Locator updated.")


@api_v1_bp.route("/ui-automation/locators/export")
@_require_permission("uiauto:locator:view")
def ui_automation_export_locators():
    project_id = _scoped_project_id()
    project_ids = [project_id] if project_id else accessible_project_ids()
    if not project_ids:
        return _ok({"items": []})
    return _ok({"items": UiAutomationService.export_locators(project_ids=project_ids)})


@api_v1_bp.route("/ui-automation/locators/import", methods=["POST"])
@_require_permission("uiauto:locator:manage")
def ui_automation_import_locators():
    payload = request.get_json(silent=True) or {}; user = get_current_user()
    try:
        project_id = int(payload.get("projectId"))
        if project_id not in accessible_project_ids():
            return _error("Project access denied.", 403)
        result = UiAutomationService.batch_import_locators(project_id, payload.get("items") or [], created_by=user.id if user else None)
    except (TypeError, ValueError, ServiceError) as exc:
        return _error(str(exc))
    return _ok({"created": [_ui_locator_payload(item) for item in result["created_locators"]], "errors": result["errors"]}, "Locator import completed.")


@api_v1_bp.route("/ui-automation/locators/batch", methods=["POST"])
@_require_permission("uiauto:locator:manage")
def ui_automation_batch_locators():
    payload = request.get_json(silent=True) or {}; user = get_current_user()
    try:
        locator_ids = [int(item) for item in payload.get("ids") or []]
        locators = UiAutomationLocator.query.filter(UiAutomationLocator.id.in_(locator_ids)).all()
        if len(locators) != len(set(locator_ids)) or any(item.project_id not in accessible_project_ids() for item in locators):
            return _error("Locator not found.", 404)
        result = UiAutomationService.bulk_update_locators(locator_ids, payload.get("action"), updated_by=user.id if user else None)
    except (TypeError, ValueError, ServiceError) as exc:
        return _error(str(exc))
    return _ok(result, "Locator batch action completed.")


@api_v1_bp.route("/ui-automation/runs/<int:run_id>/replay")
@_require_permission("uiauto:view")
def ui_automation_run_replay(run_id):
    run = db.session.get(UiAutomationRun, run_id)
    if not run or run.project_id not in accessible_project_ids():
        return _error("Run not found.", 404)
    artifacts = UiAutomationService.list_artifacts(run.id)
    steps = UiAutomationService.list_run_steps(run.id)
    artifacts_by_file_name = {item.file_name: item for item in artifacts}
    return _ok({"run": {**_ui_run_payload(run), "summary": run.summary, "errorStage": run.error_stage}, "artifacts": [_ui_artifact_payload(run, item) for item in artifacts], "steps": [_ui_replay_step_payload(run, item, artifacts_by_file_name) for item in steps], "failureAnalysis": UiAutomationService.analyze_run_failure(run)})


@api_v1_bp.route("/ui-automation/runs/<int:run_id>/artifacts/<int:artifact_id>/<string:mode>")
@_require_permission("uiauto:view")
def ui_automation_run_artifact(run_id, artifact_id, mode):
    run = db.session.get(UiAutomationRun, run_id)
    artifact = db.session.get(UiAutomationArtifact, artifact_id)
    if not run or run.project_id not in accessible_project_ids() or not artifact or artifact.run_id != run.id:
        return _error("Artifact not found.", 404)
    if mode not in {"preview", "download"}:
        return _error("Invalid artifact mode.", 404)
    try:
        path = UiAutomationWorker.resolve_artifact_path(artifact)
    except ServiceError as exc:
        return _error(str(exc), 404)
    return send_file(path, mimetype=artifact.mime_type or None, as_attachment=mode == "download", download_name=artifact.file_name)


@api_v1_bp.route("/android-automation/overview")
@_require_permission("android_uiauto:view")
def android_automation_overview():
    project_id = _scoped_project_id()
    project_ids = [project_id] if project_id else accessible_project_ids()
    worker = AndroidUiAutomationWorker.get_worker_health()
    try: devices = AndroidUiAutomationWorker.list_connected_devices_info()
    except ServiceError: devices = []
    if not project_ids:
        return _ok({"flows": [], "tasks": [], "runs": [], "devices": devices, "worker": worker, "stepTypes": [], "selectorTypes": []})
    flows = [item for item in AndroidUiAutomationService.list_project_flows() if item.project_id in project_ids]
    tasks = [item for item in AndroidUiAutomationService.list_tasks() if item.project_id in project_ids]
    runs = [item for item in AndroidUiAutomationService.list_runs() if item.project_id in project_ids]
    return _ok({"flows": [_android_flow_payload(item) for item in flows], "tasks": [_android_task_payload(item) for item in tasks], "runs": [_android_run_payload(item) for item in runs[:100]], "devices": devices, "worker": worker, "stepTypes": list(AndroidUiAutomationService.SUPPORTED_STEP_TYPES), "selectorTypes": list(AndroidUiAutomationService.SUPPORTED_SELECTOR_TYPES)})


@api_v1_bp.route("/android-automation/flows", methods=["POST"])
@_require_permission("android_uiauto:view")
def android_automation_create_flow():
    payload = request.get_json(silent=True) or {}; user = get_current_user()
    try:
        project_id = int(payload.get("projectId"))
        if project_id not in accessible_project_ids(): return _error("Project access denied.", 403)
        item = AndroidUiAutomationService.create_project_flow(project_id, payload.get("name"), payload.get("code"), payload.get("description", ""), payload.get("isDefault", False), payload.get("status", "active"), created_by=user.id if user else None)
    except (TypeError, ValueError, ServiceError) as exc: return _error(str(exc))
    return _ok(_android_flow_payload(item), "Flow created.")


@api_v1_bp.route("/android-automation/flows/<int:flow_id>", methods=["PATCH", "DELETE"])
@_require_permission("android_uiauto:view")
def android_automation_flow_detail(flow_id):
    item = db.session.get(AndroidUiProjectFlow, flow_id)
    if not item or item.project_id not in accessible_project_ids(): return _error("Flow not found.", 404)
    if request.method == "DELETE": AndroidUiAutomationService.delete_project_flow(flow_id); return _ok(message="Flow deleted.")
    payload = request.get_json(silent=True) or {}; user = get_current_user()
    try: updated = AndroidUiAutomationService.update_project_flow(flow_id, payload.get("name"), payload.get("code"), payload.get("description", ""), payload.get("isDefault", False), payload.get("status", "active"), updated_by=user.id if user else None)
    except ServiceError as exc: return _error(str(exc))
    return _ok(_android_flow_payload(updated), "Flow updated.")


@api_v1_bp.route("/android-automation/flows/<int:flow_id>/steps", methods=["POST"])
@_require_permission("android_uiauto:view")
def android_automation_create_flow_step(flow_id):
    flow = db.session.get(AndroidUiProjectFlow, flow_id)
    if not flow or flow.project_id not in accessible_project_ids(): return _error("Flow not found.", 404)
    payload = request.get_json(silent=True) or {}
    try: AndroidUiAutomationService.create_flow_step(flow_id, payload.get("name"), payload.get("type"), payload.get("selectorType", "none"), payload.get("selectorValue", ""), payload.get("inputValue", ""), payload.get("waitTimeoutSec", 20), payload.get("retryTimes", 0), payload.get("continueOnFailure", False), payload.get("captureOnSuccess", True), payload.get("captureOnFailure", True), payload.get("remark", ""))
    except (TypeError, ValueError, ServiceError) as exc: return _error(str(exc))
    return _ok(_android_flow_payload(flow), "Flow step created.")


@api_v1_bp.route("/android-automation/flow-steps/<int:step_id>", methods=["PATCH", "DELETE"])
@_require_permission("android_uiauto:view")
def android_automation_flow_step_detail(step_id):
    step = db.session.get(AndroidUiProjectFlowStep, step_id); flow = db.session.get(AndroidUiProjectFlow, step.flow_id) if step else None
    if not step or not flow or flow.project_id not in accessible_project_ids(): return _error("Flow step not found.", 404)
    if request.method == "DELETE": AndroidUiAutomationService.delete_flow_step(step_id); return _ok(_android_flow_payload(flow), "Flow step deleted.")
    payload = request.get_json(silent=True) or {}
    try: AndroidUiAutomationService.update_flow_step(step_id, payload.get("name"), payload.get("type"), payload.get("selectorType", "none"), payload.get("selectorValue", ""), payload.get("inputValue", ""), payload.get("waitTimeoutSec", 20), payload.get("retryTimes", 0), payload.get("continueOnFailure", False), payload.get("captureOnSuccess", True), payload.get("captureOnFailure", True), payload.get("remark", ""))
    except (TypeError, ValueError, ServiceError) as exc: return _error(str(exc))
    return _ok(_android_flow_payload(flow), "Flow step updated.")


@api_v1_bp.route("/android-automation/flow-presets")
@_require_permission("android_uiauto:view")
def android_automation_flow_presets():
    presets = [{"key": item.get("key", ""), "name": item.get("name", ""), "summary": item.get("summary", ""), "stepCount": len(item.get("steps") or [])} for item in AndroidUiAutomationService.flow_presets()]
    return _ok(presets)


@api_v1_bp.route("/android-automation/flows/<int:flow_id>/presets/<preset_key>", methods=["POST"])
@_require_permission("android_uiauto:view")
def android_automation_apply_flow_preset(flow_id, preset_key):
    flow = db.session.get(AndroidUiProjectFlow, flow_id)
    if not flow or flow.project_id not in accessible_project_ids():
        return _error("Flow not found.", 404)
    payload = request.get_json(silent=True) or {}
    try:
        updated, preset = AndroidUiAutomationService.apply_flow_preset(flow_id, preset_key, bool(payload.get("replaceExisting", True)))
    except ServiceError as exc:
        return _error(str(exc))
    return _ok({"flow": _android_flow_payload(updated), "preset": {"key": preset.get("key", ""), "name": preset.get("name", "")}}, "Flow preset applied.")


@api_v1_bp.route("/android-automation/tasks", methods=["POST"])
@_require_permission("android_uiauto:task:create")
def android_automation_create_task():
    payload = request.get_json(silent=True) or {}; user = get_current_user()
    try:
        project_id = int(payload.get("projectId"))
        if project_id not in accessible_project_ids(): return _error("Project access denied.", 403)
        item = AndroidUiAutomationService.create_task(project_id, payload.get("name"), payload.get("packageKey"), payload.get("flowMode", "basic"), payload.get("flowId"), payload.get("packageName", ""), payload.get("apkUrl", ""), payload.get("channelTag", ""), payload.get("deviceSerial", ""), payload.get("installTimeoutSec", 900), payload.get("launchWaitSec", 35), payload.get("autoUninstall", True), payload.get("remark", ""), created_by=user.id if user else None)
    except (TypeError, ValueError, ServiceError) as exc: return _error(str(exc))
    return _ok(_android_task_payload(item), "Task created.")


@api_v1_bp.route("/android-automation/tasks/<int:task_id>", methods=["PATCH", "DELETE"])
@_require_permission("android_uiauto:task:edit")
def android_automation_task_detail(task_id):
    item = db.session.get(AndroidUiTestTask, task_id)
    if not item or item.project_id not in accessible_project_ids(): return _error("Task not found.", 404)
    if request.method == "DELETE":
        if not has_permission("android_uiauto:task:delete"): return _error("Permission denied.", 403)
        AndroidUiAutomationService.delete_task(task_id); return _ok(message="Task deleted.")
    payload = request.get_json(silent=True) or {}; user = get_current_user()
    try: updated = AndroidUiAutomationService.update_task(task_id, payload.get("name"), payload.get("packageKey"), payload.get("flowMode", "basic"), payload.get("flowId"), payload.get("packageName", ""), payload.get("apkUrl", ""), payload.get("channelTag", ""), payload.get("deviceSerial", ""), payload.get("installTimeoutSec", 900), payload.get("launchWaitSec", 35), payload.get("autoUninstall", True), payload.get("isActive", True), payload.get("remark", ""), updated_by=user.id if user else None)
    except (TypeError, ValueError, ServiceError) as exc: return _error(str(exc))
    return _ok(_android_task_payload(updated), "Task updated.")


@api_v1_bp.route("/android-automation/tasks/<int:task_id>/runs", methods=["POST"])
@_require_permission("android_uiauto:task:run")
def android_automation_create_run(task_id):
    task = db.session.get(AndroidUiTestTask, task_id)
    if not task or task.project_id not in accessible_project_ids(): return _error("Task not found.", 404)
    try: run = AndroidUiAutomationService.create_run(task_id, created_by=get_current_user().id if get_current_user() else None)
    except ServiceError as exc: return _error(str(exc))
    return _ok(_android_run_payload(run), "Run queued.")


@api_v1_bp.route("/android-automation/runs/<int:run_id>/retry", methods=["POST"])
@_require_permission("android_uiauto:task:run")
def android_automation_retry_run(run_id):
    run = db.session.get(AndroidUiTestRun, run_id)
    if not run or run.project_id not in accessible_project_ids(): return _error("Run not found.", 404)
    try: new_run = AndroidUiAutomationService.retry_run(run_id, created_by=get_current_user().id if get_current_user() else None)
    except ServiceError as exc: return _error(str(exc))
    return _ok(_android_run_payload(new_run), "Run queued.")


@api_v1_bp.route("/android-automation/runs/<int:run_id>/detail")
@_require_permission("android_uiauto:execution:view")
def android_automation_run_detail(run_id):
    run = db.session.get(AndroidUiTestRun, run_id)
    if not run or run.project_id not in accessible_project_ids():
        return _error("Run not found.", 404)
    return _ok(_android_run_detail_payload(run))


@api_v1_bp.route("/android-automation/runs/<int:run_id>/artifacts/<artifact_kind>")
@_require_permission("android_uiauto:execution:view")
def android_automation_run_artifact(run_id, artifact_kind):
    run = db.session.get(AndroidUiTestRun, run_id)
    if not run or run.project_id not in accessible_project_ids():
        return _error("Run not found.", 404)
    path_value = run.screenshot_path if artifact_kind == "screenshot" else run.log_path if artifact_kind == "log" else ""
    path = Path(str(path_value or ""))
    if not path_value or not path.is_file():
        return _error("Artifact not found.", 404)
    return send_file(path, as_attachment=request.args.get("download") == "1", download_name=path.name)


@api_v1_bp.route("/android-automation/runs/<int:run_id>/artifacts/step/<int:step_id>/<int:artifact_id>")
@_require_permission("android_uiauto:execution:view")
def android_automation_run_step_artifact(run_id, step_id, artifact_id):
    run = db.session.get(AndroidUiTestRun, run_id)
    artifact = db.session.get(AndroidUiRunStepArtifact, artifact_id)
    if not run or run.project_id not in accessible_project_ids() or not artifact or artifact.run_step_id != step_id:
        return _error("Artifact not found.", 404)
    step = next((item for item in run.run_steps if item.id == step_id), None)
    path = Path(str(artifact.file_path or ""))
    if not step or not path.is_file():
        return _error("Artifact not found.", 404)
    return send_file(path, as_attachment=request.args.get("download") == "1", download_name=artifact.file_name or path.name)


@api_v1_bp.route("/android-automation/runs/<int:run_id>/artifacts/step/<int:step_id>/screenshot")
@_require_permission("android_uiauto:execution:view")
def android_automation_run_step_screenshot(run_id, step_id):
    run = db.session.get(AndroidUiTestRun, run_id)
    step = next((item for item in run.run_steps if item.id == step_id), None) if run else None
    path = Path(str(step.screenshot_path or "")) if step else None
    if not run or run.project_id not in accessible_project_ids() or not path or not path.is_file():
        return _error("Artifact not found.", 404)
    return send_file(path, as_attachment=request.args.get("download") == "1", download_name=path.name)


@api_v1_bp.route("/android-automation/runs/<int:run_id>/stop", methods=["POST"])
@_require_permission("android_uiauto:task:run")
def android_automation_stop_run(run_id):
    run = db.session.get(AndroidUiTestRun, run_id)
    if not run or run.project_id not in accessible_project_ids():
        return _error("Run not found.", 404)
    try:
        result = AndroidUiAutomationWorker.force_stop_run(run_id, requested_by=get_current_user().id if get_current_user() else None)
    except ServiceError as exc:
        return _error(str(exc))
    return _ok(result, "Run stopped.")


@api_v1_bp.route("/android-automation/worker/start", methods=["POST"])
@_require_permission("android_uiauto:task:run")
def android_automation_start_worker():
    try: return _ok(AndroidUiAutomationWorker.start_worker_process(), "Worker start requested.")
    except ServiceError as exc: return _error(str(exc))


@api_v1_bp.route("/android-automation/devices/<path:serial>", methods=["PATCH"])
@_require_permission("android_uiauto:view")
def android_automation_update_device(serial):
    payload = request.get_json(silent=True) or {}
    try:
        if "default" in payload and payload["default"]: AndroidUiAutomationWorker.set_default_device(serial)
        if "disabled" in payload: AndroidUiAutomationWorker.set_device_disabled(serial, bool(payload["disabled"]))
        if "annotationTag" in payload or "annotationNote" in payload: AndroidUiAutomationWorker.update_device_annotation(serial, payload.get("annotationTag", ""), payload.get("annotationNote", ""))
    except ServiceError as exc: return _error(str(exc))
    return _ok({"worker": AndroidUiAutomationWorker.get_worker_health()}, "Device updated.")


@api_v1_bp.route("/android-automation/devices/batch", methods=["POST"])
@_require_permission("android_uiauto:view")
def android_automation_batch_devices():
    payload = request.get_json(silent=True) or {}
    serials = [str(item).strip() for item in payload.get("serials", []) if str(item).strip()]
    action = str(payload.get("action") or "").strip().lower()
    if not serials:
        return _error("Select at least one device.")
    if action not in {"enable", "disable", "annotate", "set-default"}:
        return _error("Unsupported device batch action.")
    if action == "set-default" and len(serials) != 1:
        return _error("Select exactly one device to set as default.")
    succeeded, errors = [], []
    for serial in serials:
        try:
            if action == "enable": AndroidUiAutomationWorker.set_device_disabled(serial, False)
            elif action == "disable": AndroidUiAutomationWorker.set_device_disabled(serial, True)
            elif action == "annotate": AndroidUiAutomationWorker.update_device_annotation(serial, payload.get("annotationTag", ""), payload.get("annotationNote", ""))
            else: AndroidUiAutomationWorker.set_default_device(serial)
            succeeded.append(serial)
        except ServiceError as exc:
            errors.append({"serial": serial, "message": str(exc)})
    return _ok({"succeeded": succeeded, "errors": errors}, "Device batch action completed.")


@api_v1_bp.route("/android-automation/exceptions")
@_require_permission("android_uiauto:execution:view")
def android_automation_exceptions():
    project_id = _scoped_project_id(); ids = [project_id] if project_id else accessible_project_ids()
    runs = [item for item in AndroidUiAutomationService.list_runs() if item.project_id in ids and item.status == "failed"]
    return _ok([dict(_android_run_payload(item), retryAdvice=AndroidUiAutomationService.retry_advice(item)) for item in runs[:100]])


@api_v1_bp.route("/android-automation/exceptions/retry-batch", methods=["POST"])
@_require_permission("android_uiauto:task:run")
def android_automation_retry_exceptions_batch():
    payload = request.get_json(silent=True) or {}
    run_ids = [item for item in payload.get("runIds", []) if isinstance(item, int) or str(item).isdigit()]
    if not run_ids:
        return _error("Select at least one exception.")
    created, errors = [], []
    permitted = set(accessible_project_ids())
    for raw_id in run_ids:
        run = db.session.get(AndroidUiTestRun, int(raw_id))
        if not run or run.project_id not in permitted:
            errors.append({"id": raw_id, "message": "Run not found."})
            continue
        try:
            created.append(_android_run_payload(AndroidUiAutomationService.retry_run(run.id, created_by=get_current_user().id if get_current_user() else None)))
        except ServiceError as exc:
            errors.append({"id": run.id, "message": str(exc)})
    return _ok({"created": created, "errors": errors}, "Exception retry requested.")


@api_v1_bp.route("/testcases", methods=["GET", "POST"])
@_require_permission("testcase:view")
def testcases():
    if request.method == "POST":
        if not has_permission("testcase:create"):
            return _error("Permission denied.", 403)
        payload = request.get_json(silent=True) or {}
        try:
            project_id = int(payload.get("projectId"))
            module_id = int(payload.get("moduleId"))
        except (TypeError, ValueError):
            return _error("A project and module are required.")
        if project_id not in accessible_project_ids():
            return _error("Project access denied.", 403)
        try:
            testcase = TestCaseService.create(
                project_id=project_id,
                module_id=module_id,
                name=payload.get("name"),
                description=payload.get("description", ""),
                case_data=_case_data_text(payload.get("caseData")),
                source="manual",
                is_active=payload.get("enabled", True),
            )
        except ServiceError as exc:
            return _error(str(exc))
        return _ok(_testcase_payload(testcase), "Test case created.")

    project_id = _scoped_project_id()
    query = TestCase.query
    if project_id:
        query = query.filter(TestCase.project_id == project_id)
    else:
        query = query.filter(TestCase.project_id.in_(accessible_project_ids()))
    return _ok([_testcase_payload(item) for item in query.order_by(TestCase.updated_at.desc()).all()])


@api_v1_bp.route("/testcases/<int:testcase_id>", methods=["PATCH", "DELETE"])
@_require_permission("testcase:view")
def testcase_detail(testcase_id):
    testcase = db.session.get(TestCase, testcase_id)
    if not testcase or testcase.project_id not in accessible_project_ids():
        return _error("Test case not found.", 404)
    if request.method == "DELETE":
        if not has_permission("testcase:delete"):
            return _error("Permission denied.", 403)
        try:
            TestCaseService.delete(testcase_id)
        except ServiceError as exc:
            return _error(str(exc))
        return _ok(message="Test case deleted.")

    if not has_permission("testcase:edit"):
        return _error("Permission denied.", 403)
    payload = request.get_json(silent=True) or {}
    try:
        module_id = int(payload.get("moduleId"))
    except (TypeError, ValueError):
        return _error("A module is required.")
    try:
        updated = TestCaseService.update(
            testcase_id=testcase_id,
            module_id=module_id,
            name=payload.get("name"),
            description=payload.get("description", ""),
            case_data=_case_data_text(payload.get("caseData")),
            source="manual",
            is_active=payload.get("enabled", True),
        )
    except ServiceError as exc:
        return _error(str(exc))
    return _ok(_testcase_payload(updated), "Test case updated.")


@api_v1_bp.route("/executions")
@_require_permission("execution:view")
def executions():
    project_id = _scoped_project_id()
    query = Execution.query
    if project_id:
        query = query.filter(Execution.project_id == project_id)
    else:
        query = query.filter(Execution.project_id.in_(accessible_project_ids()))
    return _ok([_execution_payload(item) for item in query.order_by(Execution.created_at.desc()).limit(100).all()])


@api_v1_bp.route("/execution-options")
@_require_permission("execution:view")
def execution_options():
    project_id = _scoped_project_id()
    return _ok(_execution_run_options(project_id))


@api_v1_bp.route("/executions/<int:execution_id>/detail")
@_require_permission("execution:view")
def execution_detail(execution_id):
    execution = db.session.get(Execution, execution_id)
    if not execution or execution.project_id not in accessible_project_ids():
        return _error("Execution not found.", 404)
    return _ok(_execution_detail_payload(execution))


@api_v1_bp.route("/executions/<int:execution_id>/report")
@_require_permission("report:view")
def execution_report(execution_id):
    execution = db.session.get(Execution, execution_id)
    if not execution or execution.project_id not in accessible_project_ids():
        return _error("Execution not found.", 404)
    try:
        report = ReportService.generate(execution_id)
    except ServiceError as exc:
        return _error(str(exc))
    return _ok({"id": report.id, "title": report.title, "executionId": report.execution_id, "data": report.data})


@api_v1_bp.route("/execution-runs", methods=["POST"])
@_require_permission("execution:run")
def create_execution_run():
    payload = request.get_json(silent=True) or {}
    mode = payload.get("mode")
    environment_id = payload.get("environmentId")
    user = get_current_user()
    trigger = {"trigger_type": "manual", "trigger_user_id": user.id if user else None}
    try:
        if mode == "testcase":
            testcase_id = int(payload.get("testcaseId"))
            testcase = db.session.get(TestCase, testcase_id)
            if not testcase or testcase.project_id not in accessible_project_ids():
                return _error("Test case not found.", 404)
            execution = ExecutionService.run_testcase(testcase_id=testcase_id, environment_id=environment_id, **trigger)
        elif mode == "module":
            module_id = int(payload.get("moduleId"))
            module = db.session.get(Module, module_id)
            if not module or module.project_id not in accessible_project_ids():
                return _error("Module not found.", 404)
            execution = ExecutionService.run_module(module_id=module_id, environment_id=environment_id, **trigger)
        elif mode == "selection":
            testcase_ids = [int(item) for item in (payload.get("testcaseIds") or [])]
            testcases = TestCase.query.filter(TestCase.id.in_(testcase_ids)).all() if testcase_ids else []
            if not testcases or any(item.project_id not in accessible_project_ids() for item in testcases):
                return _error("No accessible test cases selected.", 400)
            execution = ExecutionService.run_selected_testcases(testcase_ids=testcase_ids, environment_id=environment_id, **trigger)
        elif mode == "project":
            project_id = int(payload.get("projectId"))
            if project_id not in accessible_project_ids():
                return _error("Project access denied.", 403)
            execution = ExecutionService.run_project(project_id=project_id, environment_id=environment_id, **trigger)
        else:
            return _error("Unsupported execution mode.")
    except (TypeError, ValueError):
        return _error("Invalid execution target.")
    except ServiceError as exc:
        return _error(str(exc))
    return _ok(_execution_payload(execution), "Execution completed.")
