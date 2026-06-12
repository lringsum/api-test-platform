from datetime import datetime
from io import BytesIO
import difflib
import json

from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for

from app import db
from app.models import Project, UiAutomationArtifact, UiAutomationEnvironment
from app.project_context import resolve_project_id
from app.routes import handle_page_error, handle_success
from app.security import accessible_project_ids, get_current_user, require_permission
from app.services.base_service import ServiceError, parse_json_text
from app.services.ui_automation_ai_service import UiAutomationAIService
from app.services.ui_automation_service import DEFAULT_SCRIPT_TEMPLATE, UiAutomationService
from app.services.ui_automation_worker import UiAutomationWorker


ui_automation_bp = Blueprint("ui_auto", __name__, url_prefix="/ui-automation")


SECTION_META = {
    "overview": {
        "title": "UI 自动化总览",
        "desc": "统一承载脚本、定位器、执行与回放能力，后续会逐步接入 AI 生成与修复。",
        "primary": "脚本管理",
        "secondary": "定位器库",
    },
    "scripts": {
        "title": "脚本管理",
        "desc": "脚本优先的管理方式，适合后续交给 AI 生成和修复。",
        "primary": "新建脚本",
        "secondary": "批量导入",
    },
    "locators": {
        "title": "定位器库",
        "desc": "沉淀稳定定位器，降低脚本维护成本。",
        "primary": "新增定位器",
        "secondary": "导入定位器",
    },
    "executions": {
        "title": "执行计划",
        "desc": "管理手动执行、定时执行和并发队列。",
        "primary": "新建执行",
        "secondary": "队列管理",
    },
    "replays": {
        "title": "报告回放",
        "desc": "集中查看截图、视频、Trace 和控制台日志。",
        "primary": "查看报告",
        "secondary": "Trace 回放",
    },
}


def _resolve_meta(section):
    return SECTION_META.get(section, SECTION_META["overview"])


def _run_environment_name(run):
    summary = run.summary if run.summary else {}
    environment_name = summary.get("environment_name", "")
    if environment_name:
        return environment_name
    if run.environment_id:
        environment = db.session.get(UiAutomationEnvironment, run.environment_id)
        if environment:
            return environment.name
    return ""


@ui_automation_bp.route("/")
@ui_automation_bp.route("/<section>")
@require_permission("uiauto:view")
def index(section="overview"):
    if section == "scripts":
        return redirect(url_for("ui_auto.scripts_page"))
    if section == "locators":
        return redirect(url_for("ui_auto.locators_page"))
    if section == "executions":
        return redirect(url_for("ui_auto.executions_page"))
    if section == "replays":
        return redirect(url_for("ui_auto.replays_page"))
    return render_template(
        "ui_automation/index.html",
        section=section,
        section_meta=_resolve_meta(section),
        sections=SECTION_META,
    )


@ui_automation_bp.route("/scripts")
@require_permission("uiauto:script:view")
def scripts_page():
    keyword = (request.args.get("keyword") or "").strip()
    status = (request.args.get("status") or "").strip()

    selected_project_id = resolve_project_id()
    accessible_ids = accessible_project_ids()
    if selected_project_id:
        scripts = UiAutomationService.list_scripts(project_id=selected_project_id)
    elif accessible_ids:
        scripts = UiAutomationService.list_scripts(project_ids=accessible_ids)
    else:
        scripts = []

    if selected_project_id and selected_project_id in accessible_ids:
        ai_locator_context = UiAutomationService.build_locator_ai_context(project_id=selected_project_id)
    elif accessible_ids:
        ai_locator_context = UiAutomationService.build_locator_ai_context(project_ids=accessible_ids)
    else:
        ai_locator_context = []

    if keyword:
        lowered = keyword.lower()
        scripts = [
            script
            for script in scripts
            if lowered in script.name.lower()
            or lowered in script.code.lower()
            or lowered in (script.description or "").lower()
        ]
    if status:
        scripts = [script for script in scripts if script.status == status]

    current_user = get_current_user()
    script_rows = []
    for script in scripts:
        current_version = None
        if script.current_version_id:
            current_version = next((version for version in script.versions if version.id == script.current_version_id), None)
        if not current_version and script.versions:
            current_version = script.versions[0]
        recent_runs = []
        for run in UiAutomationService.list_script_runs(script.id, limit=5):
            recent_runs.append(
                {
                    "id": run.id,
                    "status": run.status,
                    "environment_name": _run_environment_name(run),
                    "browser_type": run.browser_type,
                    "run_mode": run.run_mode,
                    "duration_ms": run.duration_ms,
                    "created_at": run.created_at.strftime("%Y-%m-%d %H:%M:%S") if run.created_at else "-",
                }
            )
        detail_payload = {
            "script_id": script.id,
            "name": script.name,
            "code": script.code,
            "description": script.description,
            "language": script.language,
            "framework": script.framework,
            "status": script.status,
            "entry_file": script.entry_file,
            "owner_name": script.owner.display_name if script.owner else "",
            "project_id": script.project_id,
            "version_count": len(script.versions),
            "current_version_no": current_version.version_no if current_version else None,
            "current_version_summary": current_version.change_summary if current_version else "",
            "current_version_content": current_version.script_content if current_version else DEFAULT_SCRIPT_TEMPLATE,
            "ai_prompt": current_version.ai_prompt if current_version else "",
            "ai_generated": bool(current_version.ai_generated) if current_version else False,
            "recent_runs": recent_runs,
            "tags": script.tags,
        }
        script_rows.append(
            {
                "script": script,
                "current_version": current_version,
                "owner_name": script.owner.display_name if script.owner else "",
                "version_count": len(script.versions),
                "recent_runs": recent_runs,
                "detail_payload": detail_payload,
            }
        )

    return render_template(
        "ui_automation/scripts.html",
        scripts=script_rows,
        keyword=keyword,
        selected_status=status,
        selected_project_id=selected_project_id,
        current_user=current_user,
        default_script_template=DEFAULT_SCRIPT_TEMPLATE,
        ai_locator_context=ai_locator_context,
        ai_locator_codes=", ".join(locator["code"] for locator in ai_locator_context[:20]),
    )


@ui_automation_bp.route("/scripts/create", methods=["POST"])
@require_permission("uiauto:script:create")
def create_script():
    try:
        current_user = get_current_user()
        owner_id = request.form.get("owner_id")
        if owner_id:
            try:
                owner_id = int(owner_id)
            except (TypeError, ValueError):
                owner_id = None
        elif current_user:
            owner_id = current_user.id

        project_id = int(request.form.get("project_id") or 0)
        if project_id not in accessible_project_ids():
            raise ServiceError("你没有访问该项目的权限。")

        UiAutomationService.create_script(
            project_id=project_id,
            name=request.form.get("name"),
            code=request.form.get("code"),
            description=request.form.get("description", ""),
            language=request.form.get("language", "python"),
            framework=request.form.get("framework", "playwright"),
            status=request.form.get("status", "draft"),
            tags_text=request.form.get("tags", ""),
            entry_file=request.form.get("entry_file", ""),
            script_content=request.form.get("script_content"),
            owner_id=owner_id,
            created_by=current_user.id if current_user else None,
            ai_generated=request.form.get("ai_generated") == "1",
            ai_prompt=request.form.get("ai_prompt", ""),
        )
        return handle_success("UI 脚本创建成功。", "ui_auto.scripts_page")
    except (ServiceError, TypeError, ValueError) as exc:
        return handle_page_error(str(exc), "ui_auto.scripts_page")


@ui_automation_bp.route("/scripts/ai-generate", methods=["POST"])
@require_permission("uiauto:script:create")
def generate_script():
    try:
        current_user = get_current_user()
        project_id = request.form.get("project_id") or resolve_project_id()
        if not project_id:
            raise ServiceError("请先选择一个项目，再生成 UI 脚本。")
        project_id = int(project_id)
        if project_id not in accessible_project_ids():
            raise ServiceError("你没有访问该项目的权限。")

        result = UiAutomationAIService.generate_script(
            project_id=project_id,
            script_name=request.form.get("script_name"),
            script_code=request.form.get("script_code"),
            test_goal=request.form.get("test_goal"),
            page_url=request.form.get("page_url", ""),
            page_name=request.form.get("page_name", ""),
            need_login=request.form.get("need_login") == "1",
            login_url=request.form.get("login_url", "/login"),
            login_username=request.form.get("login_username", "admin"),
            login_password=request.form.get("login_password", "admin123"),
            assert_text=request.form.get("assert_text", ""),
            locator_codes=request.form.get("locator_codes", ""),
            description=request.form.get("description", ""),
            entry_file=request.form.get("entry_file", "tests/test_ai_generated.py"),
            created_by=current_user.id if current_user else None,
        )
        flash(
            f"AI 脚本生成成功，已保存为草稿：{result['script'].name}",
            "success",
        )
        return redirect(url_for("ui_auto.scripts_page", project_id=project_id))
    except (ServiceError, TypeError, ValueError) as exc:
        return handle_page_error(str(exc), "ui_auto.scripts_page")


@ui_automation_bp.route("/scripts/<int:script_id>/edit", methods=["POST"])
@require_permission("uiauto:script:edit")
def edit_script(script_id):
    try:
        current_user = get_current_user()
        owner_id = request.form.get("owner_id")
        if owner_id:
            try:
                owner_id = int(owner_id)
            except (TypeError, ValueError):
                owner_id = None
        elif current_user:
            owner_id = current_user.id

        UiAutomationService.update_script(
            script_id=script_id,
            name=request.form.get("name"),
            code=request.form.get("code"),
            description=request.form.get("description", ""),
            language=request.form.get("language", "python"),
            framework=request.form.get("framework", "playwright"),
            status=request.form.get("status", "draft"),
            tags_text=request.form.get("tags", ""),
            entry_file=request.form.get("entry_file", ""),
            script_content=request.form.get("script_content"),
            owner_id=owner_id,
            created_by=current_user.id if current_user else None,
            ai_generated=request.form.get("ai_generated") == "1",
            ai_prompt=request.form.get("ai_prompt", ""),
            change_summary=request.form.get("change_summary", "内容更新"),
        )
        return handle_success("UI 脚本更新成功。", "ui_auto.scripts_page")
    except ServiceError as exc:
        return handle_page_error(str(exc), "ui_auto.scripts_page")


@ui_automation_bp.route("/scripts/<int:script_id>/delete", methods=["POST"])
@require_permission("uiauto:script:delete")
def delete_script(script_id):
    try:
        UiAutomationService.delete_script(script_id)
        flash("UI 脚本删除成功。", "success")
        return redirect(url_for("ui_auto.scripts_page"))
    except ServiceError as exc:
        return handle_page_error(str(exc), "ui_auto.scripts_page")


@ui_automation_bp.route("/scripts/<int:script_id>/ai-repair", methods=["POST"])
@require_permission("uiauto:script:edit")
def ai_repair_script(script_id):
    try:
        current_user = get_current_user()
        run_id = int(request.form.get("run_id") or 0)
        if not run_id:
            raise ServiceError("请先选择一条失败执行记录。")

        source_run = _get_accessible_run(run_id)
        result = UiAutomationAIService.repair_script_from_run(
            script_id=script_id,
            run_id=run_id,
            instruction=request.form.get("instruction", ""),
            created_by=current_user.id if current_user else None,
            locator_codes=request.form.get("locator_codes", ""),
        )
        auto_execute = request.form.get("auto_execute") == "1"
        if auto_execute:
            run = UiAutomationService.create_run(
                project_id=source_run.project_id,
                script_id=script_id,
                environment_id=source_run.environment_id,
                browser_type=source_run.browser_type,
                run_mode="ai_repair",
                max_retry=source_run.max_retry,
                trigger_source="ui_ai_repair",
                trigger_user_id=current_user.id if current_user else None,
            )
            UiAutomationWorker.execute_run(run.id)
            flash(f"AI 修复已完成并已重新执行，当前结果：{run.status}。", "success")
            return redirect(url_for("ui_auto.replay_detail_page", run_id=run.id))

        repaired_version = result["script"].versions[0] if result["script"].versions else None
        flash(
            f"AI 修复成功，已生成新版本 v{repaired_version.version_no if repaired_version else 1}。",
            "success",
        )
        return redirect(url_for("ui_auto.script_versions_page", script_id=script_id))
    except (ServiceError, TypeError, ValueError) as exc:
        flash(str(exc), "danger")
        return redirect(url_for("ui_auto.replay_detail_page", run_id=run_id if run_id else 0))


def _resolve_scripts_project_id(form):
    project_id = form.get("project_id") or resolve_project_id()
    if not project_id:
        raise ServiceError("请先选择一个项目。")
    project_id = int(project_id)
    if project_id not in accessible_project_ids():
        raise ServiceError("你没有访问该项目的权限。")
    return project_id


def _normalize_batch_script_code(name, index, used_codes):
    base_code = UiAutomationAIService._normalize_code(name or f"batch_script_{index}")
    candidate = base_code
    suffix = 2
    while candidate in used_codes:
        candidate = f"{base_code}_{suffix}"
        suffix += 1
    used_codes.add(candidate)
    return candidate


def _parse_batch_items(raw_text, field_name):
    payload = parse_json_text(raw_text, field_name)
    if isinstance(payload, dict):
        payload = payload.get("items") or payload.get("scripts") or payload.get("jobs") or [payload]
    if not isinstance(payload, list) or not payload:
        raise ServiceError(f"{field_name} 必须是非空 JSON 数组。")
    return payload


@ui_automation_bp.route("/scripts/batch-import", methods=["POST"])
@require_permission("uiauto:script:create")
def batch_import_scripts():
    try:
        current_user = get_current_user()
        project_id = _resolve_scripts_project_id(request.form)
        items = _parse_batch_items(request.form.get("batch_scripts_json", ""), "批量导入脚本 JSON")
        success_count = 0
        errors = []
        used_codes = set()

        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                errors.append(f"第 {index} 项不是对象。")
                continue

            name = str(item.get("name") or "").strip()
            code = str(item.get("code") or item.get("script_code") or "").strip().lower()
            if not code:
                code = _normalize_batch_script_code(name, index, used_codes)
            elif code in used_codes:
                errors.append(f"第 {index} 项脚本编码重复：{code}")
                continue
            else:
                used_codes.add(code)

            tags_value = item.get("tags", "")
            if isinstance(tags_value, list):
                tags_text = ",".join(str(tag).strip() for tag in tags_value if str(tag).strip())
            else:
                tags_text = str(tags_value or "").strip()

            owner_id = item.get("owner_id")
            if owner_id not in (None, ""):
                try:
                    owner_id = int(owner_id)
                except (TypeError, ValueError):
                    owner_id = None
            else:
                owner_id = current_user.id if current_user else None

            try:
                UiAutomationService.create_script(
                    project_id=project_id,
                    name=name,
                    code=code,
                    description=item.get("description", ""),
                    language=item.get("language", "python"),
                    framework=item.get("framework", "playwright"),
                    status=item.get("status", "draft"),
                    tags_text=tags_text,
                    entry_file=item.get("entry_file", ""),
                    script_content=item.get("script_content", ""),
                    owner_id=owner_id,
                    created_by=current_user.id if current_user else None,
                    ai_generated=str(item.get("ai_generated", "")).lower() in {"1", "true", "yes"},
                    ai_prompt=item.get("ai_prompt", ""),
                )
                success_count += 1
            except ServiceError as exc:
                errors.append(f"第 {index} 项：{exc}")

        if success_count == 0:
            raise ServiceError("批量导入失败：" + ("；".join(errors[:3]) if errors else "没有可导入的数据。"))

        if errors:
            flash(f"批量导入完成：成功 {success_count} 条，失败 {len(errors)} 条。", "warning")
            for message in errors[:5]:
                flash(message, "warning")
        else:
            flash(f"批量导入成功，共 {success_count} 条。", "success")
        return redirect(url_for("ui_auto.scripts_page", project_id=project_id))
    except (ServiceError, TypeError, ValueError) as exc:
        return handle_page_error(str(exc), "ui_auto.scripts_page")


@ui_automation_bp.route("/scripts/batch-generate", methods=["POST"])
@require_permission("uiauto:script:create")
def batch_generate_scripts():
    try:
        current_user = get_current_user()
        project_id = _resolve_scripts_project_id(request.form)
        items = _parse_batch_items(request.form.get("batch_jobs_json", ""), "批量生成脚本 JSON")
        success_count = 0
        errors = []
        used_codes = set()

        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                errors.append(f"第 {index} 项不是对象。")
                continue

            script_name = str(item.get("script_name") or item.get("name") or "").strip()
            if not script_name:
                errors.append(f"第 {index} 项缺少 script_name。")
                continue

            script_code = str(item.get("script_code") or item.get("code") or "").strip().lower()
            if not script_code:
                script_code = _normalize_batch_script_code(script_name, index, used_codes)
            elif script_code in used_codes:
                errors.append(f"第 {index} 项脚本编码重复：{script_code}")
                continue
            else:
                used_codes.add(script_code)

            try:
                UiAutomationAIService.generate_script(
                    project_id=project_id,
                    script_name=script_name,
                    script_code=script_code,
                    test_goal=item.get("test_goal", ""),
                    page_url=item.get("page_url", ""),
                    page_name=item.get("page_name", ""),
                    need_login=str(item.get("need_login", "")).lower() in {"1", "true", "yes"},
                    login_url=item.get("login_url", "/login"),
                    login_username=item.get("login_username", "admin"),
                    login_password=item.get("login_password", "admin123"),
                    assert_text=item.get("assert_text", ""),
                    locator_codes=item.get("locator_codes", ""),
                    description=item.get("description", ""),
                    entry_file=item.get("entry_file", "tests/test_ai_generated.py"),
                    created_by=current_user.id if current_user else None,
                )
                success_count += 1
            except ServiceError as exc:
                errors.append(f"第 {index} 项：{exc}")

        if success_count == 0:
            raise ServiceError("批量生成失败：" + ("；".join(errors[:3]) if errors else "没有可生成的数据。"))

        if errors:
            flash(f"批量生成完成：成功 {success_count} 条，失败 {len(errors)} 条。", "warning")
            for message in errors[:5]:
                flash(message, "warning")
        else:
            flash(f"批量生成成功，共 {success_count} 条。", "success")
        return redirect(url_for("ui_auto.scripts_page", project_id=project_id))
    except (ServiceError, TypeError, ValueError) as exc:
        return handle_page_error(str(exc), "ui_auto.scripts_page")


def _get_accessible_locator(locator_id):
    locator = UiAutomationService.get_locator_by_id(locator_id)
    if locator.project_id not in accessible_project_ids():
        raise ServiceError("你没有访问该定位器的权限。")
    return locator


@ui_automation_bp.route("/scripts/<int:script_id>/versions")
@require_permission("uiauto:script:view")
def script_versions_page(script_id):
    try:
        script = UiAutomationService.get_script_by_id(script_id)
        if script.project_id not in accessible_project_ids():
            raise ServiceError("浣犳病鏈夎闂鑴氭湰鐨勬潈闄愩€?")
        versions = UiAutomationService.list_script_versions(script.id)
        current_version = None
        if script.current_version_id:
            current_version = next((version for version in versions if version.id == script.current_version_id), None)
        if not current_version and versions:
            current_version = versions[0]
        return render_template(
            "ui_automation/script_versions.html",
            script=script,
            versions=versions,
            current_version=current_version,
        )
    except ServiceError as exc:
        return handle_page_error(str(exc), "ui_auto.scripts_page")


@ui_automation_bp.route("/scripts/<int:script_id>/versions/compare")
@require_permission("uiauto:script:view")
def compare_script_versions_page(script_id):
    try:
        script = UiAutomationService.get_script_by_id(script_id)
        if script.project_id not in accessible_project_ids():
            raise ServiceError("你没有访问该脚本版本的权限。")

        versions = UiAutomationService.list_script_versions(script.id)
        if len(versions) < 2:
            raise ServiceError("至少需要两个版本才能进行对比。")

        version_map = {version.id: version for version in versions}
        current_version = version_map.get(script.current_version_id) if script.current_version_id else None
        if not current_version and versions:
            current_version = versions[0]

        to_version_id = request.args.get("to_version_id", type=int)
        from_version_id = request.args.get("from_version_id", type=int)

        to_version = version_map.get(to_version_id) if to_version_id else current_version
        if not to_version:
            to_version = versions[0]

        ordered_versions = sorted(versions, key=lambda item: item.version_no)
        if from_version_id:
            from_version = version_map.get(from_version_id)
        else:
            from_version = None
            for index, version in enumerate(ordered_versions):
                if version.id == to_version.id and index > 0:
                    from_version = ordered_versions[index - 1]
                    break
            if not from_version:
                from_version = ordered_versions[0]

        if not from_version or from_version.id == to_version.id:
            raise ServiceError("请选择两个不同的版本进行对比。")

        diff_lines = list(
            difflib.unified_diff(
                (from_version.script_content or "").splitlines(),
                (to_version.script_content or "").splitlines(),
                fromfile=f"v{from_version.version_no}",
                tofile=f"v{to_version.version_no}",
                lineterm="",
            )
        )
        return render_template(
            "ui_automation/script_versions_compare.html",
            script=script,
            versions=versions,
            from_version=from_version,
            to_version=to_version,
            diff_text="\n".join(diff_lines) if diff_lines else "两个版本内容完全一致。",
            current_version=current_version,
        )
    except ServiceError as exc:
        return handle_page_error(str(exc), "ui_auto.scripts_page")


@ui_automation_bp.route("/scripts/<int:script_id>/versions/<int:version_id>/restore", methods=["POST"])
@require_permission("uiauto:script:edit")
def restore_script_version(script_id, version_id):
    try:
        script = UiAutomationService.get_script_by_id(script_id)
        if script.project_id not in accessible_project_ids():
            raise ServiceError("浣犳病鏈夎闂鑴氭湰鐨勬潈闄愩€?")
        current_user = get_current_user()
        restored = UiAutomationService.restore_script_version(
            script_id=script.id,
            version_id=version_id,
            created_by=current_user.id if current_user else None,
            change_summary=request.form.get("change_summary", "版本回滚"),
        )
        flash(f"已回滚到新版本 v{restored.version_no}。", "success")
        return redirect(url_for("ui_auto.script_versions_page", script_id=script.id))
    except ServiceError as exc:
        return handle_page_error(str(exc), "ui_auto.scripts_page")


@ui_automation_bp.route("/locators")
@require_permission("uiauto:locator:view")
def locators_page():
    keyword = (request.args.get("keyword") or "").strip()
    page_name = (request.args.get("page_name") or "").strip()
    locator_type = (request.args.get("locator_type") or "").strip().lower()
    status = (request.args.get("status") or "").strip().lower()
    stable = (request.args.get("stable") or "").strip().lower()

    selected_project_id = resolve_project_id()
    accessible_ids = accessible_project_ids()
    if selected_project_id and selected_project_id in accessible_ids:
        locators = UiAutomationService.list_locators(project_id=selected_project_id)
    elif accessible_ids:
        locators = UiAutomationService.list_locators(project_ids=accessible_ids)
    else:
        locators = []

    if keyword:
        lowered = keyword.lower()
        locators = [
            locator
            for locator in locators
            if lowered in locator.locator_code.lower()
            or lowered in locator.locator_name.lower()
            or lowered in locator.page_name.lower()
            or lowered in locator.description.lower()
            or lowered in locator.locator_value.lower()
        ]
    if page_name:
        locators = [locator for locator in locators if locator.page_name == page_name]
    if locator_type:
        locators = [locator for locator in locators if locator.locator_type == locator_type]
    if status:
        locators = [locator for locator in locators if locator.status == status]
    if stable in {"yes", "no"}:
        expected = stable == "yes"
        locators = [locator for locator in locators if locator.is_stable is expected]

    all_locators = (
        UiAutomationService.list_locators(project_id=selected_project_id)
        if selected_project_id and selected_project_id in accessible_ids
        else UiAutomationService.list_locators(project_ids=accessible_ids)
        if accessible_ids
        else []
    )
    page_names = sorted({locator.page_name for locator in all_locators if locator.page_name})
    locator_overview = UiAutomationService.build_locator_usage_map(
        project_id=selected_project_id if selected_project_id and selected_project_id in accessible_ids else None,
        project_ids=None if selected_project_id and selected_project_id in accessible_ids else accessible_ids,
    )
    locator_usage_map = locator_overview["usage_map"]
    locator_rows = []
    for locator in locators:
        usage_info = locator_usage_map.get(locator.locator_code, {})
        locator_rows.append(
            {
                "locator": locator,
                "usage_count": usage_info.get("usage_count", 0),
                "usage_scripts": usage_info.get("scripts", []),
                "matched_by": usage_info.get("matched_by", []),
            }
        )
    stats = {
        "total": len(all_locators),
        "stable": sum(1 for locator in all_locators if locator.is_stable),
        "active": sum(1 for locator in all_locators if locator.status == "active"),
        "pages": len(page_names),
        "used": locator_overview["summary"]["used"],
        "unused": locator_overview["summary"]["unused"],
        "duplicates": locator_overview["summary"]["duplicates"],
    }

    return render_template(
        "ui_automation/locators.html",
        locators=locator_rows,
        keyword=keyword,
        selected_page_name=page_name,
        selected_locator_type=locator_type,
        selected_status=status,
        selected_stable=stable,
        selected_project_id=selected_project_id,
        page_names=page_names,
        stats=stats,
        locator_overview=locator_overview,
    )


@ui_automation_bp.route("/locators/export")
@require_permission("uiauto:locator:view")
def export_locators():
    try:
        selected_project_id = resolve_project_id()
        accessible_ids = accessible_project_ids()
        if selected_project_id and selected_project_id in accessible_ids:
            export_items = UiAutomationService.export_locators(project_id=selected_project_id)
            project = db.session.get(Project, selected_project_id)
            file_prefix = project.name if project else f"project_{selected_project_id}"
            scope_label = project.name if project else "当前项目"
        else:
            export_items = UiAutomationService.export_locators(project_ids=accessible_ids)
            file_prefix = "ui_locators"
            scope_label = "全部可访问项目"

        payload = {
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "project_scope": scope_label,
            "count": len(export_items),
            "items": export_items,
        }
        content = json.dumps(payload, ensure_ascii=False, indent=2)
        buffer = BytesIO(content.encode("utf-8"))
        buffer.seek(0)
        download_name = f"{file_prefix}_locators.json".replace(" ", "_")
        return send_file(
            buffer,
            mimetype="application/json",
            as_attachment=True,
            download_name=download_name,
        )
    except ServiceError as exc:
        return handle_page_error(str(exc), "ui_auto.locators_page")


@ui_automation_bp.route("/locators/batch-import", methods=["POST"])
@require_permission("uiauto:locator:manage")
def batch_import_locators():
    try:
        current_user = get_current_user()
        project_id = int(request.form.get("project_id") or 0)
        if project_id not in accessible_project_ids():
            raise ServiceError("你没有访问该项目的权限。")
        items = _parse_batch_items(request.form.get("batch_locators_json", ""), "批量导入定位器 JSON")
        result = UiAutomationService.batch_import_locators(
            project_id=project_id,
            items=items,
            created_by=current_user.id if current_user else None,
        )
        created_count = len(result["created_locators"])
        error_count = len(result["errors"])
        if created_count and error_count:
            flash(f"批量导入完成：成功 {created_count} 条，失败 {error_count} 条。", "warning")
            for message in result["errors"][:5]:
                flash(message, "warning")
        elif created_count:
            flash(f"批量导入成功，共 {created_count} 条。", "success")
        else:
            raise ServiceError("批量导入失败：" + ("；".join(result["errors"][:3]) if result["errors"] else "没有可导入的定位器。"))
        return redirect(url_for("ui_auto.locators_page", project_id=project_id))
    except (ServiceError, TypeError, ValueError) as exc:
        return handle_page_error(str(exc), "ui_auto.locators_page")


@ui_automation_bp.route("/locators/batch-action", methods=["POST"])
@require_permission("uiauto:locator:manage")
def batch_action_locators():
    try:
        current_user = get_current_user()
        project_id = request.form.get("project_id") or resolve_project_id()
        action = request.form.get("bulk_action", "")
        locator_ids = []
        for value in request.form.getlist("locator_ids"):
            locator = _get_accessible_locator(value)
            locator_ids.append(locator.id)

        result = UiAutomationService.bulk_update_locators(
            locator_ids=locator_ids,
            action=action,
            updated_by=current_user.id if current_user else None,
        )
        if action == "delete":
            flash(f"批量删除成功，共 {result['deleted_count']} 条。", "success")
        elif action in {"activate", "deprecate"}:
            flash(f"批量更新状态成功，共 {result['updated_count']} 条。", "success")
        else:
            flash(f"批量更新稳定性成功，共 {result['updated_count']} 条。", "success")
        return redirect(url_for("ui_auto.locators_page", project_id=project_id or ""))
    except (ServiceError, TypeError, ValueError) as exc:
        return handle_page_error(str(exc), "ui_auto.locators_page")


@ui_automation_bp.route("/locators/create", methods=["POST"])
@require_permission("uiauto:locator:manage")
def create_locator():
    try:
        current_user = get_current_user()
        project_id = int(request.form.get("project_id") or 0)
        if project_id not in accessible_project_ids():
            raise ServiceError("你没有访问该项目的权限。")
        UiAutomationService.create_locator(
            project_id=project_id,
            locator_name=request.form.get("locator_name"),
            locator_code=request.form.get("locator_code"),
            locator_type=request.form.get("locator_type", "role"),
            locator_value=request.form.get("locator_value"),
            page_name=request.form.get("page_name", ""),
            page_url_pattern=request.form.get("page_url_pattern", ""),
            description=request.form.get("description", ""),
            usage_scene=request.form.get("usage_scene", ""),
            is_stable=request.form.get("is_stable") == "1",
            status=request.form.get("status", "active"),
            created_by=current_user.id if current_user else None,
        )
        return handle_success("定位器创建成功。", "ui_auto.locators_page")
    except (ServiceError, TypeError, ValueError) as exc:
        return handle_page_error(str(exc), "ui_auto.locators_page")


@ui_automation_bp.route("/locators/<int:locator_id>/edit", methods=["POST"])
@require_permission("uiauto:locator:manage")
def edit_locator(locator_id):
    try:
        locator = _get_accessible_locator(locator_id)
        current_user = get_current_user()
        UiAutomationService.update_locator(
            locator_id=locator.id,
            locator_name=request.form.get("locator_name"),
            locator_code=request.form.get("locator_code"),
            locator_type=request.form.get("locator_type", "role"),
            locator_value=request.form.get("locator_value"),
            page_name=request.form.get("page_name", ""),
            page_url_pattern=request.form.get("page_url_pattern", ""),
            description=request.form.get("description", ""),
            usage_scene=request.form.get("usage_scene", ""),
            is_stable=request.form.get("is_stable") == "1",
            status=request.form.get("status", "active"),
            updated_by=current_user.id if current_user else None,
        )
        return handle_success("定位器更新成功。", "ui_auto.locators_page")
    except ServiceError as exc:
        return handle_page_error(str(exc), "ui_auto.locators_page")


@ui_automation_bp.route("/locators/<int:locator_id>/delete", methods=["POST"])
@require_permission("uiauto:locator:manage")
def delete_locator(locator_id):
    try:
        locator = _get_accessible_locator(locator_id)
        UiAutomationService.delete_locator(locator.id)
        flash("定位器删除成功。", "success")
        return redirect(url_for("ui_auto.locators_page"))
    except ServiceError as exc:
        return handle_page_error(str(exc), "ui_auto.locators_page")


@ui_automation_bp.route("/executions")
@require_permission("uiauto:view")
def executions_page():
    selected_project_id = resolve_project_id()
    accessible_ids = accessible_project_ids()
    if selected_project_id:
        context = UiAutomationService.get_execution_context(project_id=selected_project_id)
    elif accessible_ids:
        context = UiAutomationService.get_execution_context(project_ids=accessible_ids)
    else:
        context = {"projects": [], "scripts": [], "environments": [], "runs": []}

    runs = context["runs"]
    queue_stats = {
        "total": len(runs),
        "queued": sum(1 for run in runs if run.status == "queued"),
        "running": sum(1 for run in runs if run.status == "running"),
        "passed": sum(1 for run in runs if run.status == "passed"),
        "failed": sum(1 for run in runs if run.status == "failed"),
        "timeout": sum(1 for run in runs if run.status == "timeout"),
        "scripts": len(context["scripts"]),
        "environments": len(context["environments"]),
    }

    return render_template(
        "ui_automation/executions.html",
        selected_project_id=selected_project_id,
        projects=context["projects"],
        scripts=context["scripts"],
        environments=context["environments"],
        runs=runs,
        queue_stats=queue_stats,
    )


@ui_automation_bp.route("/executions/create", methods=["POST"])
@require_permission("uiauto:script:run")
def create_execution():
    try:
        current_user = get_current_user()
        project_id = request.form.get("project_id") or resolve_project_id()
        run = UiAutomationService.create_run(
            project_id=project_id,
            script_id=request.form.get("script_id"),
            environment_id=request.form.get("environment_id") or None,
            browser_type=request.form.get("browser_type", "chromium"),
            run_mode=request.form.get("run_mode", "manual"),
            max_retry=request.form.get("max_retry", 0),
            trigger_source=request.form.get("trigger_source", "ui"),
            trigger_user_id=current_user.id if current_user else None,
        )
        flash(f"执行计划已提交，当前状态：{run.status}。", "success")
        return redirect(url_for("ui_auto.executions_page", project_id=project_id))
    except ServiceError as exc:
        return handle_page_error(str(exc), "ui_auto.executions_page")


def _get_accessible_run(run_id):
    run = UiAutomationWorker.get_run(run_id)
    if run.project_id not in accessible_project_ids():
        raise ServiceError("你没有访问该执行记录的权限。")
    return run


@ui_automation_bp.route("/executions/<int:run_id>/execute", methods=["POST"])
@require_permission("uiauto:script:run")
def execute_run(run_id):
    try:
        run = _get_accessible_run(run_id)
        UiAutomationWorker.execute_run(run.id)
        if run.status == "passed":
            flash("UI 自动化脚本执行通过。", "success")
        else:
            flash(f"UI 自动化脚本执行结束，状态：{run.status}。", "warning")
        return redirect(url_for("ui_auto.executions_page", project_id=run.project_id))
    except ServiceError as exc:
        return handle_page_error(str(exc), "ui_auto.executions_page")


@ui_automation_bp.route(
    "/executions/<int:run_id>/artifacts/<int:artifact_id>/download"
)
@require_permission("uiauto:view")
def download_artifact(run_id, artifact_id):
    try:
        run = _get_accessible_run(run_id)
        artifact = db.session.get(UiAutomationArtifact, artifact_id)
        if not artifact or artifact.run_id != run.id:
            raise ServiceError("执行产物不存在。")
        path = UiAutomationWorker.resolve_artifact_path(artifact)
        return send_file(
            path,
            mimetype=artifact.mime_type or None,
            as_attachment=True,
            download_name=artifact.file_name,
        )
    except ServiceError as exc:
        return handle_page_error(str(exc), "ui_auto.executions_page")


@ui_automation_bp.route("/replays")
@require_permission("uiauto:view")
def replays_page():
    keyword = (request.args.get("keyword") or "").strip()
    status = (request.args.get("status") or "").strip().lower()
    browser_type = (request.args.get("browser_type") or "").strip().lower()
    selected_project_id = resolve_project_id()
    accessible_ids = accessible_project_ids()

    if selected_project_id and selected_project_id in accessible_ids:
        runs = UiAutomationService.list_runs(project_id=selected_project_id)
    elif accessible_ids:
        runs = UiAutomationService.list_runs(project_ids=accessible_ids)
    else:
        runs = []

    if keyword:
        lowered = keyword.lower()
        runs = [
            run
            for run in runs
            if lowered in str(run.id).lower()
            or lowered in (run.script.name if run.script else "").lower()
            or lowered in (run.script.code if run.script else "").lower()
            or lowered in (run.summary.get("environment_name", "") if run.summary else "").lower()
            or lowered in (run.error_message or "").lower()
        ]
    if status:
        runs = [run for run in runs if run.status == status]
    if browser_type:
        runs = [run for run in runs if (run.browser_type or "").lower() == browser_type]

    active_filters = []
    if keyword:
        active_filters.append(f"关键字：{keyword}")
    if status:
        active_filters.append(f"状态：{status}")
    if browser_type:
        active_filters.append(f"浏览器：{browser_type}")

    all_runs = (
        UiAutomationService.list_runs(project_id=selected_project_id)
        if selected_project_id and selected_project_id in accessible_ids
        else UiAutomationService.list_runs(project_ids=accessible_ids)
        if accessible_ids
        else []
    )
    stats = {
        "total": len(all_runs),
        "passed": sum(1 for run in all_runs if run.status == "passed"),
        "failed": sum(1 for run in all_runs if run.status == "failed"),
        "artifacts": sum(len(UiAutomationService.list_artifacts(run.id)) for run in all_runs),
    }

    run_rows = []
    for run in runs:
        artifacts = UiAutomationService.list_artifacts(run.id)
        log_artifact = next((artifact for artifact in artifacts if artifact.artifact_type == "log"), None)
        screenshot_count = sum(1 for artifact in artifacts if artifact.artifact_type == "screenshot")
        trace_count = sum(1 for artifact in artifacts if artifact.artifact_type == "trace")
        video_count = sum(1 for artifact in artifacts if artifact.artifact_type == "video")
        report_count = sum(1 for artifact in artifacts if artifact.artifact_type == "report")
        run_rows.append(
            {
                "run": run,
                "artifact_count": len(artifacts),
                "screenshot_count": screenshot_count,
                "trace_count": trace_count,
                "video_count": video_count,
                "report_count": report_count,
                "log_artifact": log_artifact,
                "script_name": run.script.name if run.script else "",
                "script_code": run.script.code if run.script else "",
                "environment_name": run.summary.get("environment_name", ""),
                "environment_base_url": run.summary.get("environment_base_url", ""),
                "version_no": run.summary.get("script_version"),
            }
        )

    return render_template(
        "ui_automation/replays.html",
        runs=run_rows,
        keyword=keyword,
        selected_status=status,
        selected_browser_type=browser_type,
        selected_project_id=selected_project_id,
        stats=stats,
        active_filters=active_filters,
    )


@ui_automation_bp.route("/replays/<int:run_id>")
@require_permission("uiauto:view")
def replay_detail_page(run_id):
    try:
        run = _get_accessible_run(run_id)
        artifacts = UiAutomationService.list_artifacts(run.id)
        steps = UiAutomationService.list_run_steps(run.id)
        failure_analysis = UiAutomationService.analyze_run_failure(run)
        artifact_lookup = {}
        for artifact in artifacts:
            artifact_lookup[artifact.file_path] = artifact
            artifact_lookup[artifact.file_name] = artifact
        for step in steps:
            raw_meta = step.raw_log[0] if step.raw_log else {}
            screenshot_file = str(raw_meta.get("screenshot_file") or "").strip()
            screenshot_artifact = None
            if screenshot_file:
                screenshot_name = screenshot_file.replace("\\", "/").rsplit("/", 1)[-1]
                screenshot_artifact = artifact_lookup.get(screenshot_file)
                if not screenshot_artifact:
                    screenshot_artifact = artifact_lookup.get(screenshot_name)
                if not screenshot_artifact:
                    screenshot_artifact = next(
                        (
                            artifact
                            for artifact in artifacts
                            if artifact.artifact_type == "screenshot"
                            and (
                                artifact.file_path.endswith(screenshot_file)
                                or artifact.file_name == screenshot_name
                                or artifact.file_name == screenshot_file
                            )
                        ),
                        None,
                    )
            setattr(step, "screenshot_artifact", screenshot_artifact)
            setattr(
                step,
                "screenshot_preview_url",
                url_for("ui_auto.preview_replay_artifact", run_id=run.id, artifact_id=screenshot_artifact.id)
                if screenshot_artifact
                else "",
            )
            setattr(
                step,
                "screenshot_download_url",
                url_for("ui_auto.download_artifact", run_id=run.id, artifact_id=screenshot_artifact.id)
                if screenshot_artifact
                else "",
            )
        log_artifact = next((artifact for artifact in artifacts if artifact.artifact_type == "log"), None)
        log_preview = ""
        if log_artifact:
            try:
                log_path = UiAutomationWorker.resolve_artifact_path(log_artifact)
                log_preview = log_path.read_text(encoding="utf-8", errors="replace")[:12000]
            except ServiceError:
                log_preview = ""
        artifact_rows = []
        for artifact in artifacts:
            previewable = artifact.artifact_type in {"screenshot", "log", "report", "script", "config"}
            artifact_rows.append(
                {
                    "artifact": artifact,
                    "previewable": previewable,
                    "preview_url": url_for("ui_auto.preview_replay_artifact", run_id=run.id, artifact_id=artifact.id),
                    "download_url": url_for("ui_auto.download_artifact", run_id=run.id, artifact_id=artifact.id),
                }
            )

        return render_template(
            "ui_automation/replay_detail.html",
            run=run,
            artifacts=artifact_rows,
            steps=steps,
            log_preview=log_preview,
            log_artifact=log_artifact,
            failure_analysis=failure_analysis,
        )
    except ServiceError as exc:
        return handle_page_error(str(exc), "ui_auto.replays_page")


@ui_automation_bp.route("/replays/<int:run_id>/artifacts/<int:artifact_id>/preview")
@require_permission("uiauto:view")
def preview_replay_artifact(run_id, artifact_id):
    try:
        run = _get_accessible_run(run_id)
        artifact = db.session.get(UiAutomationArtifact, artifact_id)
        if not artifact or artifact.run_id != run.id:
            raise ServiceError("鎵ц浜х墿涓嶅瓨鍦ㄣ€?")
        path = UiAutomationWorker.resolve_artifact_path(artifact)
        return send_file(
            path,
            mimetype=artifact.mime_type or None,
            as_attachment=False,
            download_name=artifact.file_name,
        )
    except ServiceError as exc:
        return handle_page_error(str(exc), "ui_auto.replays_page")
