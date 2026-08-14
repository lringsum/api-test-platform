from __future__ import annotations

import importlib.util
import ast
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
import ctypes
from datetime import UTC, datetime
from pathlib import Path
from textwrap import dedent

from flask import current_app

from app import db
from app.models import (
    UiAutomationArtifact,
    UiAutomationEnvironment,
    UiAutomationRunStep,
    UiAutomationRun,
    UiAutomationScript,
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
    PASSED_RUN_DROP_ARTIFACT_TYPES = {"trace", "video"}

    @staticmethod
    def workspace_root():
        root = Path(current_app.instance_path) / "ui_automation" / "runs"
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()

    @staticmethod
    def worker_runtime_root():
        root = Path(current_app.instance_path) / "ui_automation" / "worker"
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()

    @staticmethod
    def worker_status_path():
        return UiAutomationWorker.worker_runtime_root() / "status.json"

    @staticmethod
    def worker_lock_path():
        return UiAutomationWorker.worker_runtime_root() / "worker.lock"

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).replace(tzinfo=None)

    @staticmethod
    def _to_isoformat(value):
        if not value:
            return ""
        return value.isoformat()

    @staticmethod
    def _parse_datetime(value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None

    @staticmethod
    def _seconds_since(value, now=None):
        parsed = UiAutomationWorker._parse_datetime(value)
        if not parsed:
            return None
        current = now or UiAutomationWorker._utc_now()
        return max(0.0, (current - parsed).total_seconds())

    @staticmethod
    def is_pid_running(pid):
        try:
            normalized_pid = int(pid or 0)
        except (TypeError, ValueError):
            return False
        if normalized_pid <= 0:
            return False
        if os.name == "nt":
            process_query_limited_information = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                process_query_limited_information,
                False,
                normalized_pid,
            )
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        try:
            os.kill(normalized_pid, 0)
        except OSError:
            return False
        return True

    @staticmethod
    def load_worker_status():
        path = UiAutomationWorker.worker_status_path()
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def write_worker_status(payload):
        path = UiAutomationWorker.worker_status_path()
        normalized = dict(payload or {})
        normalized.setdefault("updated_at", UiAutomationWorker._to_isoformat(UiAutomationWorker._utc_now()))
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(path)

    @staticmethod
    def get_worker_health():
        status = UiAutomationWorker.load_worker_status()
        now = UiAutomationWorker._utc_now()
        stale_seconds = int(
            current_app.config.get("UI_AUTOMATION_WORKER_STALE_SECONDS", 30)
        )
        heartbeat_age = UiAutomationWorker._seconds_since(
            status.get("last_heartbeat_at"),
            now=now,
        )
        pid_alive = UiAutomationWorker.is_pid_running(status.get("pid"))
        online = bool(status) and bool(pid_alive) and heartbeat_age is not None and heartbeat_age <= stale_seconds
        return {
            "online": online,
            "pid_alive": pid_alive,
            "state": str(status.get("state") or "offline"),
            "pid": status.get("pid"),
            "current_run_id": status.get("current_run_id"),
            "last_heartbeat_at": status.get("last_heartbeat_at", ""),
            "heartbeat_age_seconds": heartbeat_age,
            "stale_seconds": stale_seconds,
            "python_executable": status.get("python_executable", ""),
        }

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
    def list_running_runs():
        return (
            UiAutomationRun.query.filter_by(status="running")
            .order_by(UiAutomationRun.started_at.asc(), UiAutomationRun.id.asc())
            .all()
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
        preconditions = UiAutomationWorker._materialize_preconditions(version, workspace)
        UiAutomationWorker._write_runtime_config(run, workspace, preconditions)
        return workspace, output_dir, script_path

    @staticmethod
    def _infer_precondition_entrypoint(script_content):
        try:
            tree = ast.parse(script_content or "")
        except SyntaxError as exc:
            raise ServiceError(f"登录前置脚本语法错误：{exc}") from exc
        candidates = [
            node.name for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        ]
        if not candidates:
            raise ServiceError("登录前置脚本缺少可调用的 test_ 函数。")
        return candidates[0]

    @staticmethod
    def _materialize_preconditions(version, workspace):
        preconditions = []
        for dependency in version.dependencies or []:
            if not isinstance(dependency, dict):
                continue
            if dependency.get("role") != "login_precondition":
                continue
            try:
                script_id = int(dependency.get("script_id"))
            except (TypeError, ValueError):
                raise ServiceError("登录前置脚本依赖配置不合法。")
            script = db.session.get(UiAutomationScript, script_id)
            target_script = db.session.get(UiAutomationScript, version.script_id)
            if (
                not script
                or not target_script
                or script.project_id != target_script.project_id
            ):
                raise ServiceError("登录前置脚本不存在或不属于当前项目。")
            dependency_version = UiAutomationService._get_latest_script_version(script)
            if not dependency_version:
                raise ServiceError("登录前置脚本缺少可执行版本。")
            module_name = f"ui_precondition_{script.id}"
            module_path = workspace / f"{module_name}.py"
            module_path.write_text(dependency_version.script_content, encoding="utf-8")
            preconditions.append(
                {
                    "module": module_name,
                    "entrypoint": UiAutomationWorker._infer_precondition_entrypoint(
                        dependency_version.script_content
                    ),
                    "script_id": script.id,
                    "script_code": script.code,
                    "version": dependency_version.version_no,
                }
            )
        return preconditions

    @staticmethod
    def _find_chromium_executable():
        browser_root = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
        candidates = sorted(
            browser_root.glob("chromium-*/chrome-win*/chrome.exe"),
            reverse=True,
        )
        return candidates[0] if candidates else None

    @staticmethod
    def _write_runtime_config(run, workspace, preconditions=None):
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
        config_lines = [
                "import pytest",
                "from ui_step_recorder import install_recorder",
        ]
        for index, item in enumerate(preconditions or []):
            config_lines.append(
                f"from {item['module']} import {item['entrypoint']} as _platform_precondition_{index}"
            )
        config_lines.extend(
            [
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
        if preconditions:
            config_lines.extend(
                [
                    "",
                    "@pytest.fixture(autouse=True)",
                    "def platform_login_precondition(page, base_url):",
                ]
            )
            for index, _item in enumerate(preconditions):
                config_lines.append(f"    _platform_precondition_{index}(page, base_url)")
            config_lines.append("")
        config_content = "\n".join(config_lines)
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
            from contextlib import contextmanager
            from datetime import datetime, timezone
            from pathlib import Path

            from playwright.sync_api import Locator, LocatorAssertions, Page, PageAssertions


            _LOCK = threading.Lock()
            _SEQUENCE = 0
            _INSTALLED = False
            _STEP_LOCAL = threading.local()
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


            def _record(payload, reuse_sequence=False):
                global _SEQUENCE
                with _LOCK:
                    if not reuse_sequence:
                        _SEQUENCE += 1
                        payload["sequence"] = _SEQUENCE
                    _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
                    with _OUTPUT_PATH.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
                        handle.flush()


            def _step_stack():
                stack = getattr(_STEP_LOCAL, "stack", None)
                if stack is None:
                    stack = []
                    _STEP_LOCAL.stack = stack
                return stack


            def _current_step_meta():
                stack = _step_stack()
                return stack[-1] if stack else {}


            @contextmanager
            def step(title, step_type=None, input_value=None, expected_value=None, locator=None):
                stack = _step_stack()
                stack.append(
                    {
                        "title": _safe_text(title, limit=200),
                        "step_type": _safe_text(step_type, limit=50),
                        "input_value": _safe_text(input_value),
                        "expected_value": _safe_text(expected_value),
                        "locator": _safe_text(locator),
                    }
                )
                try:
                    yield
                finally:
                    stack.pop()


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
                    meta = _current_step_meta()
                    custom_title = str(meta.get("title") or "").strip()
                    custom_step_type = str(meta.get("step_type") or "").strip()
                    custom_input_value = str(meta.get("input_value") or "").strip()
                    custom_expected_value = str(meta.get("expected_value") or "").strip()
                    custom_locator = str(meta.get("locator") or "").strip()
                    custom_input_value = _mask_value(locator, custom_input_value, method_name)

                    payload = {
                        "source": "runtime",
                        "attempt": int(os.environ.get("UI_AUTOMATION_ATTEMPT", "1")),
                        "step_type": custom_step_type or step_type,
                        "step_title": custom_title or title,
                        "method": method_name,
                        "locator": custom_locator or locator,
                        "input_value": custom_input_value or input_value,
                        "expected_value": custom_expected_value or expected_value,
                        "status": "running",
                        "duration_ms": 0,
                        "error_message": "",
                        "started_at": datetime.now(timezone.utc).isoformat(),
                        "sequence_hint": 0,
                        "screenshot_file": "",
                    }
                    _record(payload)
                    try:
                        result = original(self, *args, **kwargs)
                        payload["status"] = "passed"
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
                        _record(payload, reuse_sequence=True)
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
    def _resolve_run_timeout_seconds(run):
        summary = dict(run.summary or {})
        configured_timeout = summary.get("configured_timeout_seconds")
        if configured_timeout not in (None, ""):
            try:
                timeout_seconds = int(configured_timeout)
            except (TypeError, ValueError):
                timeout_seconds = None
            if timeout_seconds is not None and 30 <= timeout_seconds <= 3600:
                return timeout_seconds, "run"

        environment = (
            db.session.get(UiAutomationEnvironment, run.environment_id)
            if run.environment_id
            else None
        )
        runtime_variables = (
            (environment.runtime_variables or {})
            if environment
            else {}
        )
        env_timeout = runtime_variables.get("UI_AUTOMATION_RUN_TIMEOUT")
        if env_timeout not in (None, ""):
            try:
                timeout_seconds = int(env_timeout)
            except (TypeError, ValueError):
                timeout_seconds = None
            if timeout_seconds is not None and 30 <= timeout_seconds <= 3600:
                return timeout_seconds, "environment"

        return int(current_app.config.get("UI_AUTOMATION_RUN_TIMEOUT", 300)), "config"

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
    def _remove_empty_parent_dirs(root, path):
        current = path.parent
        while current != root and current.exists():
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent

    @staticmethod
    def _prune_workspace_artifacts(workspace, artifact_types):
        normalized_types = {str(item or "").strip().lower() for item in artifact_types or set()}
        if not workspace or not workspace.exists() or not normalized_types:
            return []

        removed = []
        for path in sorted(item for item in workspace.rglob("*") if item.is_file()):
            if ".pytest_cache" in path.parts or "__pycache__" in path.parts:
                continue
            artifact_type = UiAutomationWorker._artifact_type(path)
            if artifact_type not in normalized_types:
                continue
            path.unlink(missing_ok=True)
            removed.append(path)
            UiAutomationWorker._remove_empty_parent_dirs(workspace, path)
        return removed

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
    def _delete_run_artifact_records(run_id):
        UiAutomationArtifact.query.filter_by(run_id=run_id).delete()

    @staticmethod
    def _cleanup_old_run_workspaces():
        runs = UiAutomationRun.query.order_by(
            UiAutomationRun.project_id.asc(),
            UiAutomationRun.id.desc(),
        ).all()

        kept_counts = {}
        stale_runs = []
        for run in runs:
            project_id = getattr(run, "project_id", None)
            keep_latest = UiAutomationService.get_artifact_keep_latest_runs(project_id)
            kept_count = kept_counts.get(project_id, 0)
            if kept_count < keep_latest:
                kept_counts[project_id] = kept_count + 1
                continue
            stale_runs.append(run)

        removed_run_ids = []
        workspace_root = UiAutomationWorker.workspace_root()
        for stale_run in stale_runs:
            workspace = workspace_root / str(stale_run.id)
            if workspace.exists():
                shutil.rmtree(workspace, ignore_errors=True)
            UiAutomationWorker._delete_run_artifact_records(stale_run.id)
            removed_run_ids.append(stale_run.id)
        return removed_run_ids

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

        steps_by_key = {}
        for line in step_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                payload = json.loads(line)
            except (TypeError, ValueError):
                continue
            if isinstance(payload, dict):
                key = (
                    int(payload.get("attempt") or 1),
                    int(payload.get("sequence") or 0),
                )
                steps_by_key[key] = payload
        return sorted(
            steps_by_key.values(),
            key=lambda item: (
                int(item.get("attempt") or 1),
                int(item.get("sequence") or 0),
            ),
        )

    @staticmethod
    def _sync_runtime_steps(run, runtime_steps, delete_stale=False, commit=True):
        templates = list(runtime_steps or [])
        existing_steps = {
            item.step_index: item
            for item in UiAutomationRunStep.query.filter_by(run_id=run.id).all()
        }
        retained_indexes = set()
        for index, template in enumerate(templates, start=1):
            retained_indexes.add(index)
            step = existing_steps.get(index)
            if step is None:
                step = UiAutomationRunStep(run_id=run.id, step_index=index)
                db.session.add(step)
            step.step_type = str(template.get("step_type") or "step")[:30]
            step.step_title = str(template.get("step_title") or f"步骤 {index}")[:150]
            step.locator = str(template.get("locator") or "")
            step.input_value = str(template.get("input_value") or "")
            step.expected_value = str(template.get("expected_value") or "")
            step.status = str(template.get("status") or "running")[:20]
            step.duration_ms = max(0, int(template.get("duration_ms") or 0))
            step.error_message = str(template.get("error_message") or "")[:4000]
            step.raw_log = template.get("raw_log") or [template]

        if delete_stale:
            for index, step in existing_steps.items():
                if index not in retained_indexes:
                    db.session.delete(step)
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return len(templates)

    @staticmethod
    def _persist_collected_run_steps(run, script_content, runtime_steps):
        if runtime_steps:
            step_templates = list(runtime_steps)
            if run.status in {"failed", "timeout"} and not any(
                item.get("status") == "failed" for item in step_templates
            ):
                step_templates.append(
                    {
                        "attempt": int(run.retry_count or 0) + 1,
                        "step_type": "worker",
                        "step_title": "执行任务结束",
                        "method": "pytest",
                        "locator": "worker",
                        "status": "failed",
                        "error_message": run.error_message or "执行任务失败。",
                    }
                )
            UiAutomationWorker._sync_runtime_steps(
                run,
                step_templates,
                delete_stale=True,
                commit=False,
            )
            return

        UiAutomationRunStep.query.filter_by(run_id=run.id).delete()
        step_templates = UiAutomationWorker._synthesize_run_steps(script_content)
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
    def _has_process_timed_out(
        started_at,
        last_progress_at,
        timeout_seconds,
        extend_on_progress,
        now,
    ):
        timeout_reference = last_progress_at if extend_on_progress else started_at
        return now - timeout_reference >= timeout_seconds

    @staticmethod
    def _run_observable_process(
        command,
        workspace,
        env,
        timeout_seconds,
        run,
        extend_on_progress=False,
    ):
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as stdout_file, tempfile.TemporaryFile(
            mode="w+", encoding="utf-8", errors="replace"
        ) as stderr_file:
            process = subprocess.Popen(
                command,
                cwd=workspace,
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            started = time.perf_counter()
            last_progress_at = started
            last_step_signature = None
            while True:
                runtime_steps = UiAutomationWorker._load_runtime_steps(workspace)
                step_signature = tuple(
                    (
                        int(item.get("attempt") or 1),
                        int(item.get("sequence") or 0),
                        str(item.get("status") or ""),
                        int(item.get("duration_ms") or 0),
                    )
                    for item in runtime_steps
                )
                if step_signature != last_step_signature:
                    UiAutomationWorker._sync_runtime_steps(run, runtime_steps)
                    last_step_signature = step_signature
                    if runtime_steps:
                        last_progress_at = time.perf_counter()

                return_code = process.poll()
                if return_code is not None:
                    stdout_file.seek(0)
                    stderr_file.seek(0)
                    final_steps = UiAutomationWorker._load_runtime_steps(workspace)
                    UiAutomationWorker._sync_runtime_steps(run, final_steps)
                    return subprocess.CompletedProcess(
                        command,
                        return_code,
                        stdout=stdout_file.read(),
                        stderr=stderr_file.read(),
                    )

                now = time.perf_counter()
                if UiAutomationWorker._has_process_timed_out(
                    started,
                    last_progress_at,
                    timeout_seconds,
                    extend_on_progress,
                    now,
                ):
                    process.kill()
                    process.wait()
                    stdout_file.seek(0)
                    stderr_file.seek(0)
                    final_steps = UiAutomationWorker._load_runtime_steps(workspace)
                    UiAutomationWorker._sync_runtime_steps(run, final_steps)
                    raise subprocess.TimeoutExpired(
                        command,
                        timeout_seconds,
                        output=stdout_file.read(),
                        stderr=stderr_file.read(),
                    )
                time.sleep(0.5)

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
    def _run_last_activity_at(run):
        workspace = UiAutomationWorker.workspace_root() / str(run.id)
        step_path = workspace / "runtime-steps.jsonl"
        if step_path.is_file():
            return datetime.fromtimestamp(step_path.stat().st_mtime, UTC).replace(tzinfo=None)
        if workspace.exists():
            return datetime.fromtimestamp(workspace.stat().st_mtime, UTC).replace(tzinfo=None)
        return UiAutomationWorker._parse_datetime(getattr(run, "started_at", None))

    @staticmethod
    def _should_recover_run(run, worker_health=None, now=None):
        current = now or UiAutomationWorker._utc_now()
        health = worker_health or {}
        if health.get("online"):
            return False
        stale_seconds = int(
            current_app.config.get("UI_AUTOMATION_RUN_STALE_SECONDS", 90)
        )
        last_activity = UiAutomationWorker._run_last_activity_at(run)
        if not last_activity:
            return False
        idle_seconds = max(0.0, (current - last_activity).total_seconds())
        return idle_seconds >= stale_seconds

    @staticmethod
    def recover_stale_runs():
        worker_health = UiAutomationWorker.get_worker_health()
        if worker_health.get("online"):
            return []

        now = UiAutomationWorker._utc_now()
        recovered_ids = []
        runs = UiAutomationWorker.list_running_runs()
        for run in runs:
            if not UiAutomationWorker._should_recover_run(
                run,
                worker_health=worker_health,
                now=now,
            ):
                continue
            run.status = "failed"
            run.error_stage = "worker"
            run.finished_at = now
            run.error_message = "Worker heartbeat lost; recovered stale running task."
            summary = dict(run.summary or {})
            summary["worker_status"] = "failed"
            summary["worker_recovered"] = True
            summary["worker_recovered_at"] = UiAutomationWorker._to_isoformat(now)
            summary["worker_recovery_reason"] = "stale_running_task"
            run.summary = summary
            recovered_ids.append(run.id)

        if recovered_ids:
            db.session.commit()
        return recovered_ids

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
        run.started_at = UiAutomationWorker._utc_now()
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
            timeout_seconds, timeout_source = (
                UiAutomationWorker._resolve_run_timeout_seconds(run)
            )
            summary = dict(run.summary or {})
            summary["effective_timeout_seconds"] = timeout_seconds
            summary["timeout_source"] = timeout_source
            summary["timeout_mode"] = (
                "inactivity" if timeout_source == "config" else "total"
            )
            run.summary = summary
            db.session.commit()
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
                    result = UiAutomationWorker._run_observable_process(
                        command,
                        workspace,
                        attempt_env,
                        timeout_seconds,
                        run,
                        extend_on_progress=timeout_source == "config",
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
                                f"Timeout source: {timeout_source}",
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
            effective_timeout = (
                dict(run.summary or {}).get("effective_timeout_seconds")
                or current_app.config.get("UI_AUTOMATION_RUN_TIMEOUT", 300)
            )
            timeout_mode = dict(run.summary or {}).get("timeout_mode")
            if timeout_mode == "inactivity":
                run.error_message = (
                    f"Playwright 脚本连续 {effective_timeout} 秒没有产生新步骤，执行超时。"
                )
            else:
                run.error_message = f"Playwright 脚本执行超时（{effective_timeout} 秒）。"
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
            run.finished_at = UiAutomationWorker._utc_now()
            run.duration_ms = int((time.perf_counter() - started) * 1000)
            if workspace and workspace.exists():
                if run.status == "passed":
                    UiAutomationWorker._prune_workspace_artifacts(
                        workspace,
                        UiAutomationWorker.PASSED_RUN_DROP_ARTIFACT_TYPES,
                    )
                UiAutomationWorker._register_artifacts(run, workspace)
                UiAutomationWorker._cleanup_old_run_workspaces()
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
