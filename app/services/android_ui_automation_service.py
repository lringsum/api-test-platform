from datetime import datetime

from app import db
from app.models import (
    ANDROID_UI_RUN_STAGE_APK_PARSE,
    ANDROID_UI_RUN_STAGE_DOWNLOAD,
    ANDROID_UI_RUN_STAGE_FINISHED,
    ANDROID_UI_RUN_STAGE_INSTALL,
    ANDROID_UI_RUN_STAGE_LAUNCH,
    ANDROID_UI_RUN_STAGE_QUEUED,
    ANDROID_UI_RUN_STAGE_SCREENSHOT,
    ANDROID_UI_RUN_STATUS_FAILED,
    ANDROID_UI_RUN_STATUS_PASSED,
    ANDROID_UI_RUN_STATUS_PENDING,
    ANDROID_UI_RUN_STATUS_RUNNING,
    ANDROID_UI_RUN_STAGES,
    AndroidUiProjectFlow,
    AndroidUiProjectFlowStep,
    AndroidUiRunStep,
    AndroidUiRunStepArtifact,
    AndroidUiTestRun,
    AndroidUiTestTask,
)
from app.services.android_ui_flow_presets import get_android_ui_flow_presets
from app.services.base_service import ServiceError, commit_session, ensure_not_blank


class AndroidUiAutomationService:
    DEFAULT_DEVICE_SENTINEL = "__default__"
    FLOW_MODE_BASIC = "basic"
    FLOW_MODE_FULL = "full"
    FLOW_MODE_DEFAULT = "default"
    FLOW_MODE_SPECIFIED = "specified"
    FLOW_MODES = (
        FLOW_MODE_BASIC,
        FLOW_MODE_FULL,
        FLOW_MODE_DEFAULT,
        FLOW_MODE_SPECIFIED,
    )
    SUPPORTED_STEP_TYPES = (
        "wait_text",
        "tap_text",
        "tap_left_of_text",
        "tap_bounds",
        "input_text",
        "keyevent",
        "sleep",
        "assert_exists",
        "assert_not_exists",
        "screenshot",
        "tap_image",
        "open_xianyu_user_center",
        "ensure_xianyu_account_login",
        "wait_image",
        "assert_image_exists",
        "assert_image_not_exists",
    )
    SUPPORTED_SELECTOR_TYPES = (
        "none",
        "text",
        "resource_id",
        "xpath",
        "bounds",
        "activity",
        "image",
    )

    @staticmethod
    def list_tasks(project_id=None, keyword="", is_active=None):
        query = AndroidUiTestTask.query
        if project_id:
            query = query.filter_by(project_id=project_id)
        tasks = query.order_by(AndroidUiTestTask.updated_at.desc()).all()

        normalized_keyword = str(keyword or "").strip().lower()
        if normalized_keyword:
            tasks = [
                item
                for item in tasks
                if normalized_keyword in item.name.lower()
                or normalized_keyword in item.package_key.lower()
                or normalized_keyword in (item.package_name or "").lower()
                or normalized_keyword in (item.apk_url or "").lower()
            ]

        if is_active is True:
            tasks = [item for item in tasks if item.is_active]
        elif is_active is False:
            tasks = [item for item in tasks if not item.is_active]

        return tasks

    @staticmethod
    def list_project_flows(project_id=None, status=""):
        query = AndroidUiProjectFlow.query
        if project_id:
            query = query.filter_by(project_id=project_id)
        flows = query.order_by(
            AndroidUiProjectFlow.project_id.asc(),
            AndroidUiProjectFlow.is_default.desc(),
            AndroidUiProjectFlow.updated_at.desc(),
        ).all()
        normalized_status = str(status or "").strip().lower()
        if normalized_status:
            flows = [item for item in flows if (item.status or "").strip().lower() == normalized_status]
        return flows

    @staticmethod
    def get_project_flow(flow_id):
        flow = db.session.get(AndroidUiProjectFlow, flow_id)
        if not flow:
            raise ServiceError("Android 项目流程不存在。")
        return flow

    @staticmethod
    def get_default_project_flow(project_id):
        if not project_id:
            return None
        return (
            AndroidUiProjectFlow.query.filter_by(
                project_id=project_id,
                is_default=True,
                status="active",
            )
            .order_by(AndroidUiProjectFlow.id.desc())
            .first()
        )

    @staticmethod
    def list_flow_steps(flow_id):
        return (
            AndroidUiProjectFlowStep.query.filter_by(flow_id=flow_id)
            .order_by(AndroidUiProjectFlowStep.sort_order.asc(), AndroidUiProjectFlowStep.id.asc())
            .all()
        )

    @staticmethod
    def get_task(task_id):
        task = db.session.get(AndroidUiTestTask, task_id)
        if not task:
            raise ServiceError("Android UI 测试任务不存在。")
        return task

    @staticmethod
    def normalize_flow_mode(flow_mode):
        normalized = str(flow_mode or "").strip().lower()
        if normalized == AndroidUiAutomationService.FLOW_MODE_BASIC:
            return AndroidUiAutomationService.FLOW_MODE_BASIC
        if normalized in (
            AndroidUiAutomationService.FLOW_MODE_FULL,
            AndroidUiAutomationService.FLOW_MODE_DEFAULT,
            AndroidUiAutomationService.FLOW_MODE_SPECIFIED,
        ):
            return AndroidUiAutomationService.FLOW_MODE_FULL
        return AndroidUiAutomationService.FLOW_MODE_BASIC

    @staticmethod
    def normalize_step_type(step_type):
        normalized = str(step_type or "").strip().lower()
        if normalized not in AndroidUiAutomationService.SUPPORTED_STEP_TYPES:
            raise ServiceError("不支持的步骤类型。")
        return normalized

    @staticmethod
    def normalize_selector_type(selector_type):
        normalized = str(selector_type or "").strip().lower() or "none"
        if normalized not in AndroidUiAutomationService.SUPPORTED_SELECTOR_TYPES:
            raise ServiceError("不支持的选择器类型。")
        return normalized

    @staticmethod
    def resolve_task_flow_binding(project_id, flow_mode="basic", flow_id=None):
        normalized_mode = AndroidUiAutomationService.normalize_flow_mode(flow_mode)
        parsed_flow_id = int(flow_id or 0) or None
        if normalized_mode == AndroidUiAutomationService.FLOW_MODE_BASIC:
            return normalized_mode, None, False
        if not parsed_flow_id:
            return normalized_mode, None, False
        flow = AndroidUiAutomationService.get_project_flow(parsed_flow_id)
        if int(flow.project_id or 0) != int(project_id or 0):
            raise ServiceError("所选流程模板不属于当前项目。")
        return normalized_mode, flow.id, True

    @staticmethod
    def resolve_task_flow(task):
        if not task:
            return None
        raw_mode = str(getattr(task, "flow_mode", "basic") or "").strip().lower()
        mode = AndroidUiAutomationService.normalize_flow_mode(raw_mode)
        if mode == AndroidUiAutomationService.FLOW_MODE_BASIC:
            return None
        if getattr(task, "flow_id", None):
            return AndroidUiAutomationService.get_project_flow(task.flow_id)
        if raw_mode in (
            AndroidUiAutomationService.FLOW_MODE_FULL,
            AndroidUiAutomationService.FLOW_MODE_DEFAULT,
            AndroidUiAutomationService.FLOW_MODE_SPECIFIED,
        ):
            return AndroidUiAutomationService.get_default_project_flow(task.project_id)
        return None

    @staticmethod
    def build_flow_snapshot(flow):
        if not flow:
            return {}
        return {
            "id": flow.id,
            "project_id": flow.project_id,
            "name": flow.name,
            "code": flow.code,
            "description": flow.description,
            "steps": [
                {
                    "id": step.id,
                    "step_no": step.step_no,
                    "step_name": step.step_name,
                    "step_type": step.step_type,
                    "selector_type": step.selector_type,
                    "selector_value": step.selector_value,
                    "input_value": step.input_value,
                    "wait_timeout_sec": step.wait_timeout_sec,
                    "retry_times": step.retry_times,
                    "continue_on_failure": step.continue_on_failure,
                    "capture_on_success": step.capture_on_success,
                    "capture_on_failure": step.capture_on_failure,
                    "remark": step.remark,
                }
                for step in AndroidUiAutomationService.list_flow_steps(flow.id)
            ],
        }

    @staticmethod
    def create_project_flow(
        project_id,
        name,
        code,
        description="",
        is_default=False,
        status="active",
        created_by=None,
    ):
        project_id = int(project_id or 0)
        if project_id <= 0:
            raise ServiceError("请选择所属项目。")
        flow = AndroidUiProjectFlow(
            project_id=project_id,
            name=ensure_not_blank(name, "流程名称"),
            code=ensure_not_blank(code, "流程编码").lower().replace(" ", "_"),
            description=str(description or "").strip(),
            is_default=bool(is_default),
            status="inactive" if str(status or "").strip().lower() == "inactive" else "active",
            created_by=created_by,
            updated_by=created_by,
        )
        exists = AndroidUiProjectFlow.query.filter_by(project_id=flow.project_id, code=flow.code).first()
        if exists:
            raise ServiceError("同一项目下该流程编码已存在。")
        db.session.add(flow)
        db.session.flush()
        if flow.is_default:
            AndroidUiProjectFlow.query.filter(
                AndroidUiProjectFlow.project_id == flow.project_id,
                AndroidUiProjectFlow.id != flow.id,
                AndroidUiProjectFlow.is_default.is_(True),
            ).update({"is_default": False}, synchronize_session=False)
        commit_session()
        return flow

    @staticmethod
    def update_project_flow(
        flow_id,
        name,
        code,
        description="",
        is_default=False,
        status="active",
        updated_by=None,
    ):
        flow = AndroidUiAutomationService.get_project_flow(flow_id)
        normalized_code = ensure_not_blank(code, "流程编码").lower().replace(" ", "_")
        exists = AndroidUiProjectFlow.query.filter(
            AndroidUiProjectFlow.project_id == flow.project_id,
            AndroidUiProjectFlow.code == normalized_code,
            AndroidUiProjectFlow.id != flow.id,
        ).first()
        if exists:
            raise ServiceError("同一项目下该流程编码已存在。")
        flow.name = ensure_not_blank(name, "流程名称")
        flow.code = normalized_code
        flow.description = str(description or "").strip()
        flow.is_default = bool(is_default)
        flow.status = "inactive" if str(status or "").strip().lower() == "inactive" else "active"
        flow.updated_by = updated_by
        flow.updated_at = datetime.utcnow()
        db.session.flush()
        if flow.is_default:
            AndroidUiProjectFlow.query.filter(
                AndroidUiProjectFlow.project_id == flow.project_id,
                AndroidUiProjectFlow.id != flow.id,
                AndroidUiProjectFlow.is_default.is_(True),
            ).update({"is_default": False}, synchronize_session=False)
        commit_session()
        return flow

    @staticmethod
    def delete_project_flow(flow_id):
        flow = AndroidUiAutomationService.get_project_flow(flow_id)
        db.session.delete(flow)
        commit_session()
        return True

    @staticmethod
    def create_flow_step(
        flow_id,
        step_name,
        step_type,
        selector_type="none",
        selector_value="",
        input_value="",
        wait_timeout_sec=20,
        retry_times=0,
        continue_on_failure=False,
        capture_on_success=True,
        capture_on_failure=True,
        remark="",
    ):
        flow = AndroidUiAutomationService.get_project_flow(flow_id)
        step_no = max((item.step_no for item in flow.steps), default=0) + 1
        step = AndroidUiProjectFlowStep(
            flow_id=flow.id,
            step_no=step_no,
            step_name=ensure_not_blank(step_name, "步骤名称"),
            step_type=AndroidUiAutomationService.normalize_step_type(step_type),
            selector_type=AndroidUiAutomationService.normalize_selector_type(selector_type),
            selector_value=str(selector_value or "").strip(),
            input_value=str(input_value or "").strip(),
            wait_timeout_sec=AndroidUiAutomationService._parse_positive_int(wait_timeout_sec, "步骤等待超时", 20),
            retry_times=max(0, int(retry_times or 0)),
            continue_on_failure=bool(continue_on_failure),
            capture_on_success=bool(capture_on_success),
            capture_on_failure=bool(capture_on_failure),
            sort_order=step_no,
            remark=str(remark or "").strip(),
        )
        db.session.add(step)
        commit_session()
        return step

    @staticmethod
    def update_flow_step(
        step_id,
        step_name,
        step_type,
        selector_type="none",
        selector_value="",
        input_value="",
        wait_timeout_sec=20,
        retry_times=0,
        continue_on_failure=False,
        capture_on_success=True,
        capture_on_failure=True,
        remark="",
    ):
        step = db.session.get(AndroidUiProjectFlowStep, step_id)
        if not step:
            raise ServiceError("流程步骤不存在。")
        step.step_name = ensure_not_blank(step_name, "步骤名称")
        step.step_type = AndroidUiAutomationService.normalize_step_type(step_type)
        step.selector_type = AndroidUiAutomationService.normalize_selector_type(selector_type)
        step.selector_value = str(selector_value or "").strip()
        step.input_value = str(input_value or "").strip()
        step.wait_timeout_sec = AndroidUiAutomationService._parse_positive_int(wait_timeout_sec, "步骤等待超时", 20)
        step.retry_times = max(0, int(retry_times or 0))
        step.continue_on_failure = bool(continue_on_failure)
        step.capture_on_success = bool(capture_on_success)
        step.capture_on_failure = bool(capture_on_failure)
        step.remark = str(remark or "").strip()
        step.updated_at = datetime.utcnow()
        commit_session()
        return step

    @staticmethod
    def delete_flow_step(step_id):
        step = db.session.get(AndroidUiProjectFlowStep, step_id)
        if not step:
            raise ServiceError("流程步骤不存在。")
        flow_id = step.flow_id
        db.session.delete(step)
        db.session.flush()
        remaining_steps = AndroidUiAutomationService.list_flow_steps(flow_id)
        # `step_no` has a per-flow unique constraint. Moving rows directly
        # from N+1 to N can transiently collide with a row that still owns N,
        # especially under SQLite's immediate uniqueness enforcement. Move to
        # a temporary range first, then assign the compact sequence.
        for index, item in enumerate(remaining_steps, start=1):
            item.step_no = 100000 + index
            item.sort_order = 100000 + index
        db.session.flush()
        for index, item in enumerate(remaining_steps, start=1):
            item.step_no = index
            item.sort_order = index
        commit_session()
        return True

    @staticmethod
    def create_task(
        project_id,
        name,
        package_key,
        flow_mode="basic",
        flow_id=None,
        package_name="",
        apk_url="",
        channel_tag="",
        device_serial="",
        install_timeout_sec=900,
        launch_wait_sec=35,
        auto_uninstall=True,
        remark="",
        created_by=None,
    ):
        project_id = int(project_id or 0)
        if project_id <= 0:
            raise ServiceError("请选择所属项目。")

        name = ensure_not_blank(name, "任务名称")
        package_key = ensure_not_blank(package_key, "包标识")
        apk_url = ensure_not_blank(apk_url, "下载链接")
        flow_mode, normalized_flow_id, flow_override_enabled = AndroidUiAutomationService.resolve_task_flow_binding(
            project_id=project_id,
            flow_mode=flow_mode,
            flow_id=flow_id,
        )
        package_name = str(package_name or "").strip()
        channel_tag = str(channel_tag or "").strip()
        device_serial = str(device_serial or "").strip()
        remark = str(remark or "").strip()

        exists = AndroidUiTestTask.query.filter_by(
            project_id=project_id,
            package_key=package_key,
        ).first()
        if exists:
            raise ServiceError("同一项目下该包标识已存在。")

        task = AndroidUiTestTask(
            project_id=project_id,
            name=name,
            package_key=package_key,
            flow_mode=flow_mode,
            flow_id=normalized_flow_id,
            flow_override_enabled=flow_override_enabled,
            package_name=package_name,
            apk_url=apk_url,
            channel_tag=channel_tag,
            device_serial=device_serial,
            install_timeout_sec=AndroidUiAutomationService._parse_positive_int(
                install_timeout_sec,
                "安装超时",
                default=900,
            ),
            launch_wait_sec=AndroidUiAutomationService._parse_positive_int(
                launch_wait_sec,
                "启动等待时长",
                default=35,
            ),
            auto_uninstall=bool(auto_uninstall),
            is_active=True,
            remark=remark,
            created_by=created_by,
            updated_by=created_by,
        )
        db.session.add(task)
        commit_session()
        return task

    @staticmethod
    def update_task(
        task_id,
        name,
        package_key,
        flow_mode="basic",
        flow_id=None,
        package_name="",
        apk_url="",
        channel_tag="",
        device_serial="",
        install_timeout_sec=900,
        launch_wait_sec=35,
        auto_uninstall=True,
        is_active=True,
        remark="",
        updated_by=None,
    ):
        task = AndroidUiAutomationService.get_task(task_id)
        name = ensure_not_blank(name, "任务名称")
        package_key = ensure_not_blank(package_key, "包标识")
        apk_url = ensure_not_blank(apk_url, "下载链接")

        flow_mode, normalized_flow_id, flow_override_enabled = AndroidUiAutomationService.resolve_task_flow_binding(
            project_id=task.project_id,
            flow_mode=flow_mode,
            flow_id=flow_id,
        )

        exists = AndroidUiTestTask.query.filter(
            AndroidUiTestTask.project_id == task.project_id,
            AndroidUiTestTask.package_key == package_key,
            AndroidUiTestTask.id != task.id,
        ).first()
        if exists:
            raise ServiceError("同一项目下该包标识已存在。")

        task.name = name
        task.package_key = package_key
        task.flow_mode = flow_mode
        task.flow_id = normalized_flow_id
        task.flow_override_enabled = flow_override_enabled
        task.package_name = str(package_name or "").strip()
        task.apk_url = apk_url
        task.channel_tag = str(channel_tag or "").strip()
        task.device_serial = str(device_serial or "").strip()
        task.install_timeout_sec = AndroidUiAutomationService._parse_positive_int(
            install_timeout_sec,
            "安装超时",
            default=900,
        )
        task.launch_wait_sec = AndroidUiAutomationService._parse_positive_int(
            launch_wait_sec,
            "启动等待时长",
            default=35,
        )
        task.auto_uninstall = bool(auto_uninstall)
        task.is_active = bool(is_active)
        task.remark = str(remark or "").strip()
        task.updated_by = updated_by
        task.updated_at = datetime.utcnow()
        commit_session()
        return task

    @staticmethod
    def delete_task(task_id):
        task = AndroidUiAutomationService.get_task(task_id)
        db.session.delete(task)
        commit_session()
        return True

    @staticmethod
    def list_runs(project_id=None, keyword="", status=""):
        query = AndroidUiTestRun.query
        if project_id:
            query = query.filter_by(project_id=project_id)
        runs = query.order_by(AndroidUiTestRun.created_at.desc()).all()

        normalized_keyword = str(keyword or "").strip().lower()
        if normalized_keyword:
            runs = [
                item
                for item in runs
                if normalized_keyword in str(item.id).lower()
                or normalized_keyword in (item.execution_no or "").lower()
                or normalized_keyword in (item.package_name or "").lower()
                or normalized_keyword in (item.device_serial or "").lower()
                or normalized_keyword in (item.stage or "").lower()
                or normalized_keyword in (item.task.name if item.task else "").lower()
                or normalized_keyword in (item.task.package_key if item.task else "").lower()
                or normalized_keyword in (item.task.package_name if item.task else "").lower()
                or normalized_keyword in (item.error_message or "").lower()
            ]

        normalized_status = str(status or "").strip().lower()
        if normalized_status:
            runs = [item for item in runs if (item.status or "").lower() == normalized_status]

        return runs

    @staticmethod
    def get_run(run_id):
        run = db.session.get(AndroidUiTestRun, run_id)
        if not run:
            raise ServiceError("Android UI 执行记录不存在。")
        return run

    @staticmethod
    def create_run(task_id, created_by=None):
        task = AndroidUiAutomationService.get_task(task_id)
        if not task.is_active:
            raise ServiceError("该任务已停用，无法发起执行。")

        conflict_run = (
            AndroidUiTestRun.query.filter(
                AndroidUiTestRun.task_id == task.id,
                AndroidUiTestRun.status.in_(
                    [ANDROID_UI_RUN_STATUS_PENDING, ANDROID_UI_RUN_STATUS_RUNNING]
                ),
            )
            .order_by(AndroidUiTestRun.id.desc())
            .first()
        )
        if conflict_run:
            raise ServiceError(
                f"该任务已有未完成的执行记录：#{conflict_run.id} / {conflict_run.execution_no or '未生成编号'}。"
            )

        run = AndroidUiTestRun(
            task_id=task.id,
            project_id=task.project_id,
            execution_no=AndroidUiAutomationService._generate_execution_no(task),
            flow_mode=task.flow_mode or AndroidUiAutomationService.FLOW_MODE_BASIC,
            status=ANDROID_UI_RUN_STATUS_PENDING,
            stage=ANDROID_UI_RUN_STAGE_QUEUED,
            package_name=task.package_name,
            device_serial=task.device_serial,
            created_by=created_by,
        )
        bound_flow = AndroidUiAutomationService.resolve_task_flow(task)
        if bound_flow:
            run.flow_id = bound_flow.id
            run.flow_snapshot = AndroidUiAutomationService.build_flow_snapshot(bound_flow)
        else:
            run.flow_snapshot = {}
        db.session.add(run)
        commit_session()
        AndroidUiAutomationService.materialize_run_steps(run)
        return run

    @staticmethod
    def retry_run(run_id, created_by=None):
        run = AndroidUiAutomationService.get_run(run_id)
        return AndroidUiAutomationService.create_run(
            task_id=run.task_id,
            created_by=created_by,
        )

    @staticmethod
    def mark_run_started(run_id, device_serial="", device_name=""):
        run = AndroidUiAutomationService.get_run(run_id)
        run.status = ANDROID_UI_RUN_STATUS_RUNNING
        run.stage = ANDROID_UI_RUN_STAGE_DOWNLOAD
        run.started_at = datetime.utcnow()
        if device_serial:
            run.device_serial = str(device_serial).strip()
        if device_name:
            run.device_name = str(device_name).strip()
        commit_session()
        return run

    @staticmethod
    def update_run_stage(run_id, stage, **fields):
        if stage not in ANDROID_UI_RUN_STAGES:
            raise ServiceError("无效的执行阶段。")

        run = AndroidUiAutomationService.get_run(run_id)
        run.stage = stage
        if run.status == ANDROID_UI_RUN_STATUS_PENDING:
            run.status = ANDROID_UI_RUN_STATUS_RUNNING
        if not run.started_at:
            run.started_at = datetime.utcnow()

        allowed_fields = {
            "download_status",
            "download_path",
            "download_size_bytes",
            "aapt_status",
            "package_name",
            "launchable_activity",
            "install_status",
            "launch_status",
            "crash_status",
            "pid",
            "current_focus",
            "device_serial",
            "device_name",
            "screenshot_path",
            "log_path",
            "error_type",
            "error_message",
        }
        for field_name, field_value in fields.items():
            if field_name in allowed_fields:
                setattr(run, field_name, field_value if field_value is not None else "")

        commit_session()
        return run

    @staticmethod
    def mark_run_passed(run_id, screenshot_path="", current_focus="", pid=""):
        run = AndroidUiAutomationService.get_run(run_id)
        run.status = ANDROID_UI_RUN_STATUS_PASSED
        run.stage = ANDROID_UI_RUN_STAGE_FINISHED
        run.launch_status = run.launch_status or "passed"
        run.crash_status = "not_detected"
        if screenshot_path:
            run.screenshot_path = screenshot_path
        if current_focus:
            run.current_focus = current_focus
        if pid:
            run.pid = pid
        AndroidUiAutomationService.finalize_run_steps(run.id, "passed")
        AndroidUiAutomationService._finish_run(run)
        commit_session()
        return run

    @staticmethod
    def mark_run_failed(run_id, stage="", error_type="", error_message=""):
        run = AndroidUiAutomationService.get_run(run_id)
        run.status = ANDROID_UI_RUN_STATUS_FAILED
        run.stage = stage if stage in ANDROID_UI_RUN_STAGES else (run.stage or ANDROID_UI_RUN_STAGE_FINISHED)
        run.error_type = str(error_type or "").strip()
        run.error_message = str(error_message or "").strip()
        AndroidUiAutomationService.finalize_run_steps(
            run.id,
            "stopped" if run.error_type == "manual_stop" else "failed",
            commit=False,
        )
        AndroidUiAutomationService._finish_run(run)
        commit_session()
        return run

    @staticmethod
    def finalize_run_steps(run_id, outcome, commit=False):
        normalized_outcome = str(outcome or "failed").strip().lower()
        pending_status = "skipped"
        current_status = {
            "passed": "passed",
            "stopped": "stopped",
        }.get(normalized_outcome, "failed")
        now = datetime.utcnow()
        steps = AndroidUiAutomationService.list_run_steps(run_id)
        for step in steps:
            if step.status == "running":
                step.status = current_status
                step.finished_at = step.finished_at or now
                if normalized_outcome == "stopped" and not step.error_message:
                    step.error_message = "执行已被手动停止。"
            elif step.status == "pending":
                step.status = pending_status
        if commit:
            commit_session()
        else:
            db.session.flush()
        return steps

    @staticmethod
    def list_run_steps(run_id):
        return (
            AndroidUiRunStep.query.filter_by(run_id=run_id)
            .order_by(AndroidUiRunStep.step_no.asc(), AndroidUiRunStep.id.asc())
            .all()
        )

    @staticmethod
    def materialize_run_steps(run):
        existing_steps = AndroidUiAutomationService.list_run_steps(getattr(run, "id", None))
        if existing_steps:
            return existing_steps
        snapshot = getattr(run, "flow_snapshot", {}) or {}
        step_rows = []
        for item in snapshot.get("steps") or []:
            step_rows.append(
                AndroidUiAutomationService.create_run_step(
                    run_id=run.id,
                    flow_id=snapshot.get("id"),
                    template_step_id=item.get("id"),
                    step_no=item.get("step_no") or len(step_rows) + 1,
                    step_name=item.get("step_name") or f"步骤 {len(step_rows) + 1}",
                    step_type=item.get("step_type") or "",
                    selector_type=item.get("selector_type") or "",
                    selector_value=item.get("selector_value") or "",
                    input_value=item.get("input_value") or "",
                    status="pending",
                )
            )
        return step_rows

    @staticmethod
    def create_run_step(
        run_id,
        flow_id,
        template_step_id,
        step_no,
        step_name,
        step_type,
        selector_type="",
        selector_value="",
        input_value="",
        status="pending",
    ):
        step = AndroidUiRunStep(
            run_id=run_id,
            flow_id=flow_id,
            template_step_id=template_step_id,
            step_no=step_no,
            step_name=str(step_name or "").strip(),
            step_type=str(step_type or "").strip(),
            selector_type=str(selector_type or "").strip(),
            selector_value=str(selector_value or "").strip(),
            input_value=str(input_value or "").strip(),
            status=str(status or "pending").strip(),
        )
        db.session.add(step)
        commit_session()
        return step

    @staticmethod
    def update_run_step(
        run_step_id,
        status=None,
        screenshot_path=None,
        error_message=None,
        started_at=None,
        finished_at=None,
        duration_ms=None,
        raw_result=None,
    ):
        step = db.session.get(AndroidUiRunStep, run_step_id)
        if not step:
            raise ServiceError("执行步骤记录不存在。")
        if status is not None:
            step.status = str(status or "").strip() or step.status
        if screenshot_path is not None:
            step.screenshot_path = str(screenshot_path or "").strip()
        if error_message is not None:
            step.error_message = str(error_message or "").strip()
        if started_at is not None:
            step.started_at = started_at
        if finished_at is not None:
            step.finished_at = finished_at
        if duration_ms is not None:
            step.duration_ms = max(0, int(duration_ms or 0))
        if raw_result is not None:
            step.raw_result = raw_result
        commit_session()
        return step

    @staticmethod
    def create_run_step_artifact(
        run_step_id,
        artifact_type,
        file_path="",
        file_name="",
        file_size=0,
    ):
        run_step = db.session.get(AndroidUiRunStep, run_step_id)
        if not run_step:
            raise ServiceError("执行步骤记录不存在。")
        artifact = AndroidUiRunStepArtifact(
            run_step_id=run_step.id,
            artifact_type=ensure_not_blank(artifact_type, "产物类型"),
            file_path=str(file_path or "").strip(),
            file_name=str(file_name or "").strip(),
            file_size=max(0, int(file_size or 0)),
        )
        db.session.add(artifact)
        commit_session()
        return artifact

    @staticmethod
    def list_run_step_artifacts(run_step_id):
        return (
            AndroidUiRunStepArtifact.query.filter_by(run_step_id=run_step_id)
            .order_by(AndroidUiRunStepArtifact.id.asc())
            .all()
        )

    @staticmethod
    def task_metrics(tasks):
        passed_count = 0
        failed_count = 0
        pending_count = 0
        for item in tasks:
            latest_run = item.runs[0] if item.runs else None
            if not latest_run:
                pending_count += 1
            elif latest_run.status == ANDROID_UI_RUN_STATUS_PASSED:
                passed_count += 1
            elif latest_run.status == ANDROID_UI_RUN_STATUS_FAILED:
                failed_count += 1
            else:
                pending_count += 1
        return {
            "total": len(tasks),
            "active": sum(1 for item in tasks if item.is_active),
            "inactive": sum(1 for item in tasks if not item.is_active),
            "passed": passed_count,
            "failed": failed_count,
            "pending": pending_count,
        }

    @staticmethod
    def run_metrics(runs):
        return {
            "total": len(runs),
            "pending": sum(1 for item in runs if item.status == ANDROID_UI_RUN_STATUS_PENDING),
            "running": sum(1 for item in runs if item.status == ANDROID_UI_RUN_STATUS_RUNNING),
            "passed": sum(1 for item in runs if item.status == ANDROID_UI_RUN_STATUS_PASSED),
            "failed": sum(1 for item in runs if item.status == ANDROID_UI_RUN_STATUS_FAILED),
        }

    @staticmethod
    def format_bytes(size_bytes):
        try:
            size = float(size_bytes or 0)
        except (TypeError, ValueError):
            size = 0.0
        if size <= 0:
            return "-"
        units = ["B", "KB", "MB", "GB", "TB"]
        unit_index = 0
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
        if unit_index == 0:
            return f"{int(size)} {units[unit_index]}"
        return f"{size:.2f} {units[unit_index]}"

    @staticmethod
    def execution_summary(task):
        latest_run = task.runs[0] if task.runs else None
        if not latest_run:
            return {
                "status": ANDROID_UI_RUN_STATUS_PENDING,
                "label": "未执行",
                "time_text": "-",
                "error_message": "",
                "error_hint": "",
            }

        label_map = {
            ANDROID_UI_RUN_STATUS_PENDING: "排队中",
            ANDROID_UI_RUN_STATUS_RUNNING: "执行中",
            ANDROID_UI_RUN_STATUS_PASSED: "通过",
            ANDROID_UI_RUN_STATUS_FAILED: "执行异常",
        }
        time_value = latest_run.finished_at or latest_run.started_at or latest_run.updated_at
        return {
            "status": latest_run.status,
            "label": label_map.get(latest_run.status, latest_run.status or "-"),
            "time_text": time_value.strftime("%Y-%m-%d %H:%M:%S") if time_value else "-",
            "error_message": latest_run.error_message or "",
            "error_hint": AndroidUiAutomationService.short_error_label(latest_run),
        }

    @staticmethod
    def stage_label(stage):
        return {
            ANDROID_UI_RUN_STAGE_QUEUED: "排队中",
            ANDROID_UI_RUN_STAGE_DOWNLOAD: "下载 APK",
            ANDROID_UI_RUN_STAGE_APK_PARSE: "解析 APK",
            ANDROID_UI_RUN_STAGE_INSTALL: "安装应用",
            ANDROID_UI_RUN_STAGE_LAUNCH: "启动应用",
            ANDROID_UI_RUN_STAGE_SCREENSHOT: "截图取证",
            ANDROID_UI_RUN_STAGE_FINISHED: "执行完成",
        }.get(stage or "", stage or "-")

    @staticmethod
    def status_label(status):
        return {
            ANDROID_UI_RUN_STATUS_PENDING: "排队中",
            ANDROID_UI_RUN_STATUS_RUNNING: "执行中",
            ANDROID_UI_RUN_STATUS_PASSED: "通过",
            ANDROID_UI_RUN_STATUS_FAILED: "失败",
        }.get(status or "", status or "-")

    @staticmethod
    def worker_state_label(worker_health):
        health = worker_health or {}
        if health.get("online") and health.get("current_run_id"):
            return "忙碌中"
        if health.get("online"):
            return "在线"
        if health.get("pid_alive"):
            return "心跳超时"
        return "离线"

    @staticmethod
    def normalize_device_serial(raw_value, device_mode=""):
        mode = str(device_mode or "").strip().lower()
        serial = str(raw_value or "").strip()
        if mode == "default":
            return AndroidUiAutomationService.DEFAULT_DEVICE_SENTINEL
        if mode == "specified":
            if not serial:
                raise ServiceError("选择“指定设备”时，必须填写设备序列号。")
            return serial
        return ""

    @staticmethod
    def detect_device_mode(device_serial):
        serial = str(device_serial or "").strip()
        if serial == AndroidUiAutomationService.DEFAULT_DEVICE_SENTINEL:
            return "default"
        if serial:
            return "specified"
        return "auto"

    @staticmethod
    def flow_mode_label(flow_mode):
        normalized = AndroidUiAutomationService.normalize_flow_mode(flow_mode)
        if normalized == AndroidUiAutomationService.FLOW_MODE_FULL:
            return "安装包+SDK全功能验证"
        return "仅基础装包验证"

    @staticmethod
    def task_flow_summary(task):
        if not task:
            return "-"
        mode_label = AndroidUiAutomationService.flow_mode_label(getattr(task, "flow_mode", "basic"))
        if getattr(task, "flow", None):
            return f"{mode_label} / {task.flow.name}"
        if AndroidUiAutomationService.normalize_flow_mode(getattr(task, "flow_mode", "basic")) == AndroidUiAutomationService.FLOW_MODE_FULL:
            default_flow = AndroidUiAutomationService.get_default_project_flow(getattr(task, "project_id", None))
            if default_flow:
                return f"{mode_label} / {default_flow.name}"
        return mode_label

    @staticmethod
    def flow_step_type_options():
        return list(AndroidUiAutomationService.SUPPORTED_STEP_TYPES)

    @staticmethod
    def flow_selector_type_options():
        return list(AndroidUiAutomationService.SUPPORTED_SELECTOR_TYPES)

    @staticmethod
    def flow_step_type_guides():
        return {
            "wait_text": {
                "summary": "等待某个界面元素出现，适合登录按钮、SDK 弹窗、进入游戏后的首页标识。",
                "selector_hint": "建议填写可稳定定位的文本、resource id 或 bounds。",
                "input_hint": "不需要输入值。",
            },
            "assert_exists": {
                "summary": "断言元素必须出现，适合关键界面校验。",
                "selector_hint": "必须提供定位条件。",
                "input_hint": "不需要输入值。",
            },
            "assert_not_exists": {
                "summary": "断言元素不应出现，适合校验弹窗已关闭或异常提示未出现。",
                "selector_hint": "必须提供定位条件。",
                "input_hint": "不需要输入值。",
            },
            "tap_text": {
                "summary": "先定位元素，再点击它的中心点。",
                "selector_hint": "建议优先使用 text 或 resource id。",
                "input_hint": "不需要输入值。",
            },
            "tap_left_of_text": {
                "summary": "先定位一段文本，再点击它左侧的圆圈或复选框，适合 SDK 协议勾选。",
                "selector_hint": "建议填写协议文案，例如“我已详细阅读并同意”。",
                "input_hint": "可填写左侧偏移像素，默认 26。",
            },
            "tap_bounds": {
                "summary": "按坐标范围直接点击，适合难以稳定定位的 SDK 控件。",
                "selector_hint": "请填写类似 [10,20][80,90] 的 bounds。",
                "input_hint": "不需要输入值。",
            },
            "input_text": {
                "summary": "先聚焦输入框，再输入文本，适合账号、密码、验证码。",
                "selector_hint": "可选。填写后会先点击输入框，不填则直接输入到当前焦点。",
                "input_hint": "必须填写要输入的内容。",
            },
            "keyevent": {
                "summary": "发送 Android keyevent，适合返回键、回车键、菜单键。",
                "selector_hint": "可留空，也可把 keycode 填在 selector 中。",
                "input_hint": "建议填写 keycode，例如 4 表示返回键。",
            },
            "sleep": {
                "summary": "强制等待一段时间，适合已知动画或加载过渡。",
                "selector_hint": "不需要定位条件。",
                "input_hint": "不需要输入值，等待秒数取“等待超时”字段。",
            },
            "screenshot": {
                "summary": "单独截一张步骤图，适合在进入游戏界面后保留凭证。",
                "selector_hint": "不需要定位条件。",
                "input_hint": "不需要输入值。",
            },
            "wait_image": {
                "summary": "等待指定图像模板出现在屏幕上，适合关闭按钮、浮窗图标等纯图形控件。",
                "selector_hint": "请填写模板图片路径，支持绝对路径或相对模板目录路径。",
                "input_hint": "不需要输入值。",
            },
            "tap_image": {
                "summary": "先匹配指定图像模板，再点击图像中心点。",
                "selector_hint": "请填写模板图片路径，建议用于无文字按钮和图标。",
                "input_hint": "不需要输入值。",
            },
            "open_xianyu_user_center": {
                "summary": "定位仙遇悬浮入口并打开用户中心；每次点击后都会确认标题出现，失败时按重试次数重新尝试并保存过程截图。",
                "selector_hint": "填写用户中心标题模板路径，默认使用 xianyu/xianyu_user_center_title.png。",
                "input_hint": "不需要输入值；重试次数表示额外尝试次数，2 表示最多执行 3 轮。",
            },
            "assert_image_exists": {
                "summary": "断言图像模板必须出现，适合校验浮窗和弹窗入口。",
                "selector_hint": "请填写模板图片路径。",
                "input_hint": "不需要输入值。",
            },
            "assert_image_not_exists": {
                "summary": "断言图像模板不应出现，适合校验关闭和消失状态。",
                "selector_hint": "请填写模板图片路径。",
                "input_hint": "不需要输入值。",
            },
        }

    @staticmethod
    def flow_selector_type_guides():
        return {
            "none": "不使用定位条件，适合 sleep、screenshot、纯 keyevent。",
            "text": "按文本或 content-desc 查找，适合游客登录、开始游戏等按钮。",
            "resource_id": "按控件 resource id 查找，稳定性通常最高。",
            "xpath": "按 XPath 查找，灵活但更容易受 UI 结构变化影响。",
            "bounds": "按控件 bounds 查找，适合固定坐标区域。",
            "activity": "按当前 Activity 判断，适合切页或进入游戏后的页面校验。",
            "image": "按图片模板查找，适合图标、关闭按钮、悬浮窗等没有稳定文字的控件。",
        }

    @staticmethod
    def flow_presets():
        return get_android_ui_flow_presets()
        return [
            {
                "key": "xianyu_leyuan_account_login",
                "name": "仙遇-乐享元游 SDK 账号登录",
                "summary": "覆盖启动协议、资源加载、账号登录、协议勾选与进入游戏界面。",
                "steps": [
                    {
                        "step_name": "等待启动协议弹窗",
                        "step_type": "wait_text",
                        "selector_type": "text",
                        "selector_value": "同意",
                        "wait_timeout_sec": 25,
                        "capture_on_success": True,
                        "remark": "确认游戏启动后先进入协议弹窗。",
                    },
                    {
                        "step_name": "点击启动协议同意",
                        "step_type": "tap_text",
                        "selector_type": "text",
                        "selector_value": "同意",
                        "wait_timeout_sec": 15,
                        "capture_on_success": True,
                        "remark": "同意启动协议，继续资源加载。",
                    },
                    {
                        "step_name": "等待资源加载完成并出现 SDK 登录弹窗",
                        "step_type": "wait_text",
                        "selector_type": "text",
                        "selector_value": "账号登录",
                        "wait_timeout_sec": 240,
                        "capture_on_success": True,
                        "remark": "资源下载完成后应出现乐享元游 SDK 登录入口。",
                    },
                    {
                        "step_name": "点击账号登录入口",
                        "step_type": "tap_text",
                        "selector_type": "text",
                        "selector_value": "账号登录",
                        "wait_timeout_sec": 20,
                        "capture_on_success": True,
                        "remark": "切换到账号密码登录表单。",
                    },
                    {
                        "step_name": "等待账号密码表单出现",
                        "step_type": "wait_text",
                        "selector_type": "text",
                        "selector_value": "请输入账号",
                        "wait_timeout_sec": 30,
                        "capture_on_success": True,
                        "remark": "确认账号输入框已经展示。",
                    },
                    {
                        "step_name": "输入测试账号",
                        "step_type": "input_text",
                        "selector_type": "text",
                        "selector_value": "请输入账号",
                        "input_value": "zsr005",
                        "wait_timeout_sec": 20,
                        "capture_on_success": True,
                        "remark": "测试账号由业务方提供。",
                    },
                    {
                        "step_name": "输入测试密码",
                        "step_type": "input_text",
                        "selector_type": "text",
                        "selector_value": "请输入密码",
                        "input_value": "123456",
                        "wait_timeout_sec": 20,
                        "capture_on_success": True,
                        "remark": "密码输入框占位文案通常包含“请输入密码”。",
                    },
                    {
                        "step_name": "勾选登录协议圆圈",
                        "step_type": "tap_left_of_text",
                        "selector_type": "text",
                        "selector_value": "我已详细阅读并同意",
                        "input_value": "26",
                        "wait_timeout_sec": 20,
                        "capture_on_success": True,
                        "remark": "点击协议文案左侧圆圈，适配无文字复选框。",
                    },
                    {
                        "step_name": "点击登录游戏",
                        "step_type": "tap_text",
                        "selector_type": "text",
                        "selector_value": "登录游戏",
                        "wait_timeout_sec": 20,
                        "capture_on_success": True,
                        "remark": "提交账号密码登录。",
                    },
                    {
                        "step_name": "等待进入游戏界面",
                        "step_type": "wait_text",
                        "selector_type": "text",
                        "selector_value": "公告",
                        "wait_timeout_sec": 90,
                        "capture_on_success": True,
                        "remark": "进入游戏后通常会出现右上角公告入口。",
                    },
                    {
                        "step_name": "保留进入游戏截图",
                        "step_type": "screenshot",
                        "selector_type": "none",
                        "selector_value": "",
                        "wait_timeout_sec": 5,
                        "capture_on_success": True,
                        "remark": "沉淀进入游戏后的凭证截图。",
                    },
                ],
            }
        ]

    @staticmethod
    def get_flow_preset(preset_key):
        normalized_key = str(preset_key or "").strip().lower()
        for item in AndroidUiAutomationService.flow_presets():
            if item["key"] == normalized_key:
                return item
        raise ServiceError("未找到对应的项目流程预设。")

    @staticmethod
    def apply_flow_preset(flow_id, preset_key, replace_existing=True):
        flow = AndroidUiAutomationService.get_project_flow(flow_id)
        preset = AndroidUiAutomationService.get_flow_preset(preset_key)
        if replace_existing:
            for current_step in list(flow.steps or []):
                db.session.delete(current_step)
            db.session.flush()
        for index, step in enumerate(preset.get("steps") or [], start=1):
            db.session.add(
                AndroidUiProjectFlowStep(
                    flow_id=flow.id,
                    step_no=index,
                    step_name=ensure_not_blank(step.get("step_name"), "步骤名称"),
                    step_type=AndroidUiAutomationService.normalize_step_type(step.get("step_type")),
                    selector_type=AndroidUiAutomationService.normalize_selector_type(step.get("selector_type", "none")),
                    selector_value=str(step.get("selector_value") or "").strip(),
                    input_value=str(step.get("input_value") or "").strip(),
                    wait_timeout_sec=AndroidUiAutomationService._parse_positive_int(
                        step.get("wait_timeout_sec", 20),
                        "步骤等待超时",
                        20,
                    ),
                    retry_times=max(0, int(step.get("retry_times") or 0)),
                    continue_on_failure=bool(step.get("continue_on_failure")),
                    capture_on_success=bool(step.get("capture_on_success", True)),
                    capture_on_failure=bool(step.get("capture_on_failure", True)),
                    sort_order=index,
                    remark=str(step.get("remark") or "").strip(),
                )
            )
        flow.updated_at = datetime.utcnow()
        commit_session()
        return flow, preset

    @staticmethod
    def device_strategy_label(device_serial):
        serial = str(device_serial or "").strip()
        if serial == AndroidUiAutomationService.DEFAULT_DEVICE_SENTINEL:
            return "默认设备"
        if serial:
            return serial
        return "自动分配可用设备"

    @staticmethod
    def worker_state_class(worker_health):
        health = worker_health or {}
        if health.get("online") and health.get("current_run_id"):
            return "status-pending"
        if health.get("online"):
            return "status-active"
        if health.get("pid_alive"):
            return "status-warning"
        return "status-muted"

    @staticmethod
    def short_error_label(run):
        if not run:
            return ""
        if run.status == ANDROID_UI_RUN_STATUS_PENDING:
            return "等待 Worker 领取"
        if run.status == ANDROID_UI_RUN_STATUS_RUNNING:
            return f"当前阶段：{AndroidUiAutomationService.stage_label(run.stage)}"
        if run.status == ANDROID_UI_RUN_STATUS_PASSED:
            return "已完成下载、安装、启动和截图"

        stage = str(run.stage or "")
        error_type = str(run.error_type or "").lower()
        message = str(run.error_message or "")
        lowered = message.lower()

        if "download" in stage or "下载" in message:
            return "下载失败"
        if "apk_parse" in stage or "aapt" in lowered or "解析" in message:
            return "APK 解析失败"
        if "install" in stage or "install" in lowered or "安装" in message:
            return "安装失败"
        if "launch" in stage or "monkey" in lowered or "am start" in lowered or "启动" in message:
            return "启动失败"
        if "screenshot" in stage or "screencap" in lowered or "截图" in message:
            return "截图失败"
        if error_type == "timeout":
            return "执行超时"
        if "闪退" in message:
            return "疑似闪退"
        return "执行失败"

    @staticmethod
    def failure_category(run):
        if not run or run.status != ANDROID_UI_RUN_STATUS_FAILED:
            return ""
        hint = AndroidUiAutomationService.short_error_label(run)
        if hint in {"下载失败", "截图失败", "执行超时"}:
            return "建议重试"
        if hint in {"APK 解析失败", "安装失败"}:
            return "疑似包或环境异常"
        if hint in {"启动失败", "疑似闪退"}:
            return "疑似包启动异常"
        return "需要人工确认"

    @staticmethod
    def retry_advice(run):
        if not run or run.status != ANDROID_UI_RUN_STATUS_FAILED:
            return ""
        hint = AndroidUiAutomationService.short_error_label(run)
        advice_map = {
            "下载失败": "优先检查下载链接、网络连通性，必要时可直接在浏览器复测链接。",
            "APK 解析失败": "优先确认 APK 文件是否完整，必要时重新下载或让研发重新出包。",
            "安装失败": "建议检查设备存储、签名冲突、系统安装限制，必要时换一台设备重试。",
            "启动失败": "建议先重试一次，再结合日志判断是设备问题还是应用本身未拉起。",
            "截图失败": "建议优先重试，并检查设备当前是否仍在线。",
            "执行超时": "建议在调大超时前，先确认当前设备和网络是否稳定。",
            "疑似闪退": "更像是包本身启动异常，建议结合日志和截图让研发排查。",
        }
        return advice_map.get(hint, "建议查看日志后再决定是否重试。")

    @staticmethod
    def timeline_steps(run):
        ordered_steps = [
            ANDROID_UI_RUN_STAGE_QUEUED,
            ANDROID_UI_RUN_STAGE_DOWNLOAD,
            ANDROID_UI_RUN_STAGE_APK_PARSE,
            ANDROID_UI_RUN_STAGE_INSTALL,
            ANDROID_UI_RUN_STAGE_LAUNCH,
            ANDROID_UI_RUN_STAGE_SCREENSHOT,
            ANDROID_UI_RUN_STAGE_FINISHED,
        ]
        current_stage = str(getattr(run, "stage", "") or "")
        current_index = ordered_steps.index(current_stage) if current_stage in ordered_steps else -1
        is_failed = getattr(run, "status", "") == ANDROID_UI_RUN_STATUS_FAILED
        is_passed = getattr(run, "status", "") == ANDROID_UI_RUN_STATUS_PASSED

        timeline = []
        for index, step in enumerate(ordered_steps):
            state = "pending"
            if current_index >= 0 and index < current_index:
                state = "done"
            elif index == current_index:
                state = "failed" if is_failed else "current"
            elif is_passed and step == ANDROID_UI_RUN_STAGE_FINISHED:
                state = "done"
            timeline.append(
                {
                    "key": step,
                    "label": AndroidUiAutomationService.stage_label(step),
                    "state": state,
                }
            )
        return timeline

    @staticmethod
    def execution_stage_cards(run):
        run_steps = AndroidUiAutomationService.list_run_steps(getattr(run, "id", None))
        if run_steps:
            cards = []
            for item in run_steps:
                state = "pending"
                if item.status == "passed":
                    state = "done"
                elif item.status in {"failed", "timeout"}:
                    state = "failed"
                elif item.status in {"running"}:
                    state = "current"
                notes = []
                if item.selector_type:
                    notes.append(f"选择器类型：{item.selector_type}")
                if item.selector_value:
                    notes.append(f"选择器值：{item.selector_value}")
                if item.input_value:
                    notes.append(f"输入值：{item.input_value}")
                if item.duration_ms:
                    notes.append(f"耗时：{item.duration_ms} ms")
                if item.error_message:
                    notes.append(f"异常：{item.error_message}")
                cards.append(
                    {
                        "index": item.step_no,
                        "key": f"run-step-{item.id}",
                        "title": item.step_name or f"步骤 {item.step_no}",
                        "state": state,
                        "status_text": {
                            "done": "已完成",
                            "current": "进行中",
                            "failed": "失败",
                            "pending": "待执行",
                        }.get(state, "待执行"),
                        "notes": notes or [f"动作类型：{item.step_type or '-'}"],
                        "show_screenshot": bool(item.screenshot_path),
                        "screenshot_path": item.screenshot_path or "",
                        "empty_shot_text": "该步骤暂无截图产物",
                    }
                )
            return cards

        ordered_steps = [
            ANDROID_UI_RUN_STAGE_QUEUED,
            ANDROID_UI_RUN_STAGE_DOWNLOAD,
            ANDROID_UI_RUN_STAGE_APK_PARSE,
            ANDROID_UI_RUN_STAGE_INSTALL,
            ANDROID_UI_RUN_STAGE_LAUNCH,
            ANDROID_UI_RUN_STAGE_SCREENSHOT,
            ANDROID_UI_RUN_STAGE_FINISHED,
        ]
        current_stage = str(getattr(run, "stage", "") or "")
        current_index = ordered_steps.index(current_stage) if current_stage in ordered_steps else -1
        is_failed = getattr(run, "status", "") == ANDROID_UI_RUN_STATUS_FAILED
        is_passed = getattr(run, "status", "") == ANDROID_UI_RUN_STATUS_PASSED
        stage_notes = {
            ANDROID_UI_RUN_STAGE_QUEUED: [
                f"执行编号：{run.execution_no or '-'}",
                f"设备策略：{AndroidUiAutomationService.device_strategy_label(run.device_serial)}",
            ],
            ANDROID_UI_RUN_STAGE_DOWNLOAD: [
                f"下载状态：{run.download_status or '待执行'}",
                f"下载大小：{AndroidUiAutomationService.format_bytes(run.download_size_bytes)}",
            ],
            ANDROID_UI_RUN_STAGE_APK_PARSE: [
                f"解析状态：{run.aapt_status or '待执行'}",
                f"包名：{run.package_name or '-'}",
                f"启动 Activity：{run.launchable_activity or '-'}",
            ],
            ANDROID_UI_RUN_STAGE_INSTALL: [
                f"安装状态：{run.install_status or '待执行'}",
                f"设备：{run.device_name or run.device_serial or '-'}",
            ],
            ANDROID_UI_RUN_STAGE_LAUNCH: [
                f"启动状态：{run.launch_status or '待执行'}",
                f"前台窗口：{run.current_focus or '-'}",
                f"进程 PID：{run.pid or '-'}",
            ],
            ANDROID_UI_RUN_STAGE_SCREENSHOT: [
                f"截图状态：{'已生成' if run.screenshot_path else '待采集'}",
                f"截图路径：{run.screenshot_path or '-'}",
            ],
            ANDROID_UI_RUN_STAGE_FINISHED: [
                f"执行结果：{AndroidUiAutomationService.status_label(run.status)}",
                f"结果说明：{AndroidUiAutomationService.short_error_label(run) or '-'}",
                f"总耗时：{run.duration_ms or 0} ms",
            ],
        }
        cards = []
        for index, step in enumerate(ordered_steps, start=1):
            state = "pending"
            if current_index >= 0 and index - 1 < current_index:
                state = "done"
            elif index - 1 == current_index:
                state = "failed" if is_failed else "current"
            elif is_passed and step == ANDROID_UI_RUN_STAGE_FINISHED:
                state = "done"
            notes = [item for item in stage_notes.get(step, []) if item and not item.endswith("：-")]
            cards.append(
                {
                    "index": index,
                    "key": step,
                    "title": AndroidUiAutomationService.stage_label(step),
                    "state": state,
                    "status_text": {
                        "done": "已完成",
                        "current": "进行中",
                        "failed": "失败",
                        "pending": "待执行",
                    }.get(state, "待执行"),
                    "notes": notes,
                    "show_screenshot": step in {ANDROID_UI_RUN_STAGE_SCREENSHOT, ANDROID_UI_RUN_STAGE_FINISHED},
                    "empty_shot_text": "该阶段暂无截图产物",
                }
            )
        return cards

    @staticmethod
    def _generate_execution_no(task):
        now = datetime.utcnow()
        return f"AUI{now.strftime('%Y%m%d%H%M%S')}-{task.id}"

    @staticmethod
    def _finish_run(run):
        now = datetime.utcnow()
        if not run.started_at:
            run.started_at = now
        run.finished_at = now
        run.duration_ms = max(0, int((run.finished_at - run.started_at).total_seconds() * 1000))

    @staticmethod
    def _parse_positive_int(value, field_name, default):
        raw = value if value not in (None, "") else default
        try:
            parsed = int(raw)
        except (TypeError, ValueError) as exc:
            raise ServiceError(f"{field_name} 必须是整数。") from exc
        if parsed <= 0:
            raise ServiceError(f"{field_name} 必须大于 0。")
        return parsed
