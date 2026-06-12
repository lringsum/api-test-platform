from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.routes import handle_page_error
from app.services.base_service import ServiceError
from app.services.environment_service import EnvironmentService
from app.services.module_service import ModuleService
from app.services.scenario_execution_service import ScenarioExecutionService
from app.services.project_service import ProjectService
from app.services.scenario_service import ScenarioService
from app.services.testcase_service import TestCaseService
from app.project_context import resolve_project_id
from app.security import accessible_project_ids, accessible_projects, require_permission

scenario_bp = Blueprint("scenario", __name__, url_prefix="/scenarios")


@scenario_bp.route("/")
@require_permission("scenario:view")
def list_scenarios():
    project_id = resolve_project_id()
    module_id = request.args.get("module_id", type=int)
    status = request.args.get("status", "").strip()
    keyword = request.args.get("keyword", "").strip()

    scenarios = ScenarioService.list_all(
        project_id=project_id,
        module_id=module_id,
        status=status or None,
        keyword=keyword or None,
    )
    projects = accessible_projects()
    modules = ModuleService.list_all(project_id=project_id) if project_id else []
    project_ids = accessible_project_ids()
    all_modules = [module for module in ModuleService.list_all() if module.project_id in project_ids] if project_ids else []
    all_environments = [env for env in EnvironmentService.list_all() if env.project_id in project_ids] if project_ids else []

    return render_template(
        "scenarios/list.html",
        scenarios=scenarios,
        projects=projects,
        modules=modules,
        all_modules=all_modules,
        all_environments=all_environments,
        selected_project_id=project_id,
        selected_module_id=module_id,
        selected_status=status,
        keyword=keyword,
    )


@scenario_bp.route("/create", methods=["POST"])
@require_permission("scenario:create")
def create_scenario():
    try:
        scenario = ScenarioService.create(
            project_id=request.form.get("project_id", type=int),
            module_id=request.form.get("module_id", type=int),
            name=request.form.get("name"),
            description=request.form.get("description", ""),
            status=request.form.get("status", "active"),
            tags_text=request.form.get("tags_text", ""),
        )
        flash("场景创建成功。", "success")
        return redirect(url_for("scenario.edit_scenario_page", scenario_id=scenario.id))
    except ServiceError as exc:
        return handle_page_error(str(exc), "scenario.list_scenarios")


@scenario_bp.route("/<int:scenario_id>/edit")
@require_permission("scenario:edit")
def edit_scenario_page(scenario_id):
    scenario = ScenarioService.get_by_id(scenario_id)
    projects = accessible_projects()
    modules = ModuleService.list_all(project_id=scenario.project_id)
    testcases = TestCaseService.list_all(project_id=scenario.project_id)
    environments = EnvironmentService.list_all(project_id=scenario.project_id)
    return render_template(
        "scenarios/edit.html",
        scenario=scenario,
        projects=projects,
        modules=modules,
        testcases=testcases,
        environments=environments,
        tags_text=ScenarioService.format_tags(scenario.tags),
    )


@scenario_bp.route("/<int:scenario_id>/edit", methods=["POST"])
@require_permission("scenario:edit")
def edit_scenario(scenario_id):
    try:
        ScenarioService.update(
            scenario_id=scenario_id,
            module_id=request.form.get("module_id", type=int),
            name=request.form.get("name"),
            description=request.form.get("description", ""),
            status=request.form.get("status", "active"),
            tags_text=request.form.get("tags_text", ""),
        )
        flash("场景更新成功。", "success")
    except ServiceError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("scenario.edit_scenario_page", scenario_id=scenario_id))


@scenario_bp.route("/<int:scenario_id>/delete", methods=["POST"])
@require_permission("scenario:delete")
def delete_scenario(scenario_id):
    try:
        ScenarioService.delete(scenario_id)
        flash("场景删除成功。", "success")
    except ServiceError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("scenario.list_scenarios"))


@scenario_bp.route("/<int:scenario_id>/run", methods=["POST"])
@require_permission("scenario:run")
def run_scenario(scenario_id):
    try:
        execution = ScenarioExecutionService.run_scenario(
            scenario_id=scenario_id,
            environment_id=request.form.get("environment_id", type=int),
            persist_extracted_to_environment=request.form.get("persist_extracted_to_environment") == "1",
        )
        flash("场景执行完成。", "success")
        return redirect(url_for("scenario.scenario_execution_detail", scenario_execution_id=execution.id))
    except ServiceError as exc:
        flash(str(exc), "danger")
        back_to = request.form.get("back_to", "list")
        if back_to == "edit":
            return redirect(url_for("scenario.edit_scenario_page", scenario_id=scenario_id))
        return redirect(url_for("scenario.list_scenarios"))


@scenario_bp.route("/<int:scenario_id>/steps/create", methods=["POST"])
@require_permission("scenario:edit")
def create_scenario_step(scenario_id):
    try:
        ScenarioService.add_step(
            scenario_id=scenario_id,
            testcase_id=request.form.get("testcase_id", type=int),
            name=request.form.get("name", ""),
            continue_on_failure=request.form.get("continue_on_failure") == "1",
            is_enabled=request.form.get("is_enabled", "1") == "1",
            setup_variables_text=request.form.get("setup_variables_text", "{}"),
            request_overrides_text=request.form.get("request_overrides_text", "{}"),
            extract_overrides_text=request.form.get("extract_overrides_text", "{}"),
            assertion_overrides_text=request.form.get("assertion_overrides_text", "[]"),
        )
        flash("步骤新增成功。", "success")
    except ServiceError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("scenario.edit_scenario_page", scenario_id=scenario_id))


@scenario_bp.route("/steps/<int:scenario_step_id>/edit", methods=["POST"])
@require_permission("scenario:edit")
def edit_scenario_step(scenario_step_id):
    try:
        step = ScenarioService.get_step_by_id(scenario_step_id)
        ScenarioService.update_step(
            scenario_step_id=scenario_step_id,
            testcase_id=request.form.get("testcase_id", type=int),
            name=request.form.get("name", ""),
            continue_on_failure=request.form.get("continue_on_failure") == "1",
            is_enabled=request.form.get("is_enabled", "1") == "1",
            setup_variables_text=request.form.get("setup_variables_text", "{}"),
            request_overrides_text=request.form.get("request_overrides_text", "{}"),
            extract_overrides_text=request.form.get("extract_overrides_text", "{}"),
            assertion_overrides_text=request.form.get("assertion_overrides_text", "[]"),
        )
        flash("步骤更新成功。", "success")
        return redirect(url_for("scenario.edit_scenario_page", scenario_id=step.scenario_id))
    except ServiceError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("scenario.list_scenarios"))


@scenario_bp.route("/steps/<int:scenario_step_id>/delete", methods=["POST"])
@require_permission("scenario:edit")
def delete_scenario_step(scenario_step_id):
    try:
        step = ScenarioService.get_step_by_id(scenario_step_id)
        scenario_id = step.scenario_id
        ScenarioService.delete_step(scenario_step_id)
        flash("步骤删除成功。", "success")
        return redirect(url_for("scenario.edit_scenario_page", scenario_id=scenario_id))
    except ServiceError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("scenario.list_scenarios"))


@scenario_bp.route("/steps/<int:scenario_step_id>/move-up", methods=["POST"])
@require_permission("scenario:edit")
def move_scenario_step_up(scenario_step_id):
    try:
        step = ScenarioService.get_step_by_id(scenario_step_id)
        scenario_id = step.scenario_id
        ScenarioService.move_step_up(scenario_step_id)
        return redirect(url_for("scenario.edit_scenario_page", scenario_id=scenario_id))
    except ServiceError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("scenario.list_scenarios"))


@scenario_bp.route("/steps/<int:scenario_step_id>/move-down", methods=["POST"])
@require_permission("scenario:edit")
def move_scenario_step_down(scenario_step_id):
    try:
        step = ScenarioService.get_step_by_id(scenario_step_id)
        scenario_id = step.scenario_id
        ScenarioService.move_step_down(scenario_step_id)
        return redirect(url_for("scenario.edit_scenario_page", scenario_id=scenario_id))
    except ServiceError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("scenario.list_scenarios"))


@scenario_bp.route("/executions/history")
@require_permission("scenario:view")
def scenario_execution_history():
    project_id = resolve_project_id()
    scenario_id = request.args.get("scenario_id", type=int)
    environment_id = request.args.get("environment_id", type=int)
    status = (request.args.get("status") or "").strip()
    page = request.args.get("page", 1, type=int)

    pagination = ScenarioExecutionService.list_all(
        project_id=project_id,
        scenario_id=scenario_id,
        environment_id=environment_id,
        status=status or None,
        page=page,
        per_page=20
    )
    projects = accessible_projects()
    scenarios = ScenarioService.list_all(project_id=project_id) if project_id else []
    environments = EnvironmentService.list_all(project_id=project_id) if project_id else []
    return render_template(
        "scenarios/history.html",
        pagination=pagination,
        projects=projects,
        scenarios=scenarios,
        environments=environments,
        selected_project_id=project_id,
        selected_scenario_id=scenario_id,
        selected_environment_id=environment_id,
        selected_status=status,
    )


@scenario_bp.route("/executions/<int:scenario_execution_id>")
@require_permission("scenario:view")
def scenario_execution_detail(scenario_execution_id):
    execution = ScenarioExecutionService.get_execution_by_id(scenario_execution_id)
    return render_template("scenarios/detail.html", execution=execution)


@scenario_bp.route("/executions/<int:scenario_execution_id>/rerun", methods=["POST"])
@require_permission("scenario:run")
def rerun_scenario_execution(scenario_execution_id):
    try:
        execution = ScenarioExecutionService.rerun(
            scenario_execution_id=scenario_execution_id,
            persist_extracted_to_environment=request.form.get("persist_extracted_to_environment") == "1",
        )
        flash("场景重跑完成。", "success")
        return redirect(url_for("scenario.scenario_execution_detail", scenario_execution_id=execution.id))
    except ServiceError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("scenario.scenario_execution_history"))
