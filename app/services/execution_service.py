import time
from copy import deepcopy
from datetime import datetime

import mimetypes
import os
import requests
from flask import current_app

from app import db
from app.models import Environment, Execution, ExecutionDetail, Module, Project, TestCase
from app.services.base_service import ServiceError, commit_session
from app.services.pre_script_service import PreScriptService
from app.services.variable_service import VariableService
from app.utils.assertion_engine import run_assertions
from app.utils.extractor import extract_variables
from app.utils.helpers import safe_response_json, truncate_text
from app.utils.request_builder import build_request_data
from app.utils.trigger import normalize_trigger_type


class ExecutionService:

    @staticmethod
    def _looks_like_garbled_text(text):
        value = str(text or "")
        if not value:
            return False
        return ("�" in value) or ("??" in value)

    @staticmethod
    def list_all(project_id=None, page=1, per_page=20):
        query = Execution.query
        if project_id:
            query = query.filter_by(project_id=project_id)
        return query.order_by(Execution.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

    @staticmethod
    def get_by_id(execution_id):
        execution = db.session.get(Execution, execution_id)
        if not execution:
            raise ServiceError("执行记录不存在。")
        return execution

    @staticmethod
    def create_execution(
        project_id,
        environment_id,
        execution_type,
        target_type,
        target_id,
        trigger_type="automatic",
        trigger_user_id=None,
    ):
        project = db.session.get(Project, project_id)
        if not project:
            raise ServiceError("所属项目不存在。")

        environment = None
        if environment_id:
            environment = db.session.get(Environment, environment_id)
            if not environment or environment.project_id != project_id:
                raise ServiceError("环境不存在或与项目不匹配。")

        execution = Execution(
            project_id=project_id,
            environment_id=environment.id if environment else None,
            execution_type=execution_type,
            target_type=target_type,
            target_id=target_id,
            trigger_type=normalize_trigger_type(trigger_type),
            trigger_user_id=trigger_user_id,
            status="running",
            started_at=datetime.utcnow(),
        )
        db.session.add(execution)
        commit_session()
        return execution

    @staticmethod
    def get_active_environment(project_id, environment_id):
        environment = db.session.get(Environment, environment_id)
        if not environment or environment.project_id != project_id:
            raise ServiceError("环境不存在或与项目不匹配。")
        if not environment.is_active:
            raise ServiceError("当前环境已停用，无法执行。")
        if not environment.base_url:
            raise ServiceError("当前环境未配置 base_url。")
        return environment

    @staticmethod
    def execute_case(testcase, environment, runtime_variables, testcase_data=None):
        return ExecutionService._execute_one_case(
            testcase=testcase,
            environment=environment,
            runtime_variables=runtime_variables,
            testcase_data=testcase_data,
        )

    @staticmethod
    def apply_extracted_values(
        project_id,
        environment_id,
        runtime_variables,
        extracted_values,
        persist_to_environment=True,
    ):
        if not extracted_values:
            return runtime_variables

        runtime_variables.update(extracted_values)
        if persist_to_environment:
            VariableService.upsert_environment_variables(
                project_id=project_id,
                environment_id=environment_id,
                extracted_values=extracted_values,
            )
        return runtime_variables

    @staticmethod
    def merge_case_data(base_case_data, request_overrides=None, extract_overrides=None, assertion_overrides=None):
        merged_case_data = deepcopy(base_case_data or {})

        if request_overrides:
            merged_case_data = ExecutionService._deep_merge_dict(merged_case_data, request_overrides)

        if extract_overrides:
            merged_extract = deepcopy(merged_case_data.get("extract", {}))
            merged_extract.update(extract_overrides)
            merged_case_data["extract"] = merged_extract

        if assertion_overrides is not None:
            merged_case_data["assertions"] = assertion_overrides

        return merged_case_data

    @staticmethod
    def _deep_merge_dict(base_data, override_data):
        result = deepcopy(base_data or {})
        for key, value in (override_data or {}).items():
            if (
                isinstance(result.get(key), dict)
                and isinstance(value, dict)
            ):
                result[key] = ExecutionService._deep_merge_dict(result[key], value)
            else:
                result[key] = deepcopy(value)
        return result

    @staticmethod
    def add_detail(
        execution_id,
        testcase_id,
        testcase_name,
        status="pending",
        request_data=None,
        response_data=None,
        assertion_data=None,
        extract_data=None,
        error_message="",
        duration_ms=0,
    ):
        execution = ExecutionService.get_by_id(execution_id)

        if testcase_id:
            testcase = db.session.get(TestCase, testcase_id)
            if not testcase:
                raise ServiceError("关联用例不存在。")
            if ExecutionService._looks_like_garbled_text(testcase_name):
                testcase_name = testcase.name

        detail = ExecutionDetail(
            execution_id=execution.id,
            testcase_id=testcase_id,
            testcase_name=testcase_name,
            status=status,
            error_message=error_message or "",
            duration_ms=duration_ms or 0,
        )
        detail.request_data = request_data or {}
        detail.response_data = response_data or {}
        detail.assertion_data = assertion_data or []
        detail.extract_data = extract_data or {}

        db.session.add(detail)
        commit_session()
        return detail

    @staticmethod
    def finish_execution(execution_id, status, total_count=0, passed_count=0, failed_count=0, total_duration_ms=0, summary=None):
        execution = ExecutionService.get_by_id(execution_id)

        execution.status = status
        execution.total_count = total_count
        execution.passed_count = passed_count
        execution.failed_count = failed_count
        execution.total_duration_ms = total_duration_ms
        execution.pass_rate = 0.0 if total_count == 0 else round((passed_count / total_count) * 100, 2)
        execution.finished_at = datetime.utcnow()
        execution.summary = summary or {}

        commit_session()
        return execution

    @staticmethod
    def run_testcase(
        testcase_id,
        environment_id,
        trigger_type="automatic",
        trigger_user_id=None,
    ):
        testcase = db.session.get(TestCase, testcase_id)
        if not testcase:
            raise ServiceError("用例不存在。")
        if not testcase.is_active:
            raise ServiceError("当前用例已停用，无法执行。")

        environment = ExecutionService.get_active_environment(
            project_id=testcase.project_id,
            environment_id=environment_id,
        )

        execution = ExecutionService.create_execution(
            project_id=testcase.project_id,
            environment_id=environment.id,
            execution_type="single",
            target_type="testcase",
            target_id=testcase.id,
            trigger_type=trigger_type,
            trigger_user_id=trigger_user_id,
        )

        runtime_variables = VariableService.build_runtime_variables(
            project_id=testcase.project_id,
            environment_id=environment.id,
        )

        case_result = ExecutionService.execute_case(
            testcase=testcase,
            environment=environment,
            runtime_variables=runtime_variables,
        )

        ExecutionService.add_detail(
            execution_id=execution.id,
            testcase_id=testcase.id,
            testcase_name=testcase.name,
            status=case_result["status"],
            request_data=case_result["request_snapshot"],
            response_data=case_result["response_snapshot"],
            assertion_data=case_result["assertion_results"],
            extract_data=case_result["extract_results"],
            error_message=case_result["error_message"],
            duration_ms=case_result["duration_ms"],
        )

        if case_result["extracted_values"]:
            ExecutionService.apply_extracted_values(
                project_id=testcase.project_id,
                environment_id=environment.id,
                runtime_variables=runtime_variables,
                extracted_values=case_result["extracted_values"],
                persist_to_environment=True,
            )

        passed_count = 1 if case_result["status"] == "passed" else 0
        failed_count = 1 - passed_count

        summary = {
            "environment_name": environment.name,
            "environment_base_url": environment.base_url,
            "runtime_variables": runtime_variables,
            "last_extracted_values": case_result["extracted_values"],
            "trigger_type": execution.trigger_type,
            "trigger_person": execution.trigger_person_name,
        }

        ExecutionService.finish_execution(
            execution_id=execution.id,
            status="passed" if passed_count == 1 else "failed",
            total_count=1,
            passed_count=passed_count,
            failed_count=failed_count,
            total_duration_ms=case_result["duration_ms"],
            summary=summary,
        )
        from app.services.report_service import ReportService

        ReportService.generate(execution.id)
        return ExecutionService.get_by_id(execution.id)

    @staticmethod
    def run_module(
        module_id,
        environment_id,
        trigger_type="automatic",
        trigger_user_id=None,
    ):
        module = db.session.get(Module, module_id)
        if not module:
            raise ServiceError("模块不存在。")

        testcases = (
            TestCase.query.filter_by(module_id=module.id, is_active=True)
            .order_by(TestCase.id.asc())
            .all()
        )
        if not testcases:
            raise ServiceError("当前模块下没有可执行的启用用例。")

        return ExecutionService._run_batch(
            project_id=module.project_id,
            environment_id=environment_id,
            testcases=testcases,
            execution_type="batch",
            target_type="module",
            target_id=module.id,
            trigger_type=trigger_type,
            trigger_user_id=trigger_user_id,
        )

    @staticmethod
    def run_selected_testcases(
        testcase_ids,
        environment_id,
        trigger_type="automatic",
        trigger_user_id=None,
    ):
        normalized_ids = []
        for testcase_id in testcase_ids or []:
            try:
                normalized_id = int(testcase_id)
            except (TypeError, ValueError):
                continue
            if normalized_id > 0 and normalized_id not in normalized_ids:
                normalized_ids.append(normalized_id)

        if not normalized_ids:
            raise ServiceError("请至少选择一条有效用例。")

        testcases = (
            TestCase.query.filter(
                TestCase.id.in_(normalized_ids),
                TestCase.is_active.is_(True),
            )
            .order_by(TestCase.id.asc())
            .all()
        )
        if not testcases:
            raise ServiceError("未找到可执行的启用用例。")

        testcase_map = {item.id: item for item in testcases}
        missing_ids = [item_id for item_id in normalized_ids if item_id not in testcase_map]
        if missing_ids:
            raise ServiceError(f"部分用例不存在或已停用：{missing_ids}")

        project_ids = {item.project_id for item in testcases}
        if len(project_ids) != 1:
            raise ServiceError("选中的用例必须属于同一个项目。")

        ordered_testcases = [testcase_map[item_id] for item_id in normalized_ids]
        summary_extra = {
            "selected_testcase_ids": normalized_ids,
            "selected_testcase_names": [item.name for item in ordered_testcases],
            "selected_count": len(ordered_testcases),
        }

        return ExecutionService._run_batch(
            project_id=ordered_testcases[0].project_id,
            environment_id=environment_id,
            testcases=ordered_testcases,
            execution_type="batch",
            target_type="selection",
            target_id=0,
            summary_extra=summary_extra,
            trigger_type=trigger_type,
            trigger_user_id=trigger_user_id,
        )

    @staticmethod
    def run_project(
        project_id,
        environment_id,
        trigger_type="automatic",
        trigger_user_id=None,
    ):
        project = db.session.get(Project, project_id)
        if not project:
            raise ServiceError("项目不存在。")

        testcases = (
            TestCase.query.filter_by(project_id=project.id, is_active=True)
            .order_by(TestCase.id.asc())
            .all()
        )
        if not testcases:
            raise ServiceError("当前项目下没有可执行的启用用例。")

        return ExecutionService._run_batch(
            project_id=project.id,
            environment_id=environment_id,
            testcases=testcases,
            execution_type="batch",
            target_type="project",
            target_id=project.id,
            trigger_type=trigger_type,
            trigger_user_id=trigger_user_id,
        )

    @staticmethod
    def _run_batch(
        project_id,
        environment_id,
        testcases,
        execution_type,
        target_type,
        target_id,
        summary_extra=None,
        trigger_type="automatic",
        trigger_user_id=None,
    ):
        environment = ExecutionService.get_active_environment(
            project_id=project_id,
            environment_id=environment_id,
        )

        execution = ExecutionService.create_execution(
            project_id=project_id,
            environment_id=environment.id,
            execution_type=execution_type,
            target_type=target_type,
            target_id=target_id,
            trigger_type=trigger_type,
            trigger_user_id=trigger_user_id,
        )

        runtime_variables = VariableService.build_runtime_variables(
            project_id=project_id,
            environment_id=environment.id,
        )

        passed_count = 0
        failed_count = 0
        total_duration_ms = 0
        failed_cases = []

        for testcase in testcases:
            case_result = ExecutionService.execute_case(
                testcase=testcase,
                environment=environment,
                runtime_variables=runtime_variables,
            )

            ExecutionService.add_detail(
                execution_id=execution.id,
                testcase_id=testcase.id,
                testcase_name=testcase.name,
                status=case_result["status"],
                request_data=case_result["request_snapshot"],
                response_data=case_result["response_snapshot"],
                assertion_data=case_result["assertion_results"],
                extract_data=case_result["extract_results"],
                error_message=case_result["error_message"],
                duration_ms=case_result["duration_ms"],
            )

            total_duration_ms += case_result["duration_ms"]

            if case_result["status"] == "passed":
                passed_count += 1
            else:
                failed_count += 1
                failed_cases.append(testcase.name)

            if case_result["extracted_values"]:
                ExecutionService.apply_extracted_values(
                    project_id=project_id,
                    environment_id=environment.id,
                    runtime_variables=runtime_variables,
                    extracted_values=case_result["extracted_values"],
                    persist_to_environment=True,
                )

        final_status = "passed" if failed_count == 0 else "failed"
        summary = {
            "environment_name": environment.name,
            "environment_base_url": environment.base_url,
            "runtime_variables": runtime_variables,
            "failed_cases": failed_cases,
            "trigger_type": execution.trigger_type,
            "trigger_person": execution.trigger_person_name,
        }
        if summary_extra:
            summary.update(summary_extra)

        ExecutionService.finish_execution(
            execution_id=execution.id,
            status=final_status,
            total_count=len(testcases),
            passed_count=passed_count,
            failed_count=failed_count,
            total_duration_ms=total_duration_ms,
            summary=summary,
        )
        from app.services.report_service import ReportService

        ReportService.generate(execution.id)
        return ExecutionService.get_by_id(execution.id)

    @staticmethod
    def _execute_one_case(testcase, environment, runtime_variables, testcase_data=None):
        timeout = current_app.config.get("DEFAULT_TIMEOUT", 10)
        testcase_data = testcase_data or testcase.data
        request_snapshot = {}
        response_snapshot = {
            "status_code": None,
            "headers": {},
            "text": "",
            "json": None,
        }
        assertion_results = []
        extract_results = {}
        extracted_values = {}
        error_message = ""
        status = "failed"
        duration_ms = 0
        opened_files = []

        try:
            request_snapshot = build_request_data(
                testcase_data=testcase_data,
                environment=environment,
                runtime_variables=runtime_variables,
                timeout=timeout,
            )
            try:
                request_snapshot = ExecutionService._apply_pre_script(
                    testcase=testcase,
                    environment=environment,
                    runtime_variables=runtime_variables,
                    testcase_data=testcase_data,
                    request_snapshot=request_snapshot,
                )
            except ServiceError as exc:
                request_snapshot["pre_script"] = {
                    "enabled": True,
                    "status": "failed",
                    "error": str(exc),
                }
                raise

            request_kwargs = {
                "method": request_snapshot["method"],
                "url": request_snapshot["url"],
                "headers": dict(request_snapshot["headers"]),
                "params": request_snapshot["params"],
                "timeout": timeout,
            }

            body_type = request_snapshot.get("body_type", "json")
            if body_type == "json":
                request_kwargs["json"] = request_snapshot["body"]
            elif body_type == "form":
                request_kwargs["data"] = request_snapshot["body"]
            elif body_type == "multipart":
                request_kwargs["data"] = request_snapshot["body"]
                multipart_files = {}
                for field_name, file_path in (request_snapshot.get("files") or {}).items():
                    file_path = str(file_path or "").strip()
                    if not file_path:
                        continue
                    if not os.path.exists(file_path):
                        raise ServiceError(f"上传文件不存在：{file_path}")
                    mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
                    file_handle = open(file_path, "rb")
                    opened_files.append(file_handle)
                    multipart_files[field_name] = (os.path.basename(file_path), file_handle, mime_type)
                request_kwargs["files"] = multipart_files
                request_kwargs["headers"] = {
                    key: value
                    for key, value in request_kwargs["headers"].items()
                    if key.lower() != "content-type"
                }
            else:
                request_kwargs["json"] = request_snapshot["body"]

            start_time = time.perf_counter()
            response = requests.request(**request_kwargs)
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            response_json = safe_response_json(response)
            response_snapshot = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "text": truncate_text(response.text, 5000),
                "json": response_json,
            }

            extracted_values, extract_results = extract_variables(
                extract_rules=testcase_data.get("extract", {}),
                response_json=response_json,
            )

            assertion_variables = dict(runtime_variables)
            assertion_variables.update(extracted_values)
            passed, assertion_results = run_assertions(
                assertions=testcase_data.get("assertions", []),
                response_snapshot=response_snapshot,
                duration_ms=duration_ms,
                runtime_variables=assertion_variables,
            )

            status = "passed" if passed else "failed"

        except requests.RequestException as exc:
            error_message = f"请求异常：{exc}"
            status = "failed"
        except ServiceError as exc:
            error_message = str(exc)
            status = "failed"
        except Exception as exc:
            error_message = f"执行异常：{exc}"
            status = "failed"
        finally:
            for file_handle in opened_files:
                try:
                    file_handle.close()
                except Exception:
                    pass

        return {
            "status": status,
            "request_snapshot": request_snapshot,
            "response_snapshot": response_snapshot,
            "assertion_results": assertion_results,
            "extract_results": extract_results,
            "extracted_values": extracted_values,
            "error_message": error_message,
            "duration_ms": duration_ms,
        }

    @staticmethod
    def _apply_pre_script(testcase, environment, runtime_variables, testcase_data, request_snapshot):
        script_config = PreScriptService.get_normalized_config(testcase_data)
        if not script_config.get("enabled"):
            request_snapshot["pre_script"] = {
                "enabled": False,
                "status": "skipped",
            }
            return request_snapshot

        project_variables = VariableService.build_project_variables(testcase.project_id)
        environment_variables = VariableService.build_environment_variables(
            project_id=testcase.project_id,
            environment_id=environment.id,
        )
        script_result = PreScriptService.execute_script(
            script_config=script_config,
            context={
                "env": environment_variables,
                "project_vars": project_variables,
                "runtime_vars": runtime_variables,
                "headers": request_snapshot.get("headers", {}),
                "params": request_snapshot.get("params", {}),
                "body": request_snapshot.get("body", {}),
            },
        )

        runtime_before = deepcopy(runtime_variables)
        runtime_variables.update(script_result.get("runtime_vars", {}))
        runtime_updates = {
            key: value
            for key, value in script_result.get("runtime_vars", {}).items()
            if runtime_before.get(key) != value
        }

        request_snapshot["headers"] = script_result.get("headers", {})
        request_snapshot["params"] = script_result.get("params", {})
        request_snapshot["body"] = script_result.get("body", {})
        request_snapshot["pre_script"] = {
            "enabled": True,
            "status": "passed",
            "runtime_updates": runtime_updates,
        }
        return request_snapshot





