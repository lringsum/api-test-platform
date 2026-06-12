from copy import deepcopy
from datetime import datetime

from app import db
from app.models import Scenario, ScenarioExecution, ScenarioExecutionDetail
from app.services.base_service import ServiceError, commit_session
from app.services.execution_service import ExecutionService
from app.services.variable_service import VariableService


class ScenarioExecutionService:
    @staticmethod
    def list_all(project_id=None, scenario_id=None, environment_id=None, status=None, page=1, per_page=20):
        query = ScenarioExecution.query.join(Scenario, ScenarioExecution.scenario_id == Scenario.id)
        if project_id:
            query = query.filter(Scenario.project_id == project_id)
        if scenario_id:
            query = query.filter(ScenarioExecution.scenario_id == scenario_id)
        if environment_id:
            query = query.filter(ScenarioExecution.environment_id == environment_id)
        if status:
            query = query.filter(ScenarioExecution.status == status)
        return query.order_by(ScenarioExecution.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

    @staticmethod
    def get_scenario_by_id(scenario_id):
        scenario = db.session.get(Scenario, scenario_id)
        if not scenario:
            raise ServiceError("场景不存在。")
        return scenario

    @staticmethod
    def get_execution_by_id(scenario_execution_id):
        execution = db.session.get(ScenarioExecution, scenario_execution_id)
        if not execution:
            raise ServiceError("场景执行记录不存在。")
        return execution

    @staticmethod
    def create_execution(scenario_id, environment_id, trigger_mode="manual"):
        scenario = ScenarioExecutionService.get_scenario_by_id(scenario_id)
        execution = ScenarioExecution(
            scenario_id=scenario.id,
            environment_id=environment_id,
            trigger_mode=trigger_mode,
            status="running",
            started_at=datetime.utcnow(),
        )
        db.session.add(execution)
        commit_session()
        return execution

    @staticmethod
    def add_detail(
        scenario_execution_id,
        scenario_step_id,
        testcase_id,
        step_name,
        testcase_name="",
        status="pending",
        request_data=None,
        response_data=None,
        extract_data=None,
        assertion_data=None,
        error_message="",
        duration_ms=0,
    ):
        execution = ScenarioExecutionService.get_execution_by_id(scenario_execution_id)
        detail = ScenarioExecutionDetail(
            scenario_execution_id=execution.id,
            scenario_step_id=scenario_step_id,
            testcase_id=testcase_id,
            step_name=step_name,
            testcase_name=testcase_name or "",
            status=status,
            error_message=error_message or "",
            duration_ms=duration_ms or 0,
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
        )
        detail.request_data = request_data or {}
        detail.response_data = response_data or {}
        detail.extract_data = extract_data or {}
        detail.assertion_data = assertion_data or []
        db.session.add(detail)
        commit_session()
        return detail

    @staticmethod
    def finish_execution(
        scenario_execution_id,
        status,
        total_steps=0,
        passed_steps=0,
        failed_steps=0,
        duration_ms=0,
        runtime_variables=None,
    ):
        execution = ScenarioExecutionService.get_execution_by_id(scenario_execution_id)
        execution.status = status
        execution.total_steps = total_steps
        execution.passed_steps = passed_steps
        execution.failed_steps = failed_steps
        execution.duration_ms = duration_ms
        execution.finished_at = datetime.utcnow()
        execution.runtime_variables = runtime_variables or {}
        commit_session()
        return execution

    @staticmethod
    def run_scenario(
        scenario_id,
        environment_id,
        trigger_mode="manual",
        persist_extracted_to_environment=False,
        runtime_injections=None,
    ):
        scenario = ScenarioExecutionService.get_scenario_by_id(scenario_id)
        if scenario.status != "active":
            raise ServiceError("当前场景已停用，无法执行。")

        enabled_steps = [item for item in scenario.steps if item.is_enabled]
        if not enabled_steps:
            raise ServiceError("当前场景没有可执行的启用步骤。")

        environment = ExecutionService.get_active_environment(
            project_id=scenario.project_id,
            environment_id=environment_id,
        )
        execution = ScenarioExecutionService.create_execution(
            scenario_id=scenario.id,
            environment_id=environment.id,
            trigger_mode=trigger_mode,
        )

        runtime_variables = VariableService.build_runtime_variables(
            project_id=scenario.project_id,
            environment_id=environment.id,
        )
        runtime_variables.update(runtime_injections or {})

        passed_steps = 0
        failed_steps = 0
        total_duration_ms = 0

        for step in enabled_steps:
            runtime_variables.update(step.setup_variables)
            step_runtime_variables = deepcopy(runtime_variables)

            step_name = step.name or (
                step.testcase.name if step.testcase else f"步骤{step.order_no}"
            )
            testcase_name = step.testcase.name if step.testcase else ""

            if not step.testcase:
                failed_steps += 1
                ScenarioExecutionService.add_detail(
                    scenario_execution_id=execution.id,
                    scenario_step_id=step.id,
                    testcase_id=None,
                    step_name=step_name,
                    testcase_name=testcase_name,
                    status="failed",
                    error_message="步骤未关联可用用例。",
                )
                if not step.continue_on_failure:
                    break
                continue

            if not step.testcase.is_active:
                failed_steps += 1
                ScenarioExecutionService.add_detail(
                    scenario_execution_id=execution.id,
                    scenario_step_id=step.id,
                    testcase_id=step.testcase.id,
                    step_name=step_name,
                    testcase_name=testcase_name,
                    status="failed",
                    error_message="关联用例已停用，无法执行。",
                )
                if not step.continue_on_failure:
                    break
                continue

            merged_case_data = ExecutionService.merge_case_data(
                base_case_data=step.testcase.data,
                request_overrides=step.request_overrides,
                extract_overrides=step.extract_overrides,
                assertion_overrides=ScenarioExecutionService._resolve_assertion_overrides(step),
            )

            case_result = ExecutionService.execute_case(
                testcase=step.testcase,
                environment=environment,
                runtime_variables=step_runtime_variables,
                testcase_data=merged_case_data,
            )

            ScenarioExecutionService.add_detail(
                scenario_execution_id=execution.id,
                scenario_step_id=step.id,
                testcase_id=step.testcase.id,
                step_name=step_name,
                testcase_name=testcase_name,
                status=case_result["status"],
                request_data=case_result["request_snapshot"],
                response_data=case_result["response_snapshot"],
                extract_data=case_result["extract_results"],
                assertion_data=case_result["assertion_results"],
                error_message=case_result["error_message"],
                duration_ms=case_result["duration_ms"],
            )

            total_duration_ms += case_result["duration_ms"]
            if case_result["status"] == "passed":
                passed_steps += 1
            else:
                failed_steps += 1

            if case_result["extracted_values"]:
                ExecutionService.apply_extracted_values(
                    project_id=scenario.project_id,
                    environment_id=environment.id,
                    runtime_variables=runtime_variables,
                    extracted_values=case_result["extracted_values"],
                    persist_to_environment=persist_extracted_to_environment,
                )

            if case_result["status"] != "passed" and not step.continue_on_failure:
                break

        final_status = ScenarioExecutionService._resolve_final_status(
            passed_steps=passed_steps,
            failed_steps=failed_steps,
        )
        ScenarioExecutionService.finish_execution(
            scenario_execution_id=execution.id,
            status=final_status,
            total_steps=len(enabled_steps),
            passed_steps=passed_steps,
            failed_steps=failed_steps,
            duration_ms=total_duration_ms,
            runtime_variables=runtime_variables,
        )
        return ScenarioExecutionService.get_execution_by_id(execution.id)

    @staticmethod
    def rerun(scenario_execution_id, persist_extracted_to_environment=False):
        execution = ScenarioExecutionService.get_execution_by_id(scenario_execution_id)
        return ScenarioExecutionService.run_scenario(
            scenario_id=execution.scenario_id,
            environment_id=execution.environment_id,
            trigger_mode="manual",
            persist_extracted_to_environment=persist_extracted_to_environment,
        )

    @staticmethod
    def _resolve_assertion_overrides(step):
        raw_text = str(step.assertion_overrides_json or "").strip()
        if raw_text in ("", "[]"):
            return None
        return step.assertion_overrides

    @staticmethod
    def _resolve_final_status(passed_steps, failed_steps):
        if failed_steps == 0:
            return "passed"
        if passed_steps > 0:
            return "partial_success"
        return "failed"
