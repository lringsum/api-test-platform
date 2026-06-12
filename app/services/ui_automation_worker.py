from __future__ import annotations

import importlib.util
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from textwrap import dedent

from flask import current_app

from app import db
from app.models import (
    UiAutomationArtifact,
    UiAutomationEnvironment,
    UiAutomationRunStep,
    UiAutomationRun,
    UiAutomationScriptVersion,
)
from app.services.base_service import ServiceError
from app.services.ui_automation_service import UiAutomationService


class UiAutomationWorker:
    REQUIRED_MODULES = {
        "pytest": "pytest",
        "playwright": "playwright",
        "pytest_playwright": "pytest-playwright",
    }

    @staticmethod
    def workspace_root():
        root = Path(current_app.instance_path) / "ui_automation" / "runs"
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()

    @staticmethod
    def get_run(run_id):
        run = db.session.get(UiAutomationRun, run_id)
        if not run:
            raise ServiceError("UI 自动化执行记录不存在。")
        return run

    @staticmethod
    def get_next_queued_run():
        return (
            UiAutomationRun.query.filter_by(status="queued")
            .order_by(UiAutomationRun.created_at.asc(), UiAutomationRun.id.asc())
            .first()
        )

    @staticmethod
    def _validate_runtime():
        missing = [
            package_name
            for module_name, package_name in UiAutomationWorker.REQUIRED_MODULES.items()
            if importlib.util.find_spec(module_name) is None
        ]
        if missing:
            packages = " ".join(missing)
            raise ServiceError(
                f"UI 自动化 Worker 缺少运行依赖：{packages}。"
                f"请执行：{sys.executable} -m pip install {packages}"
            )

    @staticmethod
    def _prepare_workspace(run):
        workspace = UiAutomationWorker.workspace_root() / str(run.id)
        if workspace.exists():
            shutil.rmtree(workspace)
        output_dir = workspace / "test-results"
        workspace.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        version = db.session.get(UiAutomationScriptVersion, run.script_version_id)
        if not version:
            raise ServiceError("执行记录缺少脚本版本。")

        script_path = workspace / "test_script.py"
        script_path.write_text(version.script_content, encoding="utf-8")
        UiAutomationWorker._write_runtime_config(run, workspace)
        return workspace, output_dir, script_path

    @staticmethod
    def _find_chromium_executable():
        browser_root = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
        candidates = sorted(
            browser_root.glob("chromium-*/chrome-win*/chrome.exe"),
            reverse=True,
        )
        return candidates[0] if candidates else None

    @staticmethod
    def _write_runtime_config(run, workspace):
        environment = (
            db.session.get(UiAutomationEnvironment, run.environment_id)
            if run.environment_id
            else None
        )
        launch_args = {}
        if (run.browser_type or "chromium").lower() == "chromium":
            executable = UiAutomationWorker._find_chromium_executable()
            if executable:
                launch_args["executable_path"] = str(executable)

        viewport = {
            "width": environment.viewport_width if environment else 1440,
            "height": environment.viewport_height if environment else 900,
        }
        config_content = "\n".join(
            [
                "import pytest",
                "from ui_step_recorder import install_recorder",
                "",
                "install_recorder()",
                "",
                "",
                "@pytest.fixture(scope=\"session\")",
                "def browser_type_launch_args(browser_type_launch_args):",
                f"    return {{**browser_type_launch_args, **{launch_args!r}}}",
                "",
                "",
                "@pytest.fixture(scope=\"session\")",
                "def browser_context_args(browser_context_args):",
                f"    return {{**browser_context_args, \"viewport\": {viewport!r}}}",
                "",
            ]
        )
        (workspace / "conftest.py").write_text(config_content, encoding="utf-8")
        (workspace / "ui_step_recorder.py").write_text(
            UiAutomationWorker._runtime_recorder_source(),
            encoding="utf-8",
        )

    @staticmethod
    def _runtime_recorder_source():
        return dedent(
            r'''
            import functools
            import json
            import os
            import threading
            import time
            from datetime import datetime, timezone
            from pathlib import Path

            from playwright.sync_api import Locator, LocatorAssertions, Page, PageAssertions


            _LOCK = threading.Lock()
            _SEQUENCE = 0
            _INSTALLED = False
            _OUTPUT_PATH = Path(os.environ.get("UI_AUTOMATION_STEP_FILE", "runtime-steps.jsonl"))
            _SCREENSHOT_ROOT = Path(
                os.environ.get("UI_AUTOMATION_STEP_SCREENSHOT_DIR", "step_screenshots")
            )

            PAGE_ACTIONS = {
                "goto": ("navigate", "打开页面"),
                "reload": ("navigate", "刷新页面"),
                "go_back": ("navigate", "返回上一页"),
                "go_forward": ("navigate", "前进到下一页"),
                "set_content": ("setup", "设置页面内容"),
                "wait_for_load_state": ("wait", "等待页面加载"),
            }

            LOCATOR_ACTIONS = {
                "click": ("click", "点击元素"),
                "dblclick": ("click", "双击元素"),
                "fill": ("fill", "填写字段"),
                "type": ("fill", "输入文本"),
                "press": ("press", "键盘输入"),
                "select_option": ("select", "选择选项"),
                "check": ("select", "勾选选项"),
                "uncheck": ("select", "取消勾选"),
                "hover": ("hover", "悬停元素"),
                "focus": ("focus", "聚焦元素"),
                "blur": ("focus", "移出焦点"),
                "drag_to": ("drag", "拖拽元素"),
                "scroll_into_view_if_needed": ("scroll", "滚动到元素"),
                "set_input_files": ("upload", "上传文件"),
                "wait_for": ("wait", "等待元素"),
            }


            def _safe_text(value, limit=1200):
                if value is None:
                    return ""
                if isinstance(value, (str, int, float, bool)):
                    text = str(value)
                else:
                    try:
                        text = json.dumps(value, ensure_ascii=False, default=str)
                    except (TypeError, ValueError):
                        text = repr(value)
                return text if len(text) <= limit else text[:limit] + "..."


            def _target_text(target):
                impl = getattr(target, "_impl_obj", None)
                actual = getattr(impl, "_actual_locator", None) or getattr(impl, "_actual_page", None)
                if actual is not None:
                    return _safe_text(actual)
                return _safe_text(target)


            def _sync_api_object(candidate):
                if candidate is None:
                    return None
                return getattr(candidate, "_pw_api_instance_", candidate)


            def _resolve_page(target):
                if isinstance(target, Page):
                    return target
                if isinstance(target, Locator):
                    return _sync_api_object(getattr(target, "page", None))
                impl = getattr(target, "_impl_obj", None)
                if impl is not None:
                    actual_page = getattr(impl, "_actual_page", None)
                    if actual_page is not None:
                        return _sync_api_object(getattr(actual_page, "page", actual_page))
                    actual_locator = getattr(impl, "_actual_locator", None)
                    if actual_locator is not None:
                        return _sync_api_object(getattr(actual_locator, "page", None))
                    page = getattr(impl, "page", None)
                    if page is not None:
                        return _sync_api_object(page)
                return _sync_api_object(getattr(target, "page", None))


            def _step_screenshot_path(payload):
                attempt = int(payload.get("attempt") or 1)
                sequence = int(payload.get("sequence_hint") or 0)
                step_type = str(payload.get("step_type") or "step")
                method_name = str(payload.get("method") or "action")
                safe_method = "".join(ch if ch.isalnum() else "-" for ch in method_name).strip("-") or "action"
                safe_type = "".join(ch if ch.isalnum() else "-" for ch in step_type).strip("-") or "step"
                folder = _SCREENSHOT_ROOT / f"attempt-{attempt}"
                folder.mkdir(parents=True, exist_ok=True)
                return folder / f"step-{sequence:03d}-{safe_type}-{safe_method}.png"


            def _capture_step_screenshot(target, payload):
                page = _resolve_page(target)
                if page is None:
                    return ""
                try:
                    path = _step_screenshot_path(payload)
                    page.screenshot(path=str(path), full_page=False)
                    return str(path.as_posix())
                except Exception:
                    return ""


            def _mask_value(locator, value, method_name):
                if method_name not in {"fill", "type"}:
                    return value
                lowered = locator.lower()
                if any(token in lowered for token in ("password", "passwd", "pwd", "密码")):
                    return "******"
                return value


            def _record(payload):
                global _SEQUENCE
                with _LOCK:
                    _SEQUENCE += 1
                    payload["sequence"] = _SEQUENCE
                    _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
                    with _OUTPUT_PATH.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


            def _wrap_method(owner, method_name, step_type, title, assertion=False):
                original = getattr(owner, method_name, None)
                if original is None or getattr(original, "_ui_step_wrapped", False):
                    return

                @functools.wraps(original)
                def wrapped(self, *args, **kwargs):
                    started = time.perf_counter()
                    locator = _target_text(self)
                    input_value = ""
                    expected_value = ""
                    if assertion:
                        expected_value = _safe_text(args[0]) if args else ""
                    elif method_name in {"goto", "set_content"}:
                        input_value = _safe_text(args[0]) if args else ""
                    elif method_name in {
                        "fill", "type", "press", "select_option", "set_input_files"
                    }:
                        input_value = _safe_text(args[0]) if args else ""
                    input_value = _mask_value(locator, input_value, method_name)

                    payload = {
                        "source": "runtime",
                        "attempt": int(os.environ.get("UI_AUTOMATION_ATTEMPT", "1")),
                        "step_type": step_type,
                        "step_title": title,
                        "method": method_name,
                        "locator": locator,
                        "input_value": input_value,
                        "expected_value": expected_value,
                        "status": "passed",
                        "duration_ms": 0,
                        "error_message": "",
                        "started_at": datetime.now(timezone.utc).isoformat(),
                        "sequence_hint": 0,
                        "screenshot_file": "",
                    }
                    try:
                        result = original(self, *args, **kwargs)
                    except BaseException as exc:
                        payload["status"] = "failed"
                        payload["error_message"] = _safe_text(exc, limit=4000)
                        raise
                    finally:
                        with _LOCK:
                            payload["sequence_hint"] = _SEQUENCE + 1
                        payload["screenshot_file"] = _capture_step_screenshot(self, payload)
                        payload["duration_ms"] = max(
                            1,
                            int((time.perf_counter() - started) * 1000),
                        )
                        _record(payload)
                    return result

                wrapped._ui_step_wrapped = True
                setattr(owner, method_name, wrapped)


            def install_recorder():
                global _INSTALLED
                if _INSTALLED:
                    return
                _INSTALLED = True

                for method_name, meta in PAGE_ACTIONS.items():
                    _wrap_method(Page, method_name, *meta)
                _wrap_method(Page, "wait_for_url", "wait", "Wait for page navigation")
                for method_name, meta in LOCATOR_ACTIONS.items():
                    _wrap_method(Locator, method_name, *meta)

                for assertion_class in (LocatorAssertions, PageAssertions):
                    for method_name in dir(assertion_class):
                        if method_name.startswith(("to_", "not_to_")):
                            _wrap_method(
                                assertion_class,
                                method_name,
                                "assert",
                                "断言结果",
                                assertion=True,
                            )
            '''
        ).strip() + "\n"

    @staticmethod
    def _build_command(run, output_dir, script_path):
        environment = (
            db.session.get(UiAutomationEnvironment, run.environment_id)
            if run.environment_id
            else None
        )
        browser_type = (run.browser_type or "chromium").lower()
        browser_engine = "chromium" if browser_type == "chrome" else browser_type
        command = [
            sys.executable,
            "-m",
            "pytest",
            str(script_path),
            "-q",
            "--disable-warnings",
            "--browser",
            browser_engine,
            "--output",
            str(output_dir),
            "--tracing",
            "retain-on-failure",
            "--video",
            "retain-on-failure",
            "--screenshot",
            "only-on-failure",
        ]
        if browser_type == "chrome":
            command.extend(["--browser-channel", "chrome"])
        if environment and environment.base_url:
            command.extend(["--base-url", environment.base_url])
        if environment and not environment.headless_default:
            command.append("--headed")
        return command

    @staticmethod
    def _artifact_type(path):
        name = path.name.lower()
        suffix = path.suffix.lower()
        if name == "execution.log":
            return "log"
        if name == "runtime-steps.jsonl":
            return "steps"
        if name == "test_script.py":
            return "script"
        if name == "conftest.py":
            return "config"
        if name == "trace.zip":
            return "trace"
        if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            return "screenshot"
        if suffix in {".webm", ".mp4"}:
            return "video"
        if suffix in {".xml", ".html", ".json"}:
            return "report"
        return "file"

    @staticmethod
    def _register_artifacts(run, workspace):
        UiAutomationArtifact.query.filter_by(run_id=run.id).delete()
        for path in sorted(item for item in workspace.rglob("*") if item.is_file()):
            if ".pytest_cache" in path.parts or "__pycache__" in path.parts:
                continue
            relative_path = path.relative_to(UiAutomationWorker.workspace_root()).as_posix()
            artifact = UiAutomationArtifact(
                run_id=run.id,
                artifact_type=UiAutomationWorker._artifact_type(path),
                file_name=path.name,
                file_path=relative_path,
                file_size=path.stat().st_size,
                mime_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            )
            db.session.add(artifact)

    @staticmethod
    def _summarize_step_title(step_type, source_line):
        if step_type == "navigate":
            return "打开页面"
        if step_type == "setup":
            return "准备页面"
        if step_type == "fill":
            return "填写字段"
        if step_type == "click":
            return "点击元素"
        if step_type == "assert":
            return "断言结果"
        if step_type == "wait":
            return "等待稳定"
        if step_type == "press":
            return "键盘输入"
        if step_type == "select":
            return "选择选项"
        if step_type == "hover":
            return "悬停操作"
        if step_type == "scroll":
            return "滚动页面"
        return "执行步骤"

    @staticmethod
    def _synthesize_run_steps(script_content):
        steps = []
        for raw_line in (script_content or "").splitlines():
            line = raw_line.strip()
            if not line or line.startswith(("from ", "import ", "def ", "class ", "@", "#")):
                continue
            if any(token in line for token in ("page.goto(", "page.reload(", "page.set_content(")):
                step_type = "navigate" if "goto(" in line else "setup"
            elif ".fill(" in line:
                step_type = "fill"
            elif ".click(" in line:
                step_type = "click"
            elif "expect(" in line:
                step_type = "assert"
            elif "wait_for_" in line:
                step_type = "wait"
            elif ".press(" in line:
                step_type = "press"
            elif ".select_option(" in line:
                step_type = "select"
            elif ".hover(" in line:
                step_type = "hover"
            elif ".scroll_into_view_if_needed(" in line or "mouse.wheel(" in line:
                step_type = "scroll"
            else:
                step_type = "step"

            steps.append(
                {
                    "step_type": step_type,
                    "step_title": UiAutomationWorker._summarize_step_title(step_type, line),
                    "locator": line,
                    "input_value": "",
                    "expected_value": "",
                    "raw_log": [
                        {
                            "source": "script",
                            "line": line,
                        }
                    ],
                }
            )

        if not steps:
            steps = [
                {
                    "step_type": "setup",
                    "step_title": "准备运行环境",
                    "locator": "worker",
                    "input_value": "",
                    "expected_value": "",
                    "raw_log": [{"source": "worker", "line": "prepare_runtime"}],
                },
                {
                    "step_type": "navigate",
                    "step_title": "启动并打开目标页面",
                    "locator": "worker",
                    "input_value": "",
                    "expected_value": "",
                    "raw_log": [{"source": "worker", "line": "launch_and_open"}],
                },
                {
                    "step_type": "assert",
                    "step_title": "收尾与结果校验",
                    "locator": "worker",
                    "input_value": "",
                    "expected_value": "",
                    "raw_log": [{"source": "worker", "line": "finish_and_assert"}],
                },
            ]

        return steps[:20]

    @staticmethod
    def _persist_run_steps(run, script_content):
        UiAutomationWorker._persist_collected_run_steps(run, script_content, [])

    @staticmethod
    def _load_runtime_steps(workspace):
        step_path = workspace / "runtime-steps.jsonl"
        if not step_path.is_file():
            return []

        steps = []
        for line in step_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                payload = json.loads(line)
            except (TypeError, ValueError):
                continue
            if isinstance(payload, dict):
                steps.append(payload)
        return sorted(
            steps,
            key=lambda item: (
                int(item.get("attempt") or 1),
                int(item.get("sequence") or 0),
            ),
        )

    @staticmethod
    def _persist_collected_run_steps(run, script_content, runtime_steps):
        UiAutomationRunStep.query.filter_by(run_id=run.id).delete()
        step_templates = list(runtime_steps) or UiAutomationWorker._synthesize_run_steps(script_content)
        if runtime_steps and run.status in {"failed", "timeout"}:
            if not any(item.get("status") == "failed" for item in step_templates):
                step_templates.append(
                    {
                        "attempt": int(run.retry_count or 0) + 1,
                        "step_type": "worker",
                        "step_title": "执行任务结束",
                        "method": "pytest",
                        "locator": "worker",
                        "input_value": "",
                        "expected_value": "",
                        "status": "failed",
                        "duration_ms": 0,
                        "error_message": run.error_message or "执行任务失败。",
                    }
                )
        total_steps = len(step_templates)
        duration_total = max(int(run.duration_ms or 0), total_steps * 100)
        base_duration = duration_total // total_steps if total_steps else 0
        remainder = duration_total - (base_duration * total_steps)

        for index, template in enumerate(step_templates, start=1):
            step_duration = int(
                template.get("duration_ms")
                or (base_duration + (1 if index <= remainder else 0))
            )
            step_status = str(template.get("status") or "passed")
            error_message = str(template.get("error_message") or "")[:4000]

            step = UiAutomationRunStep(
                run_id=run.id,
                step_index=index,
                step_type=template["step_type"],
                step_title=template["step_title"],
                locator=template.get("locator", ""),
                input_value=str(template.get("input_value") or ""),
                expected_value=str(template.get("expected_value") or ""),
                status=step_status,
                duration_ms=step_duration,
                error_message=error_message,
            )
            if runtime_steps:
                step.raw_log = template.get("raw_log") or [template]
            else:
                step.raw_log = [
                    {
                        "source": "runtime" if runtime_steps else "script",
                        "attempt": template.get("attempt", 1),
                        "method": template.get("method", ""),
                        "started_at": template.get("started_at", ""),
                        "screenshot_file": template.get("screenshot_file", ""),
                    }
                ]
            db.session.add(step)

    @staticmethod
    def resolve_artifact_path(artifact):
        root = UiAutomationWorker.workspace_root()
        target = (root / artifact.file_path).resolve()
        if root != target and root not in target.parents:
            raise ServiceError("执行产物路径不合法。")
        if not target.is_file():
            raise ServiceError("执行产物文件不存在。")
        return target

    @staticmethod
    def execute_run(run_id):
        run = UiAutomationWorker.get_run(run_id)
        if run.status == "running":
            raise ServiceError("该任务正在执行中。")
        if run.status not in {"queued", "failed", "timeout"}:
            raise ServiceError("当前状态不允许执行。")

        workspace = None
        version = None
        started = time.perf_counter()
        run.status = "running"
        run.started_at = datetime.utcnow()
        run.finished_at = None
        run.duration_ms = 0
        run.retry_count = 0
        run.error_message = ""
        run.error_stage = ""
        db.session.commit()

        try:
            UiAutomationWorker._validate_runtime()
            workspace, output_dir, script_path = UiAutomationWorker._prepare_workspace(run)
            version = db.session.get(UiAutomationScriptVersion, run.script_version_id)
            command = UiAutomationWorker._build_command(run, output_dir, script_path)
            timeout_seconds = int(
                current_app.config.get("UI_AUTOMATION_RUN_TIMEOUT", 300)
            )
            attempt_logs = []
            final_result = None
            total_attempts = max(1, int(run.max_retry or 0) + 1)

            for attempt in range(1, total_attempts + 1):
                attempt_started = time.perf_counter()
                try:
                    attempt_env = os.environ.copy()
                    environment = (
                        db.session.get(UiAutomationEnvironment, run.environment_id)
                        if run.environment_id
                        else None
                    )
                    if environment:
                        for key, value in (environment.runtime_variables or {}).items():
                            normalized_key = str(key or "").strip()
                            if normalized_key.startswith("UI_AUTOMATION_"):
                                attempt_env[normalized_key] = str(value or "")
                    attempt_env["UI_AUTOMATION_STEP_FILE"] = str(
                        workspace / "runtime-steps.jsonl"
                    )
                    attempt_env["UI_AUTOMATION_STEP_SCREENSHOT_DIR"] = str(
                        workspace / "step_screenshots"
                    )
                    attempt_env["UI_AUTOMATION_ATTEMPT"] = str(attempt)
                    result = subprocess.run(
                        command,
                        cwd=workspace,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=timeout_seconds,
                        env=attempt_env,
                    )
                    final_result = result
                    attempt_logs.append(
                        "\n".join(
                            [
                                f"=== Attempt {attempt}/{total_attempts} ===",
                                f"Command: {subprocess.list2cmdline(command)}",
                                f"Duration: {int((time.perf_counter() - attempt_started) * 1000)} ms",
                                f"Exit code: {result.returncode}",
                                "--- stdout ---",
                                result.stdout or "",
                                "--- stderr ---",
                                result.stderr or "",
                            ]
                        )
                    )
                    if result.returncode == 0:
                        break
                    run.retry_count = attempt if attempt < total_attempts else total_attempts - 1
                except subprocess.TimeoutExpired as exc:
                    attempt_logs.append(
                        "\n".join(
                            [
                                f"=== Attempt {attempt}/{total_attempts} ===",
                                f"Command: {subprocess.list2cmdline(command)}",
                                f"Timeout: {timeout_seconds} seconds",
                                "--- stdout ---",
                                str(exc.stdout or ""),
                                "--- stderr ---",
                                str(exc.stderr or ""),
                            ]
                        )
                    )
                    run.retry_count = attempt if attempt < total_attempts else total_attempts - 1
                    if attempt == total_attempts:
                        raise

            log_path = workspace / "execution.log"
            log_path.write_text("\n\n".join(attempt_logs), encoding="utf-8")

            passed = bool(final_result and final_result.returncode == 0)
            run.status = "passed" if passed else "failed"
            if not passed:
                run.error_stage = "pytest"
                output = (final_result.stdout or "") + "\n" + (final_result.stderr or "")
                run.error_message = output.strip()[-4000:] or "Playwright 脚本执行失败。"
        except subprocess.TimeoutExpired:
            run.status = "timeout"
            run.error_stage = "timeout"
            run.error_message = "Playwright 脚本执行超时。"
            if workspace:
                (workspace / "execution.log").write_text(
                    run.error_message,
                    encoding="utf-8",
                )
        except Exception as exc:
            run.status = "failed"
            run.error_stage = "worker"
            run.error_message = str(exc)
            if workspace:
                (workspace / "execution.log").write_text(
                    f"Worker error: {exc}",
                    encoding="utf-8",
                )
        finally:
            run.finished_at = datetime.utcnow()
            run.duration_ms = int((time.perf_counter() - started) * 1000)
            if workspace and workspace.exists():
                UiAutomationWorker._register_artifacts(run, workspace)
                db.session.flush()
            artifact_count = UiAutomationArtifact.query.filter_by(run_id=run.id).count()
            summary = dict(run.summary or {})
            summary.update(
                {
                    "worker_status": run.status,
                    "duration_ms": run.duration_ms,
                    "retry_count": run.retry_count,
                    "artifact_count": artifact_count,
                }
            )
            run.summary = summary
            try:
                script_content = version.script_content if version else ""
                runtime_steps = (
                    UiAutomationWorker._load_runtime_steps(workspace)
                    if workspace and workspace.exists()
                    else []
                )
                UiAutomationWorker._persist_collected_run_steps(
                    run,
                    script_content,
                    runtime_steps,
                )
                summary["step_count"] = len(runtime_steps) or len(
                    UiAutomationWorker._synthesize_run_steps(script_content)
                )
                summary["step_source"] = "runtime" if runtime_steps else "script"
                failure_analysis = {}
                if run.status in {"failed", "timeout"}:
                    try:
                        failure_analysis = UiAutomationService.analyze_run_failure(run)
                    except Exception:
                        failure_analysis = {}
                if failure_analysis:
                    summary["failure_analysis"] = failure_analysis
                    summary["failure_category"] = failure_analysis.get("category", "")
                    summary["failure_category_label"] = failure_analysis.get("category_label", "")
                    summary["failure_step_index"] = failure_analysis.get("step_index")
                    summary["failure_step_title"] = failure_analysis.get("step_title", "")
                    summary["failure_step_locator"] = failure_analysis.get("locator", "")
                    summary["failure_suggestion"] = failure_analysis.get("suggestion", "")
                run.summary = summary
            except Exception:
                pass
            db.session.commit()

        return run
