from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import ctypes
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree

import cv2
from flask import current_app
from appium import webdriver as appium_webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
import requests
from requests import exceptions as requests_exceptions
import numpy as np
from sqlalchemy.exc import OperationalError

from app import db
from app.models import AndroidUiTestRun
from app.services.android_ui_automation_service import AndroidUiAutomationService
from app.services.base_service import ServiceError


class AndroidUiAutomationWorker:
    DEFAULT_DEVICE_SENTINEL = "__default__"

    @staticmethod
    def workspace_root():
        root = Path(current_app.instance_path) / "android_ui_automation" / "runs"
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()

    @staticmethod
    def worker_runtime_root():
        root = Path(current_app.instance_path) / "android_ui_automation" / "worker"
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()

    @staticmethod
    def worker_status_path():
        return AndroidUiAutomationWorker.worker_runtime_root() / "status.json"

    @staticmethod
    def worker_lock_path():
        return AndroidUiAutomationWorker.worker_runtime_root() / "worker.lock"

    @staticmethod
    def device_preferences_path():
        return AndroidUiAutomationWorker.worker_runtime_root() / "device_preferences.json"

    @staticmethod
    def stop_requests_path():
        return AndroidUiAutomationWorker.worker_runtime_root() / "stop_requests.json"

    @staticmethod
    def apk_cache_root():
        root = Path(current_app.instance_path) / "android_ui_automation" / "apk_cache"
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()

    @staticmethod
    def apk_cache_manifest_path():
        return AndroidUiAutomationWorker.apk_cache_root() / "cache_manifest.json"

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
        parsed = AndroidUiAutomationWorker._parse_datetime(value)
        if not parsed:
            return None
        current = now or AndroidUiAutomationWorker._utc_now()
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
        path = AndroidUiAutomationWorker.worker_status_path()
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def write_worker_status(payload):
        path = AndroidUiAutomationWorker.worker_status_path()
        normalized = dict(payload or {})
        normalized.setdefault(
            "updated_at",
            AndroidUiAutomationWorker._to_isoformat(AndroidUiAutomationWorker._utc_now()),
        )
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(path)

    @staticmethod
    def load_stop_requests():
        path = AndroidUiAutomationWorker.stop_requests_path()
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        normalized = {}
        for key, value in payload.items():
            run_key = str(key or "").strip()
            if not run_key or not isinstance(value, dict):
                continue
            normalized[run_key] = {
                "requested_at": str(value.get("requested_at") or "").strip(),
                "requested_by": value.get("requested_by"),
                "reason": str(value.get("reason") or "").strip(),
            }
        return normalized

    @staticmethod
    def save_stop_requests(payload):
        path = AndroidUiAutomationWorker.stop_requests_path()
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(dict(payload or {}), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(path)

    @staticmethod
    def load_apk_cache_manifest():
        path = AndroidUiAutomationWorker.apk_cache_manifest_path()
        if not path.is_file():
            return {"sources": {}}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {"sources": {}}
        if not isinstance(payload, dict):
            return {"sources": {}}
        sources = payload.get("sources") or {}
        if not isinstance(sources, dict):
            sources = {}
        normalized = {}
        for key, value in sources.items():
            source_key = str(key or "").strip()
            if not source_key or not isinstance(value, dict):
                continue
            normalized[source_key] = {
                "cache_path": str(value.get("cache_path") or "").strip(),
                "package_name": str(value.get("package_name") or "").strip(),
                "updated_at": str(value.get("updated_at") or "").strip(),
            }
        return {"sources": normalized}

    @staticmethod
    def save_apk_cache_manifest(payload):
        path = AndroidUiAutomationWorker.apk_cache_manifest_path()
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(dict(payload or {"sources": {}}), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(path)

    @staticmethod
    def _apk_source_key(url):
        text = str(url or "").strip()
        if not text:
            return ""
        local_source = Path(text).expanduser()
        if local_source.is_file():
            try:
                normalized = str(local_source.resolve())
            except OSError:
                normalized = str(local_source)
            return f"local:{normalized}"
        return f"url:{text}"

    @staticmethod
    def _sanitize_cache_name(value, fallback="download"):
        text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip()).strip("._-")
        return text or fallback

    @staticmethod
    def _source_cache_path(url):
        parsed = urlparse(str(url or "").strip())
        filename = Path(parsed.path or "").name or "download.apk"
        if not filename.lower().endswith(".apk"):
            filename = f"{filename}.apk"
        digest = hashlib.sha1(str(url or "").strip().encode("utf-8")).hexdigest()[:12]
        safe_name = AndroidUiAutomationWorker._sanitize_cache_name(Path(filename).stem, "download")
        return AndroidUiAutomationWorker.apk_cache_root() / f"src__{digest}__{safe_name}.apk"

    @staticmethod
    def _package_cache_path(package_name):
        safe_name = AndroidUiAutomationWorker._sanitize_cache_name(package_name, "package")
        return AndroidUiAutomationWorker.apk_cache_root() / f"pkg__{safe_name}.apk"

    @staticmethod
    def _lookup_cached_apk(url):
        source_key = AndroidUiAutomationWorker._apk_source_key(url)
        if not source_key:
            return None
        manifest = AndroidUiAutomationWorker.load_apk_cache_manifest()
        entry = (manifest.get("sources") or {}).get(source_key) or {}
        cache_path = Path(str(entry.get("cache_path") or "").strip())
        if cache_path and cache_path.is_file():
            return cache_path.resolve()
        return None

    @staticmethod
    def _record_cached_apk(url, cache_path, package_name=""):
        source_key = AndroidUiAutomationWorker._apk_source_key(url)
        if not source_key:
            return
        manifest = AndroidUiAutomationWorker.load_apk_cache_manifest()
        sources = manifest.setdefault("sources", {})
        sources[source_key] = {
            "cache_path": str(Path(cache_path).resolve()),
            "package_name": str(package_name or "").strip(),
            "updated_at": AndroidUiAutomationWorker._to_isoformat(
                AndroidUiAutomationWorker._utc_now()
            ),
        }
        AndroidUiAutomationWorker.save_apk_cache_manifest(manifest)

    @staticmethod
    def request_stop_run(run_id, requested_by=None, reason="manual_stop"):
        run = AndroidUiAutomationWorker.get_run(run_id)
        if run.status == "pending":
            AndroidUiAutomationService.mark_run_failed(
                run.id,
                stage=run.stage or "queued",
                error_type="manual_stop",
                error_message="任务已手动停止，未进入执行。",
            )
            AndroidUiAutomationWorker.clear_stop_request(run.id)
            return {"run_id": run.id, "state": "stopped"}
        if run.status != "running":
            raise ServiceError("只有排队中或执行中的记录可以手动停止。")
        requests_map = AndroidUiAutomationWorker.load_stop_requests()
        requests_map[str(run.id)] = {
            "requested_at": AndroidUiAutomationWorker._to_isoformat(
                AndroidUiAutomationWorker._utc_now()
            ),
            "requested_by": requested_by,
            "reason": str(reason or "manual_stop").strip(),
        }
        AndroidUiAutomationWorker.save_stop_requests(requests_map)
        return {"run_id": run.id, "state": "requested"}

    @staticmethod
    def _remove_worker_lock_if_stale(expected_pid=None):
        lock_path = AndroidUiAutomationWorker.worker_lock_path()
        if not lock_path.is_file():
            return False
        try:
            payload = json.loads(lock_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            payload = {}
        lock_pid = payload.get("pid")
        if expected_pid is not None and str(lock_pid or "") != str(expected_pid):
            return False
        if AndroidUiAutomationWorker.is_pid_running(lock_pid):
            return False
        try:
            lock_path.unlink()
        except FileNotFoundError:
            return False
        return True

    @staticmethod
    def terminate_worker_process(pid):
        try:
            normalized_pid = int(pid or 0)
        except (TypeError, ValueError):
            return False
        if normalized_pid <= 0:
            return False
        if not AndroidUiAutomationWorker.is_pid_running(normalized_pid):
            AndroidUiAutomationWorker._remove_worker_lock_if_stale(expected_pid=normalized_pid)
            return False

        if os.name == "nt":
            completed = subprocess.run(
                ["taskkill", "/PID", str(normalized_pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
            success = completed.returncode == 0
        else:
            try:
                os.kill(normalized_pid, 9)
                success = True
            except OSError:
                success = False

        for _ in range(20):
            if not AndroidUiAutomationWorker.is_pid_running(normalized_pid):
                break
            time.sleep(0.25)
        AndroidUiAutomationWorker._remove_worker_lock_if_stale(expected_pid=normalized_pid)
        return not AndroidUiAutomationWorker.is_pid_running(normalized_pid) and success

    @staticmethod
    def start_worker_process():
        project_root = Path(current_app.root_path).resolve().parent
        status_payload = AndroidUiAutomationWorker.load_worker_status()
        python_executable = str(status_payload.get("python_executable") or "").strip()
        script_path = str(status_payload.get("script") or "").strip()

        if not python_executable:
            venv_python = project_root / ".venv" / "Scripts" / "python.exe"
            python_executable = str(venv_python if venv_python.is_file() else Path(sys.executable).resolve())
        if not script_path:
            script_path = str((project_root / "scripts" / "run_android_ui_automation_worker.py").resolve())

        command = [python_executable, script_path]
        popen_kwargs = {
            "cwd": str(project_root),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if os.name == "nt":
            creationflags = 0x00000008 | 0x00000200 | 0x08000000
            popen_kwargs["creationflags"] = creationflags
        else:
            popen_kwargs["start_new_session"] = True

        process = subprocess.Popen(command, **popen_kwargs)
        return {
            "pid": process.pid,
            "python_executable": python_executable,
            "script": script_path,
        }

    @staticmethod
    def force_stop_run(run_id, requested_by=None, reason="manual_stop"):
        run = AndroidUiAutomationWorker.get_run(run_id)
        if run.status == "pending":
            AndroidUiAutomationService.mark_run_failed(
                run.id,
                stage=run.stage or "queued",
                error_type="manual_stop",
                error_message="任务已手动终止，未进入执行。",
            )
            AndroidUiAutomationWorker.clear_stop_request(run.id)
            return {"run_id": run.id, "state": "stopped", "worker_restarted": False}
        if run.status != "running":
            raise ServiceError("只有排队中或执行中的记录才可以手动停止。")

        worker_health = AndroidUiAutomationWorker.get_worker_health()
        worker_pid = worker_health.get("pid")
        worker_run_id = worker_health.get("current_run_id")
        same_run = str(worker_run_id or "") == str(run.id)
        worker_terminated = False
        worker_restarted = False

        if same_run and worker_pid:
            worker_terminated = AndroidUiAutomationWorker.terminate_worker_process(worker_pid)

        AndroidUiAutomationService.mark_run_failed(
            run.id,
            stage=run.stage or "finished",
            error_type=str(reason or "manual_stop").strip() or "manual_stop",
            error_message="任务已被手动终止。",
        )
        AndroidUiAutomationWorker.clear_stop_request(run.id)

        if same_run:
            AndroidUiAutomationWorker.write_worker_status(
                {
                    "pid": None,
                    "state": "stopped",
                    "current_run_id": None,
                    "last_error": "任务已被手动终止。",
                    "current_stage": "",
                    "progress_text": "",
                    "progress_percent": None,
                    "current_task_name": "",
                    "python_executable": worker_health.get("python_executable") or "",
                    "script": worker_health.get("script") or "",
                }
            )

        if same_run or not worker_health.get("online"):
            restarted = AndroidUiAutomationWorker.start_worker_process()
            worker_restarted = bool(restarted.get("pid"))

        return {
            "run_id": run.id,
            "state": "stopped",
            "worker_terminated": worker_terminated,
            "worker_restarted": worker_restarted,
            "requested_by": requested_by,
        }

    @staticmethod
    def clear_stop_request(run_id):
        requests_map = AndroidUiAutomationWorker.load_stop_requests()
        removed = requests_map.pop(str(run_id), None)
        if removed is not None or requests_map:
            AndroidUiAutomationWorker.save_stop_requests(requests_map)
        return removed

    @staticmethod
    def is_stop_requested(run_id):
        if not run_id:
            return False
        return str(run_id) in AndroidUiAutomationWorker.load_stop_requests()

    @staticmethod
    def raise_if_stop_requested(run_id):
        if AndroidUiAutomationWorker.is_stop_requested(run_id):
            raise ServiceError("执行已被手动停止。")

    @staticmethod
    def load_device_preferences():
        path = AndroidUiAutomationWorker.device_preferences_path()
        if not path.is_file():
            return {
                "default_device_serial": "",
                "disabled_devices": [],
                "device_health": {},
                "device_annotations": {},
            }
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {
                "default_device_serial": "",
                "disabled_devices": [],
                "device_health": {},
                "device_annotations": {},
            }
        if not isinstance(payload, dict):
            return {
                "default_device_serial": "",
                "disabled_devices": [],
                "device_health": {},
                "device_annotations": {},
            }
        disabled_devices = payload.get("disabled_devices") or []
        if not isinstance(disabled_devices, list):
            disabled_devices = []
        device_health = payload.get("device_health") or {}
        if not isinstance(device_health, dict):
            device_health = {}
        device_annotations = payload.get("device_annotations") or {}
        if not isinstance(device_annotations, dict):
            device_annotations = {}
        return {
            "default_device_serial": str(payload.get("default_device_serial") or "").strip(),
            "disabled_devices": [str(item).strip() for item in disabled_devices if str(item).strip()],
            "device_health": {
                str(serial).strip(): value
                for serial, value in device_health.items()
                if str(serial).strip() and isinstance(value, dict)
            },
            "device_annotations": {
                str(serial).strip(): value
                for serial, value in device_annotations.items()
                if str(serial).strip() and isinstance(value, dict)
            },
        }

    @staticmethod
    def save_device_preferences(
        default_device_serial=None,
        disabled_devices=None,
        device_health=None,
        device_annotations=None,
    ):
        current = AndroidUiAutomationWorker.load_device_preferences()
        if default_device_serial is not None:
            current["default_device_serial"] = str(default_device_serial or "").strip()
        if disabled_devices is not None:
            current["disabled_devices"] = [
                str(item).strip()
                for item in disabled_devices
                if str(item).strip()
            ]
        if device_health is not None:
            normalized_health = {}
            for serial, value in device_health.items():
                serial_text = str(serial or "").strip()
                if not serial_text or not isinstance(value, dict):
                    continue
                normalized_health[serial_text] = {
                    "status": str(value.get("status") or "").strip(),
                    "message": str(value.get("message") or "").strip(),
                    "checked_at": str(value.get("checked_at") or "").strip(),
                }
            current["device_health"] = normalized_health
        if device_annotations is not None:
            normalized_annotations = {}
            for serial, value in device_annotations.items():
                serial_text = str(serial or "").strip()
                if not serial_text or not isinstance(value, dict):
                    continue
                normalized_annotations[serial_text] = {
                    "tag": str(value.get("tag") or "").strip(),
                    "note": str(value.get("note") or "").strip(),
                    "updated_at": str(value.get("updated_at") or "").strip(),
                }
            current["device_annotations"] = normalized_annotations
        path = AndroidUiAutomationWorker.device_preferences_path()
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(current, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(path)
        return current

    @staticmethod
    def set_default_device(serial):
        prefs = AndroidUiAutomationWorker.load_device_preferences()
        serial = str(serial or "").strip()
        if serial and serial in prefs["disabled_devices"]:
            prefs["disabled_devices"] = [item for item in prefs["disabled_devices"] if item != serial]
        prefs["default_device_serial"] = serial
        return AndroidUiAutomationWorker.save_device_preferences(
            default_device_serial=prefs["default_device_serial"],
            disabled_devices=prefs["disabled_devices"],
            device_health=prefs.get("device_health") or {},
            device_annotations=prefs.get("device_annotations") or {},
        )

    @staticmethod
    def toggle_device_disabled(serial):
        prefs = AndroidUiAutomationWorker.load_device_preferences()
        serial = str(serial or "").strip()
        disabled = set(prefs["disabled_devices"])
        if serial in disabled:
            disabled.remove(serial)
            is_disabled = False
        else:
            disabled.add(serial)
            if prefs["default_device_serial"] == serial:
                prefs["default_device_serial"] = ""
            is_disabled = True
        AndroidUiAutomationWorker.save_device_preferences(
            default_device_serial=prefs["default_device_serial"],
            disabled_devices=sorted(disabled),
            device_health=prefs.get("device_health") or {},
            device_annotations=prefs.get("device_annotations") or {},
        )
        return is_disabled

    @staticmethod
    def set_device_disabled(serial, disabled):
        prefs = AndroidUiAutomationWorker.load_device_preferences()
        serial = str(serial or "").strip()
        if not serial:
            raise ServiceError("设备序列号不能为空。")
        disabled_devices = set(prefs["disabled_devices"])
        if disabled:
            disabled_devices.add(serial)
            if prefs["default_device_serial"] == serial:
                prefs["default_device_serial"] = ""
        else:
            disabled_devices.discard(serial)
        AndroidUiAutomationWorker.save_device_preferences(
            default_device_serial=prefs["default_device_serial"],
            disabled_devices=sorted(disabled_devices),
            device_health=prefs.get("device_health") or {},
            device_annotations=prefs.get("device_annotations") or {},
        )
        return bool(disabled)

    @staticmethod
    def update_device_health(serial, status, message=""):
        prefs = AndroidUiAutomationWorker.load_device_preferences()
        serial = str(serial or "").strip()
        if not serial:
            return prefs
        device_health = dict(prefs.get("device_health") or {})
        device_health[serial] = {
            "status": str(status or "").strip(),
            "message": str(message or "").strip(),
            "checked_at": AndroidUiAutomationWorker._to_isoformat(AndroidUiAutomationWorker._utc_now()),
        }
        return AndroidUiAutomationWorker.save_device_preferences(
            default_device_serial=prefs.get("default_device_serial") or "",
            disabled_devices=prefs.get("disabled_devices") or [],
            device_health=device_health,
            device_annotations=prefs.get("device_annotations") or {},
        )

    @staticmethod
    def update_device_annotation(serial, tag="", note=""):
        prefs = AndroidUiAutomationWorker.load_device_preferences()
        serial = str(serial or "").strip()
        if not serial:
            raise ServiceError("设备序列号不能为空。")
        device_annotations = dict(prefs.get("device_annotations") or {})
        tag_text = str(tag or "").strip()
        note_text = str(note or "").strip()
        if not tag_text and not note_text:
            device_annotations.pop(serial, None)
        else:
            device_annotations[serial] = {
                "tag": tag_text,
                "note": note_text,
                "updated_at": AndroidUiAutomationWorker._to_isoformat(AndroidUiAutomationWorker._utc_now()),
            }
        return AndroidUiAutomationWorker.save_device_preferences(
            default_device_serial=prefs.get("default_device_serial") or "",
            disabled_devices=prefs.get("disabled_devices") or [],
            device_health=prefs.get("device_health") or {},
            device_annotations=device_annotations,
        )

    @staticmethod
    def get_worker_health():
        status = AndroidUiAutomationWorker.load_worker_status()
        now = AndroidUiAutomationWorker._utc_now()
        stale_seconds = int(
            current_app.config.get("ANDROID_UI_WORKER_STALE_SECONDS", 30)
        )
        heartbeat_age = AndroidUiAutomationWorker._seconds_since(
            status.get("last_heartbeat_at"),
            now=now,
        )
        pid_alive = AndroidUiAutomationWorker.is_pid_running(status.get("pid"))
        online = bool(status) and bool(pid_alive) and heartbeat_age is not None and heartbeat_age <= stale_seconds
        return {
            "online": online,
            "pid_alive": pid_alive,
            "state": str(status.get("state") or "offline"),
            "pid": status.get("pid"),
            "current_run_id": status.get("current_run_id"),
            "current_stage": str(status.get("current_stage") or ""),
            "progress_text": str(status.get("progress_text") or ""),
            "progress_percent": status.get("progress_percent"),
            "current_task_name": str(status.get("current_task_name") or ""),
            "last_error": str(status.get("last_error") or ""),
            "last_heartbeat_at": status.get("last_heartbeat_at", ""),
            "heartbeat_age_seconds": heartbeat_age,
            "stale_seconds": stale_seconds,
            "python_executable": status.get("python_executable", ""),
        }

    @staticmethod
    def _simple_run(command, timeout=20):
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )

    @staticmethod
    def get_run(run_id):
        run = db.session.get(AndroidUiTestRun, run_id)
        if not run:
            raise ServiceError("Android UI 执行记录不存在。")
        return run

    @staticmethod
    def get_next_queued_run():
        try:
            return (
                AndroidUiTestRun.query.filter_by(status="pending")
                .order_by(AndroidUiTestRun.created_at.asc(), AndroidUiTestRun.id.asc())
                .first()
            )
        except OperationalError as exc:
            raise ServiceError("Android UI 自动化数据表尚未创建，请先执行数据库迁移。") from exc

    @staticmethod
    def list_running_runs():
        try:
            return (
                AndroidUiTestRun.query.filter_by(status="running")
                .order_by(AndroidUiTestRun.started_at.asc(), AndroidUiTestRun.id.asc())
                .all()
            )
        except OperationalError as exc:
            raise ServiceError("Android UI 自动化数据表尚未创建，请先执行数据库迁移。") from exc

    @staticmethod
    def resolve_adb_path():
        configured = str(current_app.config.get("ANDROID_UI_ADB_PATH") or "").strip()
        candidates = [
            configured,
            os.environ.get("ANDROID_UI_ADB_PATH", ""),
            r"C:\Program Files\Netease\MuMu\nx_main\adb.exe",
            r"C:\Program Files\Netease\MuMu\nx_main\adb",
            "adb",
        ]
        for candidate in candidates:
            if not candidate:
                continue
            if candidate == "adb":
                return candidate
            path = Path(candidate)
            if path.is_file():
                return str(path)
        raise ServiceError("未找到 adb，可在配置中设置 ANDROID_UI_ADB_PATH。")

    @staticmethod
    def resolve_mumu_cli_path(adb_path=""):
        normalized_adb_path = str(adb_path or "").strip() or AndroidUiAutomationWorker.resolve_adb_path()
        adb_file = Path(normalized_adb_path)
        candidates = [
            adb_file.parent / "mumu-cli.exe",
            adb_file.parent / "MuMuManager.exe",
            Path(r"C:\Program Files\Netease\MuMu\nx_main\mumu-cli.exe"),
            Path(r"C:\Program Files\Netease\MuMu\nx_main\MuMuManager.exe"),
        ]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        raise ServiceError("未找到 MuMu CLI，当前平台还不能自动拉起模拟器。")

    @staticmethod
    def _parse_serial_host_port(serial):
        normalized = str(serial or "").strip()
        if ":" not in normalized:
            raise ServiceError(f"设备序列号不支持自动拉起：{normalized or '-'}")
        host, port_text = normalized.rsplit(":", 1)
        host = host.strip()
        try:
            port = int(port_text.strip())
        except (TypeError, ValueError) as exc:
            raise ServiceError(f"设备序列号端口无效：{normalized}") from exc
        if not host:
            raise ServiceError(f"设备序列号不支持自动拉起：{normalized}")
        return host, port

    @staticmethod
    def _list_mumu_instances(mumu_cli_path):
        result = AndroidUiAutomationWorker._simple_run(
            [mumu_cli_path, "info", "--vmindex", "all"],
            timeout=20,
        )
        if result.returncode != 0:
            raise ServiceError(f"读取 MuMu 实例信息失败：{result.stderr.strip() or result.stdout.strip()}")
        try:
            payload = json.loads(result.stdout or "{}")
        except (TypeError, ValueError) as exc:
            raise ServiceError("读取 MuMu 实例信息失败：返回结果不是合法 JSON。") from exc
        if not isinstance(payload, dict):
            raise ServiceError("读取 MuMu 实例信息失败：实例列表格式无效。")
        return payload

    @staticmethod
    def _pick_mumu_vmindex_for_serial(mumu_instances, serial):
        host, port = AndroidUiAutomationWorker._parse_serial_host_port(serial)
        matched_index = None
        fallback_main_index = None
        fallback_single_index = None
        normalized_items = []
        for index, raw_item in (mumu_instances or {}).items():
            if not isinstance(raw_item, dict):
                continue
            item = dict(raw_item)
            item["index"] = str(item.get("index") or index)
            normalized_items.append(item)
        if len(normalized_items) == 1:
            fallback_single_index = normalized_items[0]["index"]
        for item in normalized_items:
            index = item["index"]
            if bool(item.get("is_main")) and fallback_main_index is None:
                fallback_main_index = index
            item_host = str(item.get("adb_host_ip") or "").strip()
            try:
                item_port = int(item.get("adb_port"))
            except (TypeError, ValueError):
                item_port = None
            if item_host == host and item_port == port:
                matched_index = index
                break
        if matched_index is not None:
            return matched_index
        if host == "127.0.0.1" and fallback_main_index is not None:
            return fallback_main_index
        if fallback_single_index is not None:
            return fallback_single_index
        raise ServiceError(f"无法根据设备序列号匹配 MuMu 实例：{serial}")

    @staticmethod
    def _launch_mumu_instance(mumu_cli_path, vmindex):
        result = AndroidUiAutomationWorker._simple_run(
            [mumu_cli_path, "control", "--vmindex", str(vmindex), "launch"],
            timeout=30,
        )
        if result.returncode != 0:
            raise ServiceError(f"启动 MuMu 实例失败：{result.stderr.strip() or result.stdout.strip()}")
        return result

    @staticmethod
    def _adb_connect(adb_path, serial):
        result = AndroidUiAutomationWorker._simple_run(
            [adb_path, "connect", str(serial or "").strip()],
            timeout=20,
        )
        if result.returncode != 0:
            raise ServiceError(f"adb connect 失败：{result.stderr.strip() or result.stdout.strip()}")
        return result

    @staticmethod
    def bring_device_online(serial, wait_seconds=45):
        normalized_serial = str(serial or "").strip()
        if not normalized_serial:
            raise ServiceError("设备序列号不能为空。")
        try:
            result = AndroidUiAutomationWorker.test_device_connection(normalized_serial)
            result["auto_started"] = False
            return result
        except ServiceError:
            pass

        adb_path = AndroidUiAutomationWorker.resolve_adb_path()
        mumu_cli_path = AndroidUiAutomationWorker.resolve_mumu_cli_path(adb_path)
        mumu_instances = AndroidUiAutomationWorker._list_mumu_instances(mumu_cli_path)
        vmindex = AndroidUiAutomationWorker._pick_mumu_vmindex_for_serial(mumu_instances, normalized_serial)
        AndroidUiAutomationWorker._launch_mumu_instance(mumu_cli_path, vmindex)

        deadline = time.time() + max(5, int(wait_seconds or 45))
        last_error = ""
        while time.time() < deadline:
            try:
                AndroidUiAutomationWorker._adb_connect(adb_path, normalized_serial)
            except ServiceError as exc:
                last_error = str(exc)
            try:
                result = AndroidUiAutomationWorker.test_device_connection(normalized_serial)
                result["auto_started"] = True
                result["vmindex"] = str(vmindex)
                return result
            except ServiceError as exc:
                last_error = str(exc)
                time.sleep(2)
        raise ServiceError(last_error or f"等待设备上线超时：{normalized_serial}")

    @staticmethod
    def bring_default_device_online(wait_seconds=45):
        prefs = AndroidUiAutomationWorker.load_device_preferences()
        default_serial = str(prefs.get("default_device_serial") or "").strip()
        if not default_serial:
            raise ServiceError("当前没有默认设备，无法一键拉起。")
        return AndroidUiAutomationWorker.bring_device_online(default_serial, wait_seconds=wait_seconds)

    @staticmethod
    def resolve_aapt_path():
        configured = str(current_app.config.get("ANDROID_UI_AAPT_PATH") or "").strip()
        candidates = [
            configured,
            os.environ.get("ANDROID_UI_AAPT_PATH", ""),
        ]
        android_homes = [
            os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT"),
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk"),
        ]
        for android_home in android_homes:
            if not android_home:
                continue
            build_tools_root = Path(android_home) / "build-tools"
            if build_tools_root.is_dir():
                versions = sorted(build_tools_root.iterdir(), reverse=True)
                for version_dir in versions:
                    candidates.append(str(version_dir / "aapt.exe"))
                    candidates.append(str(version_dir / "aapt"))
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate)
            if path.is_file():
                return str(path)
        raise ServiceError("未找到 aapt，请安装 Android SDK build-tools，或在配置中设置 ANDROID_UI_AAPT_PATH。")

    @staticmethod
    def validate_runtime_dependencies():
        """Resolve the tools required before a run mutates device or run state."""
        return {
            "adb_path": AndroidUiAutomationWorker.resolve_adb_path(),
            "aapt_path": AndroidUiAutomationWorker.resolve_aapt_path(),
        }

    @staticmethod
    def _prepare_workspace(run):
        workspace = AndroidUiAutomationWorker.workspace_root() / str(run.id)
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace

    @staticmethod
    def _log_line(lines, text):
        lines.append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {text}")

    @staticmethod
    def _flush_log(workspace, lines):
        path = workspace / "execution.log"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    @staticmethod
    def _pick_device(adb_path, expected_serial=""):
        devices = AndroidUiAutomationWorker._list_connected_devices(adb_path)
        preferences = AndroidUiAutomationWorker.load_device_preferences()
        disabled_devices = set(preferences.get("disabled_devices") or [])
        normalized_expected_serial = str(expected_serial or "").strip()
        if normalized_expected_serial == AndroidUiAutomationWorker.DEFAULT_DEVICE_SENTINEL:
            normalized_expected_serial = ""
        if normalized_expected_serial:
            for device in devices:
                if device["serial"] == normalized_expected_serial:
                    if normalized_expected_serial in disabled_devices:
                        raise ServiceError(f"目标设备已被禁用：{normalized_expected_serial}")
                    return device
            raise ServiceError(f"未找到目标设备：{normalized_expected_serial}")
        enabled_devices = [device for device in devices if device["serial"] not in disabled_devices]
        if not enabled_devices:
            raise ServiceError("当前没有已连接的 Android 设备。")
        default_device_serial = str(preferences.get("default_device_serial") or "").strip()
        if default_device_serial:
            for device in enabled_devices:
                if device["serial"] == default_device_serial:
                    return device
        if len(enabled_devices) > 1:
            raise ServiceError("检测到多个设备，请在任务中指定 device_serial。")
        return enabled_devices[0]

    @staticmethod
    def _auto_start_serial(expected_serial=""):
        normalized_serial = str(expected_serial or "").strip()
        if normalized_serial == AndroidUiAutomationWorker.DEFAULT_DEVICE_SENTINEL:
            normalized_serial = ""
        if not normalized_serial:
            preferences = AndroidUiAutomationWorker.load_device_preferences()
            normalized_serial = str(
                preferences.get("default_device_serial") or ""
            ).strip()
        if not normalized_serial:
            return ""
        try:
            host, _port = AndroidUiAutomationWorker._parse_serial_host_port(
                normalized_serial
            )
        except ServiceError:
            return ""
        return normalized_serial if host.lower() in {"127.0.0.1", "localhost"} else ""

    @staticmethod
    def _pick_device_with_auto_start(
        adb_path,
        expected_serial="",
        log_lines=None,
        progress_callback=None,
        task_name="",
    ):
        try:
            return AndroidUiAutomationWorker._pick_device(adb_path, expected_serial)
        except ServiceError as selection_error:
            if not current_app.config.get("ANDROID_UI_AUTO_START_DEVICE", True):
                raise

            serial = AndroidUiAutomationWorker._auto_start_serial(expected_serial)
            if not serial:
                raise

            wait_seconds = max(
                5,
                int(
                    current_app.config.get(
                        "ANDROID_UI_DEVICE_START_WAIT_SECONDS",
                        90,
                    )
                ),
            )
            if log_lines is not None:
                AndroidUiAutomationWorker._log_line(
                    log_lines,
                    f"device unavailable: {selection_error}; auto-starting MuMu for {serial}",
                )
            if progress_callback:
                progress_callback(
                    stage="queued",
                    task_name=task_name,
                    progress_text="目标设备离线，正在自动启动 MuMu",
                    progress_percent=None,
                )
            try:
                AndroidUiAutomationWorker.bring_device_online(
                    serial,
                    wait_seconds=wait_seconds,
                )
            except ServiceError as auto_start_error:
                if log_lines is not None:
                    AndroidUiAutomationWorker._log_line(
                        log_lines,
                        f"device auto-start failed: {auto_start_error}",
                    )
                raise ServiceError(
                    f"目标设备离线，自动拉起 MuMu 失败：{serial}。{auto_start_error}"
                ) from auto_start_error

            selected_device = AndroidUiAutomationWorker._pick_device(
                adb_path,
                expected_serial,
            )
            if log_lines is not None:
                AndroidUiAutomationWorker._log_line(
                    log_lines,
                    f"device auto-started and selected: {selected_device['serial']}",
                )
            return selected_device

    @staticmethod
    def _list_connected_devices(adb_path):
        result = subprocess.run(
            [adb_path, "devices", "-l"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        if result.returncode != 0:
            raise ServiceError(f"adb devices 执行失败：{result.stderr.strip() or result.stdout.strip()}")
        devices = []
        for line in (result.stdout or "").splitlines():
            text = line.strip()
            if not text or text.startswith("List of devices attached"):
                continue
            if "\tdevice" not in text and " device " not in text:
                continue
            parts = text.split()
            serial = parts[0]
            model = ""
            for part in parts[1:]:
                if part.startswith("model:"):
                    model = part.split(":", 1)[1]
                    break
            devices.append({"serial": serial, "model": model})
        return devices

    @staticmethod
    def list_connected_devices_info():
        adb_path = AndroidUiAutomationWorker.resolve_adb_path()
        devices = AndroidUiAutomationWorker._list_connected_devices(adb_path)
        preferences = AndroidUiAutomationWorker.load_device_preferences()
        default_device_serial = str(preferences.get("default_device_serial") or "").strip()
        disabled_devices = set(preferences.get("disabled_devices") or [])
        device_health = preferences.get("device_health") or {}
        device_annotations = preferences.get("device_annotations") or {}
        running_runs = {
            str(item.device_serial or "").strip(): item
            for item in AndroidUiAutomationWorker.list_running_runs()
            if str(item.device_serial or "").strip()
        }
        enriched = []
        for device in devices:
            serial = str(device.get("serial") or "").strip()
            current_run = running_runs.get(serial)
            is_disabled = serial in disabled_devices
            health = device_health.get(serial) or {}
            annotation = device_annotations.get(serial) or {}
            enriched.append(
                {
                    "serial": serial,
                    "model": str(device.get("model") or ""),
                    "android_version": AndroidUiAutomationWorker._read_prop(adb_path, serial, "ro.build.version.release"),
                    "sdk_version": AndroidUiAutomationWorker._read_prop(adb_path, serial, "ro.build.version.sdk"),
                    "brand": AndroidUiAutomationWorker._read_prop(adb_path, serial, "ro.product.brand"),
                    "abi": AndroidUiAutomationWorker._read_prop(adb_path, serial, "ro.product.cpu.abi"),
                    "resolution": AndroidUiAutomationWorker._read_resolution(adb_path, serial),
                    "battery_level": AndroidUiAutomationWorker._read_battery_level(adb_path, serial),
                    "status": "disabled" if is_disabled else ("busy" if current_run else "idle"),
                    "current_run_id": current_run.id if current_run else None,
                    "current_task_name": current_run.task.name if current_run and current_run.task else "",
                    "last_seen_at": AndroidUiAutomationWorker._to_isoformat(AndroidUiAutomationWorker._utc_now()),
                    "is_default": serial == default_device_serial and not is_disabled,
                    "is_disabled": is_disabled,
                    "last_check_status": str(health.get("status") or "").strip(),
                    "last_check_message": str(health.get("message") or "").strip(),
                    "last_checked_at": str(health.get("checked_at") or "").strip(),
                    "annotation_tag": str(annotation.get("tag") or "").strip(),
                    "annotation_note": str(annotation.get("note") or "").strip(),
                    "annotation_updated_at": str(annotation.get("updated_at") or "").strip(),
                }
            )
        return enriched

    @staticmethod
    def test_device_connection(serial):
        adb_path = AndroidUiAutomationWorker.resolve_adb_path()
        normalized_serial = str(serial or "").strip()
        if not normalized_serial:
            raise ServiceError("设备序列号不能为空。")
        devices = AndroidUiAutomationWorker._list_connected_devices(adb_path)
        matched = next((item for item in devices if item["serial"] == normalized_serial), None)
        if not matched:
            raise ServiceError(f"未找到在线设备：{normalized_serial}")
        result = {
            "serial": normalized_serial,
            "model": matched.get("model") or "",
            "android_version": AndroidUiAutomationWorker._read_prop(adb_path, normalized_serial, "ro.build.version.release"),
            "sdk_version": AndroidUiAutomationWorker._read_prop(adb_path, normalized_serial, "ro.build.version.sdk"),
            "brand": AndroidUiAutomationWorker._read_prop(adb_path, normalized_serial, "ro.product.brand"),
            "resolution": AndroidUiAutomationWorker._read_resolution(adb_path, normalized_serial),
            "battery_level": AndroidUiAutomationWorker._read_battery_level(adb_path, normalized_serial),
        }
        AndroidUiAutomationWorker.update_device_health(
            normalized_serial,
            "passed",
            "设备连接正常",
        )
        return result

    @staticmethod
    def _read_prop(adb_path, serial, prop_name):
        result = AndroidUiAutomationWorker._simple_run(
            [adb_path, "-s", serial, "shell", "getprop", prop_name],
            timeout=15,
        )
        if result.returncode != 0:
            return ""
        return str(result.stdout or "").strip()

    @staticmethod
    def _read_resolution(adb_path, serial):
        result = AndroidUiAutomationWorker._simple_run(
            [adb_path, "-s", serial, "shell", "wm", "size"],
            timeout=15,
        )
        if result.returncode != 0:
            return ""
        output = str(result.stdout or "")
        match = re.search(r"Physical size:\s*([0-9]+x[0-9]+)", output)
        if match:
            return match.group(1)
        return output.strip()

    @staticmethod
    def _read_battery_level(adb_path, serial):
        result = AndroidUiAutomationWorker._simple_run(
            [adb_path, "-s", serial, "shell", "dumpsys", "battery"],
            timeout=15,
        )
        if result.returncode != 0:
            return ""
        output = str(result.stdout or "")
        match = re.search(r"level:\s*([0-9]+)", output)
        if match:
            return f"{match.group(1)}%"
        return ""

    @staticmethod
    def _download_apk(url, workspace, log_lines, progress_callback=None, package_name_hint=""):
        local_source = Path(str(url or "").strip()).expanduser()
        if local_source.is_file():
            target_path = local_source.resolve()
            total = target_path.stat().st_size
            AndroidUiAutomationWorker._record_cached_apk(
                url,
                target_path,
                package_name=package_name_hint,
            )
            AndroidUiAutomationWorker._log_line(
                log_lines,
                f"local APK reused directly: {target_path} ({total} bytes)",
            )
            if progress_callback:
                progress_callback(
                    stage="download",
                    progress_text=f"使用本地 APK：{total} bytes",
                    progress_percent=100.0,
                )
            return target_path, total

        cached_path = AndroidUiAutomationWorker._lookup_cached_apk(url)
        if cached_path:
            total = cached_path.stat().st_size
            AndroidUiAutomationWorker._log_line(
                log_lines,
                f"shared APK cache hit: {cached_path} ({total} bytes)",
            )
            if progress_callback:
                progress_callback(
                    stage="download",
                    progress_text=f"复用共享 APK 缓存：{total} bytes",
                    progress_percent=100.0,
                )
            return cached_path, total

        parsed = urlparse(url)
        filename = Path(parsed.path or "").name or "download.apk"
        if not filename.lower().endswith(".apk"):
            filename = f"{filename}.apk"
        target_path = (
            AndroidUiAutomationWorker._package_cache_path(package_name_hint)
            if package_name_hint
            else AndroidUiAutomationWorker._source_cache_path(url)
        )
        if target_path.is_file() and not package_name_hint:
            total = target_path.stat().st_size
            AndroidUiAutomationWorker._record_cached_apk(
                url,
                target_path,
                package_name=package_name_hint,
            )
            AndroidUiAutomationWorker._log_line(
                log_lines,
                f"shared APK cache reused: {target_path} ({total} bytes)",
            )
            if progress_callback:
                progress_callback(
                    stage="download",
                    progress_text=f"复用共享 APK 缓存：{total} bytes",
                    progress_percent=100.0,
                )
            return target_path, total

        connect_timeout = float(
            current_app.config.get("ANDROID_UI_DOWNLOAD_CONNECT_TIMEOUT_SECONDS", 20)
        )
        read_timeout = float(
            current_app.config.get("ANDROID_UI_DOWNLOAD_READ_TIMEOUT_SECONDS", 60)
        )
        max_seconds = float(
            current_app.config.get("ANDROID_UI_DOWNLOAD_MAX_SECONDS", 1800)
        )
        chunk_size = int(
            current_app.config.get("ANDROID_UI_DOWNLOAD_CHUNK_BYTES", 1024 * 512)
        )
        AndroidUiAutomationWorker._log_line(log_lines, f"download start: {url}")
        started = time.monotonic()
        last_log_mark = 0
        temp_path = target_path.with_suffix(f"{target_path.suffix}.part")
        try:
            with requests.get(
                url,
                stream=True,
                timeout=(connect_timeout, read_timeout),
            ) as response:
                response.raise_for_status()
                total = 0
                expected_bytes = int(response.headers.get("Content-Length") or 0)
                with temp_path.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if not chunk:
                            continue
                        handle.write(chunk)
                        total += len(chunk)
                        elapsed = time.monotonic() - started
                        if elapsed > max_seconds:
                            raise ServiceError(
                                f"APK 下载超时，已超过 {int(max_seconds)} 秒。"
                            )
                        if progress_callback:
                            if expected_bytes > 0:
                                percent = round((total / expected_bytes) * 100, 1)
                                progress_callback(
                                    stage="download",
                                    progress_text=f"下载中：{total}/{expected_bytes} bytes",
                                    progress_percent=percent,
                                )
                            else:
                                progress_callback(
                                    stage="download",
                                    progress_text=f"下载中：{total} bytes",
                                    progress_percent=None,
                                )
                        if total - last_log_mark >= 50 * 1024 * 1024:
                            last_log_mark = total
                            if expected_bytes > 0:
                                AndroidUiAutomationWorker._log_line(
                                    log_lines,
                                    f"download progress: {total}/{expected_bytes} bytes",
                                )
                            else:
                                AndroidUiAutomationWorker._log_line(
                                    log_lines,
                                    f"download progress: {total} bytes",
                                )
        except requests_exceptions.Timeout as exc:
            temp_path.unlink(missing_ok=True)
            raise ServiceError(
                f"APK 下载超时：连接或读取超过限制（connect={int(connect_timeout)}s, read={int(read_timeout)}s）。"
            ) from exc
        except requests_exceptions.RequestException as exc:
            temp_path.unlink(missing_ok=True)
            raise ServiceError(f"APK 下载失败：{exc}") from exc
        temp_path.replace(target_path)
        AndroidUiAutomationWorker._record_cached_apk(
            url,
            target_path,
            package_name=package_name_hint,
        )
        AndroidUiAutomationWorker._log_line(
            log_lines,
            f"download completed: {target_path.name} ({total} bytes)",
        )
        return target_path, total

    @staticmethod
    def _run_command(command, timeout, log_lines, binary=False):
        AndroidUiAutomationWorker._log_line(
            log_lines,
            f"command: {subprocess.list2cmdline(command)}",
        )
        result = subprocess.run(
            command,
            capture_output=True,
            text=not binary,
            encoding=None if binary else "utf-8",
            errors=None if binary else "replace",
            timeout=timeout,
        )
        stdout = result.stdout if binary else str(result.stdout or "")
        stderr = result.stderr if binary else str(result.stderr or "")
        if binary:
            AndroidUiAutomationWorker._log_line(
                log_lines,
                f"exit={result.returncode} stdout_bytes={len(stdout or b'')} stderr_bytes={len(stderr or b'')}",
            )
        else:
            AndroidUiAutomationWorker._log_line(log_lines, f"exit={result.returncode}")
            if stdout.strip():
                AndroidUiAutomationWorker._log_line(log_lines, f"stdout: {stdout.strip()[:2000]}")
            if stderr.strip():
                AndroidUiAutomationWorker._log_line(log_lines, f"stderr: {stderr.strip()[:2000]}")
        return result

    @staticmethod
    def _parse_badging(aapt_path, apk_path, log_lines):
        result = AndroidUiAutomationWorker._run_command(
            [aapt_path, "dump", "badging", str(apk_path)],
            timeout=60,
            log_lines=log_lines,
        )
        if result.returncode != 0:
            raise ServiceError(f"aapt 解析失败：{(result.stderr or result.stdout or '').strip()}")
        output = result.stdout or ""
        package_match = re.search(r"package:\s+name='([^']+)'", output)
        launchable_match = re.search(r"launchable-activity:\s+name='([^']+)'", output)
        if not package_match:
            raise ServiceError("未能从 APK 中解析出 package name。")
        package_name = package_match.group(1).strip()
        launchable_activity = launchable_match.group(1).strip() if launchable_match else ""
        return package_name, launchable_activity

    @staticmethod
    def _finalize_cached_apk(url, apk_path, package_name, log_lines):
        package_name = str(package_name or "").strip()
        current_path = Path(apk_path)
        if not package_name:
            AndroidUiAutomationWorker._record_cached_apk(url, current_path)
            return current_path
        if not current_path.is_file():
            return current_path
        local_source = Path(str(url or "").strip()).expanduser()
        if local_source.is_file():
            AndroidUiAutomationWorker._record_cached_apk(
                url,
                current_path,
                package_name=package_name,
            )
            return current_path
        final_path = AndroidUiAutomationWorker._package_cache_path(package_name)
        try:
            if current_path.resolve() != final_path.resolve():
                final_path.parent.mkdir(parents=True, exist_ok=True)
                temp_path = final_path.with_suffix(f"{final_path.suffix}.part")
                shutil.copy2(current_path, temp_path)
                temp_path.replace(final_path)
                if current_path.name.startswith("src__") and current_path.is_file():
                    current_path.unlink(missing_ok=True)
                current_path = final_path
                AndroidUiAutomationWorker._log_line(
                    log_lines,
                    f"shared APK cache normalized to package key: {package_name} -> {final_path.name}",
                )
        except OSError as exc:
            AndroidUiAutomationWorker._log_line(
                log_lines,
                f"shared APK cache normalize skipped: {exc}",
            )
        AndroidUiAutomationWorker._record_cached_apk(
            url,
            current_path,
            package_name=package_name,
        )
        return current_path

    @staticmethod
    def _normalize_component(package_name, activity_name):
        if not activity_name:
            return ""
        if activity_name.startswith("."):
            return f"{package_name}/{package_name}{activity_name}"
        if "/" in activity_name:
            return activity_name
        return f"{package_name}/{activity_name}"

    @staticmethod
    def _install_apk(adb_path, serial, apk_path, timeout, log_lines):
        result = AndroidUiAutomationWorker._run_command(
            [adb_path, "-s", serial, "install", "-r", str(apk_path)],
            timeout=timeout,
            log_lines=log_lines,
        )
        output = f"{result.stdout or ''}\n{result.stderr or ''}".strip()
        if result.returncode != 0 or "Success" not in output:
            raise ServiceError(f"安装失败：{output or 'adb install 返回异常'}")
        return output

    @staticmethod
    def _launch_app(adb_path, serial, component_name, timeout, log_lines):
        result = AndroidUiAutomationWorker._run_command(
            [adb_path, "-s", serial, "shell", "am", "start", "-W", "-n", component_name],
            timeout=timeout,
            log_lines=log_lines,
        )
        output = f"{result.stdout or ''}\n{result.stderr or ''}".strip()
        if result.returncode != 0:
            raise ServiceError(f"启动失败：{output or 'am start 返回异常'}")
        if "Error:" in output or "Exception" in output:
            raise ServiceError(f"启动失败：{output}")
        return output

    @staticmethod
    def _resolve_activity_via_pm(adb_path, serial, package_name, log_lines):
        result = AndroidUiAutomationWorker._run_command(
            [adb_path, "-s", serial, "shell", "cmd", "package", "resolve-activity", "--brief", package_name],
            timeout=30,
            log_lines=log_lines,
        )
        if result.returncode != 0:
            return ""
        lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
        for line in reversed(lines):
            if "/" in line and package_name in line:
                return line
        return ""

    @staticmethod
    def _launch_app_with_monkey(adb_path, serial, package_name, timeout, log_lines):
        result = AndroidUiAutomationWorker._run_command(
            [
                adb_path,
                "-s",
                serial,
                "shell",
                "monkey",
                "-p",
                package_name,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ],
            timeout=timeout,
            log_lines=log_lines,
        )
        output = f"{result.stdout or ''}\n{result.stderr or ''}".strip()
        if result.returncode != 0:
            raise ServiceError(f"启动失败：{output or 'monkey 返回异常'}")
        if "No activities found to run" in output:
            raise ServiceError(f"启动失败：{output}")
        return output

    @staticmethod
    def _read_current_focus(adb_path, serial, log_lines):
        result = AndroidUiAutomationWorker._run_command(
            [adb_path, "-s", serial, "shell", "dumpsys", "window", "windows"],
            timeout=30,
            log_lines=log_lines,
        )
        if result.returncode != 0:
            return ""
        output = result.stdout or ""
        matches = []
        for line in output.splitlines():
            text = line.strip()
            if "mCurrentFocus" in text or "mFocusedApp" in text:
                matches.append(text)
        return "\n".join(matches[:10]).strip()

    @staticmethod
    def _read_pid(adb_path, serial, package_name, log_lines):
        result = AndroidUiAutomationWorker._run_command(
            [adb_path, "-s", serial, "shell", "pidof", package_name],
            timeout=20,
            log_lines=log_lines,
        )
        if result.returncode != 0:
            return ""
        return (result.stdout or "").strip()

    @staticmethod
    def _capture_screenshot(adb_path, serial, workspace, log_lines):
        target_path = workspace / "launch.png"
        result = AndroidUiAutomationWorker._run_command(
            [adb_path, "-s", serial, "exec-out", "screencap", "-p"],
            timeout=40,
            log_lines=log_lines,
            binary=True,
        )
        if result.returncode != 0 or not result.stdout:
            raise ServiceError("截图失败：adb screencap 未返回图片数据。")
        target_path.write_bytes(result.stdout)
        AndroidUiAutomationWorker._log_line(log_lines, f"screenshot saved: {target_path.name}")
        return target_path

    @staticmethod
    def _capture_named_screenshot(adb_path, serial, workspace, log_lines, filename):
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", str(filename or "").strip()) or "step.png"
        target_path = workspace / safe_name
        result = AndroidUiAutomationWorker._run_command(
            [adb_path, "-s", serial, "exec-out", "screencap", "-p"],
            timeout=40,
            log_lines=log_lines,
            binary=True,
        )
        if result.returncode != 0 or not result.stdout:
            raise ServiceError("截图失败：adb screencap 未返回图片数据。")
        target_path.write_bytes(result.stdout)
        AndroidUiAutomationWorker._log_line(log_lines, f"screenshot saved: {target_path.name}")
        return target_path

    @staticmethod
    def _adb_shell(adb_path, serial, shell_args, timeout, log_lines):
        command = [adb_path, "-s", serial, "shell", *shell_args]
        return AndroidUiAutomationWorker._run_command(
            command,
            timeout=timeout,
            log_lines=log_lines,
        )

    @staticmethod
    def _escape_input_text(value):
        text = str(value or "")
        text = text.replace(" ", "%s")
        return text

    @staticmethod
    def _tap_point(adb_path, serial, x, y, log_lines):
        result = AndroidUiAutomationWorker._adb_shell(
            adb_path,
            serial,
            ["input", "tap", str(int(x)), str(int(y))],
            timeout=15,
            log_lines=log_lines,
        )
        if result.returncode != 0:
            raise ServiceError("点击失败：adb input tap 返回异常。")
        return True

    @staticmethod
    def _send_keyevent(adb_path, serial, key_value, log_lines):
        key_values = [
            item
            for item in str(key_value or "").replace(",", " ").split()
            if item
        ]
        if not key_values:
            raise ServiceError("keyevent value cannot be empty")
        result = AndroidUiAutomationWorker._adb_shell(
            adb_path,
            serial,
            ["input", "keyevent", *key_values],
            timeout=15,
            log_lines=log_lines,
        )
        if result.returncode != 0:
            raise ServiceError("按键事件发送失败。")
        return True

    @staticmethod
    def _input_text(adb_path, serial, value, log_lines):
        escaped = AndroidUiAutomationWorker._escape_input_text(value)
        result = AndroidUiAutomationWorker._adb_shell(
            adb_path,
            serial,
            ["input", "text", escaped],
            timeout=20,
            log_lines=log_lines,
        )
        if result.returncode != 0:
            raise ServiceError("输入文本失败。")
        return True

    @staticmethod
    def _uiautomator_dump(adb_path, serial, log_lines):
        result = AndroidUiAutomationWorker._adb_shell(
            adb_path,
            serial,
            ["uiautomator", "dump", "/dev/tty"],
            timeout=30,
            log_lines=log_lines,
        )
        if result.returncode != 0:
            fallback_path = "/sdcard/window_dump.xml"
            fallback_dump = AndroidUiAutomationWorker._adb_shell(
                adb_path,
                serial,
                ["uiautomator", "dump", fallback_path],
                timeout=30,
                log_lines=log_lines,
            )
            if fallback_dump.returncode == 0:
                fallback_read = AndroidUiAutomationWorker._adb_shell(
                    adb_path,
                    serial,
                    ["cat", fallback_path],
                    timeout=30,
                    log_lines=log_lines,
                )
                if fallback_read.returncode == 0:
                    result.returncode = 0
                    result.stdout = fallback_read.stdout
        if result.returncode != 0:
            raise ServiceError("获取界面结构失败。")
        output = str(result.stdout or "")
        xml_index = output.find("<?xml")
        if xml_index < 0:
            xml_index = output.find("<hierarchy")
        if xml_index < 0:
            raise ServiceError("获取界面结构失败：未找到 XML 内容。")
        xml_text = output[xml_index:].strip()
        try:
            return ElementTree.fromstring(xml_text)
        except ElementTree.ParseError as exc:
            raise ServiceError(f"获取界面结构失败：{exc}") from exc

    @staticmethod
    def _parse_bounds_center(bounds_text):
        match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", str(bounds_text or "").strip())
        if not match:
            raise ServiceError("坐标范围格式无效，应为 [x1,y1][x2,y2]。")
        x1, y1, x2, y2 = [int(item) for item in match.groups()]
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    @staticmethod
    def _parse_bounds_box(bounds_text):
        match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", str(bounds_text or "").strip())
        if not match:
            raise ServiceError("坐标范围格式无效，应为 [x1,y1][x2,y2]。")
        return [int(item) for item in match.groups()]


    @staticmethod
    def _visual_template_root():
        root = Path(current_app.instance_path) / "android_ui_automation" / "templates"
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()

    @staticmethod
    def _resolve_visual_template_path(selector_value):
        candidate = Path(str(selector_value or "").strip())
        if candidate.is_file():
            return candidate.resolve()
        template_root = AndroidUiAutomationWorker._visual_template_root()
        candidate = template_root / str(selector_value or "").strip()
        if candidate.is_file():
            return candidate.resolve()
        return None

    @staticmethod
    def _template_image_base64(selector_value):
        template_path = AndroidUiAutomationWorker._resolve_visual_template_path(selector_value)
        if not template_path:
            raise ServiceError(f"??????????{selector_value}")
        return base64.b64encode(template_path.read_bytes()).decode("ascii")

    @staticmethod
    def _create_visual_driver(serial, package_name, activity_name, log_lines):
        if not serial or not package_name or not activity_name:
            return None
        if not appium_webdriver or not UiAutomator2Options:
            return None
        options = UiAutomator2Options()
        options.platform_name = "Android"
        options.device_name = serial
        options.udid = serial
        options.automation_name = "UiAutomator2"
        options.app_package = package_name
        options.app_activity = activity_name
        options.no_reset = True
        options.set_capability("appium:dontStopAppOnReset", True)
        options.new_command_timeout = 120
        options.set_capability("appium:skipDeviceInitialization", True)
        options.set_capability("appium:disableWindowAnimation", True)
        options.set_capability("appium:settings[ocrLanguage]", "chi_sim+eng")
        driver = appium_webdriver.Remote("http://127.0.0.1:4723", options=options)
        try:
            driver.update_settings(
                {
                    "ocrLanguage": "chi_sim+eng",
                    "ocrContrast": 0.8,
                    "imageMatchThreshold": 0.45,
                }
            )
        except Exception as exc:
            AndroidUiAutomationWorker._log_line(log_lines, f"visual settings update failed: {exc}")
        return driver

    @staticmethod
    def _close_visual_driver(driver):
        if not driver:
            return
        try:
            driver.quit()
        except Exception:
            pass

    @staticmethod
    def _xpath_literal(value):
        text = str(value or "")
        if '"' not in text:
            return f'"{text}"'
        if "'" not in text:
            return f"'{text}'"
        parts = text.split('"')
        expr_parts = []
        for index, part in enumerate(parts):
            if part:
                expr_parts.append(f'"{part}"')
            if index < len(parts) - 1:
                expr_parts.append('\'"\'' )
        return "concat(" + ", ".join(expr_parts) + ")"

    @staticmethod
    def _find_ocr_node(driver, selector_value):
        selector = str(selector_value or "").strip()
        if not driver or not selector:
            return None
        driver.switch_to.context("OCR")
        literal = AndroidUiAutomationWorker._xpath_literal(selector)
        xpath = f'//lines/item[contains(text(), {literal})] | //words/item[contains(text(), {literal})]'
        matches = driver.find_elements(AppiumBy.XPATH, xpath)
        return matches[0] if matches else None

    @staticmethod
    def _find_image_node(driver, selector_value):
        return None

    @staticmethod
    def _capture_screen_bytes(adb_path, serial, log_lines):
        result = AndroidUiAutomationWorker._run_command(
            [adb_path, "-s", serial, "exec-out", "screencap", "-p"],
            timeout=40,
            log_lines=log_lines,
            binary=True,
        )
        if result.returncode != 0 or not result.stdout:
            raise ServiceError("截图失败：adb screencap 未返回图片数据。")
        return result.stdout

    @staticmethod
    def _load_grayscale_image(image_bytes):
        buffer = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ServiceError("图像解析失败：无法解码截图数据。")
        return image

    @staticmethod
    def _image_search_region(template_name, screen_width, screen_height):
        lowered = str(template_name or "").lower()
        if "floating_entry" in lowered:
            return 0, max(0, int(screen_height * 0.35)), min(screen_width, int(screen_width * 0.18)), screen_height
        if "user_center_close" in lowered:
            return max(0, screen_width - 420), 0, screen_width, min(screen_height, 220)
        if "user_center_title" in lowered:
            return int(screen_width * 0.35), int(screen_height * 0.06), int(screen_width * 0.66), int(screen_height * 0.22)
        if "user_center_account_management" in lowered:
            return int(screen_width * 0.12), int(screen_height * 0.16), int(screen_width * 0.34), int(screen_height * 0.42)
        if "user_center_phone" in lowered:
            return int(screen_width * 0.12), int(screen_height * 0.24), int(screen_width * 0.34), int(screen_height * 0.50)
        if "user_center_realname" in lowered:
            return int(screen_width * 0.40), int(screen_height * 0.16), int(screen_width * 0.60), int(screen_height * 0.42)
        if "user_center_thirdparty" in lowered:
            return int(screen_width * 0.48), int(screen_height * 0.16), int(screen_width * 0.70), int(screen_height * 0.42)
        if "customer_title" in lowered:
            return int(screen_width * 0.38), int(screen_height * 0.06), int(screen_width * 0.62), int(screen_height * 0.22)
        if "customer_contact_link" in lowered:
            return int(screen_width * 0.20), int(screen_height * 0.22), int(screen_width * 0.45), int(screen_height * 0.42)
        if "customer_chat_title" in lowered:
            return 0, 0, int(screen_width * 0.55), int(screen_height * 0.15)
        if "customer_sent_message" in lowered:
            return int(screen_width * 0.25), int(screen_height * 0.35), int(screen_width * 0.55), int(screen_height * 0.70)
        if "customer_send_success_reply" in lowered:
            return 0, int(screen_height * 0.25), int(screen_width * 0.50), int(screen_height * 0.70)
        if "user_agreement" in lowered or "privacy_policy" in lowered:
            return int(screen_width * 0.05), int(screen_height * 0.05), int(screen_width * 0.95), int(screen_height * 0.95)
        if "order_list" in lowered:
            return int(screen_width * 0.25), 0, screen_width, screen_height
        if "switch_account_other_login" in lowered:
            return int(screen_width * 0.25), int(screen_height * 0.25), int(screen_width * 0.75), int(screen_height * 0.75)
        if "phone_login_form" in lowered or "phone_error_correct_number" in lowered or "phone_code_error" in lowered:
            return int(screen_width * 0.25), int(screen_height * 0.20), int(screen_width * 0.75), int(screen_height * 0.80)
        # The post-login privacy prompt is a fixed-size SDK dialog on the
        # configured emulator. Restrict these selectors to their dialog zones
        # so the login page cannot be mistaken for the prompt.
        if "sdk_post_login_title" in lowered:
            return int(screen_width * 0.35), int(screen_height * 0.25), int(screen_width * 0.68), int(screen_height * 0.58)
        if "sdk_post_login_agree" in lowered:
            return int(screen_width * 0.48), int(screen_height * 0.48), int(screen_width * 0.68), int(screen_height * 0.78)
        if "sdk_agreement_circle" in lowered or "sdk_agreement_checkbox" in lowered:
            return int(screen_width * 0.30), int(screen_height * 0.64), int(screen_width * 0.42), int(screen_height * 0.76)
        if "sdk_login_error_password" in lowered:
            return int(screen_width * 0.32), int(screen_height * 0.42), int(screen_width * 0.66), int(screen_height * 0.64)
        return 0, 0, screen_width, screen_height

    @staticmethod
    def _find_image_match(adb_path, serial, selector_value, log_lines):
        template_path = AndroidUiAutomationWorker._resolve_visual_template_path(selector_value)
        if not template_path:
            raise ServiceError(f"未找到图像模板文件：{selector_value}")
        template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
        if template is None:
            raise ServiceError(f"图像模板解析失败：{template_path.name}")
        screen = AndroidUiAutomationWorker._load_grayscale_image(
            AndroidUiAutomationWorker._capture_screen_bytes(adb_path, serial, log_lines)
        )
        screen_height, screen_width = screen.shape[:2]
        template_height, template_width = template.shape[:2]
        left, top, right, bottom = AndroidUiAutomationWorker._image_search_region(
            template_path.name,
            screen_width,
            screen_height,
        )
        search_area = screen[top:bottom, left:right]
        if search_area.size == 0 or search_area.shape[0] < template_height or search_area.shape[1] < template_width:
            search_area = screen
            left = 0
            top = 0
        # SDK WebView controls can be rendered at a slightly different scale
        # on each emulator profile. Search a small scale band so templates do
        # not become tied to one exact DPI configuration.
        candidates = [(template, 1.0)]
        if any(token in template_path.name for token in ("sdk_", "floating_entry")):
            candidates = []
            scales = (1.0,) if any(
                token in template_path.name for token in (
                    "sdk_post_login_title",
                    "sdk_post_login_agree",
                    "sdk_agreement_checkbox",
                    "sdk_agreement_circle",
                    "sdk_login_error_password",
                )
            ) else (0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2)
            for scale in scales:
                scaled = cv2.resize(
                    template,
                    None,
                    fx=scale,
                    fy=scale,
                    interpolation=cv2.INTER_LINEAR,
                )
                if scaled.shape[0] <= search_area.shape[0] and scaled.shape[1] <= search_area.shape[1]:
                    candidates.append((scaled, scale))
        best = None
        for candidate, scale in candidates:
            result = cv2.matchTemplate(search_area, candidate, cv2.TM_CCOEFF_NORMED)
            _min_val, max_val, _min_loc, max_loc = cv2.minMaxLoc(result)
            if best is None or max_val > best[0]:
                best = (max_val, max_loc, candidate, scale)
        if best is None:
            return None
        max_val, max_loc, matched_template, _scale = best
        threshold = 0.75 if ("floating_entry" in template_path.name or "user_center_close" in template_path.name) else 0.8
        if "sdk_post_login_title" in template_path.name or "sdk_post_login_agree" in template_path.name:
            threshold = 0.92
        if "sdk_login_error_password" in template_path.name:
            threshold = 0.9
        if "sdk_username_field" in template_path.name or "sdk_password_field" in template_path.name:
            threshold = 0.72
        if max_val < threshold:
            return None
        x = left + int(max_loc[0])
        y = top + int(max_loc[1])
        return {
            "rect": {
                "x": x,
                "y": y,
                "width": int(matched_template.shape[1]),
                "height": int(matched_template.shape[0]),
            },
            "center": {
                "x": x + (matched_template.shape[1] // 2),
                "y": y + (matched_template.shape[0] // 2),
            },
            "score": float(max_val),
            "template_path": str(template_path),
        }

    @staticmethod
    def _detect_xianyu_login_failure(adb_path, serial, log_lines):
        for selector_value, message in (
            ("xianyu/sdk_login_error_password.png", "登录失败，密码错误"),
        ):
            try:
                node = AndroidUiAutomationWorker._find_image_match(
                    adb_path,
                    serial,
                    selector_value,
                    log_lines,
                )
            except Exception:
                continue
            if node is not None:
                return message, node
        return "", None

    @staticmethod
    def _wait_for_image(
        adb_path,
        serial,
        selector_value,
        timeout,
        log_lines,
        should_exist=True,
        run_id=None,
    ):
        candidate_map = {
            "xianyu/sdk_login_button.png": (
                "xianyu/sdk_login_button.png",
                "xianyu/sdk_login_button_candidate2.png",
                "xianyu/sdk_login_button_candidate3.png",
            ),
            "xianyu/sdk_account_login_switch.png": (
                "xianyu/sdk_account_login_switch.png",
                "xianyu/sdk_account_login_switch_candidate2.png",
                "xianyu/sdk_account_login_switch_candidate3.png",
                "xianyu/sdk_account_login_tab.png",
            ),
            "xianyu/xianyu_floating_entry.png": (
                "xianyu/xianyu_floating_entry.png",
                "xianyu/floating_candidate_1.png",
                "xianyu/floating_candidate_2.png",
                "xianyu/floating_candidate_3.png",
            ),
        }
        fallback_selectors = candidate_map.get(str(selector_value or "").strip())
        if should_exist and fallback_selectors:
            _selector, node = AndroidUiAutomationWorker._wait_for_any_image(
                adb_path,
                serial,
                fallback_selectors,
                timeout,
                log_lines,
                run_id=run_id,
            )
            return node
        deadline = time.monotonic() + max(1, int(timeout or 1))
        last_error = None
        while time.monotonic() <= deadline:
            AndroidUiAutomationWorker.raise_if_stop_requested(run_id)
            try:
                node = AndroidUiAutomationWorker._find_image_match(adb_path, serial, selector_value, log_lines)
                if should_exist and node is not None:
                    return node
                if not should_exist and node is None:
                    return None
            except Exception as exc:
                last_error = exc
            time.sleep(1)
        if should_exist:
            if last_error:
                raise last_error
            raise ServiceError(f"等待图像模板超时：{selector_value}")
        return None

    @staticmethod
    def _wait_for_any_image(adb_path, serial, selector_values, timeout, log_lines, run_id=None):
        selectors = [str(item or "").strip() for item in (selector_values or []) if str(item or "").strip()]
        if not selectors:
            raise ServiceError("No image selectors provided.")
        deadline = time.monotonic() + max(1, int(timeout or 1))
        last_error = None
        while time.monotonic() <= deadline:
            AndroidUiAutomationWorker.raise_if_stop_requested(run_id)
            for selector_value in selectors:
                try:
                    node = AndroidUiAutomationWorker._find_image_match(
                        adb_path,
                        serial,
                        selector_value,
                        log_lines,
                    )
                except Exception as exc:
                    last_error = exc
                    continue
                if node is not None:
                    return selector_value, node
            time.sleep(1)
        if last_error:
            raise last_error
        raise ServiceError(f"等待图像模板超时：{' | '.join(selectors)}")

    @staticmethod
    def _capture_xianyu_user_center_attempt(
        adb_path,
        serial,
        workspace,
        log_lines,
        step,
        attempt,
        phase,
    ):
        screenshot_path = AndroidUiAutomationWorker._capture_named_screenshot(
            adb_path,
            serial,
            workspace,
            log_lines,
            f"step_{int(step.step_no):02d}_attempt_{int(attempt):02d}_{phase}.png",
        )
        AndroidUiAutomationWorker._attach_step_artifact(
            step,
            screenshot_path,
            artifact_type="attempt_screenshot",
        )
        return str(screenshot_path)

    @staticmethod
    def _open_xianyu_user_center(
        adb_path,
        serial,
        workspace,
        log_lines,
        step,
        target_selector,
        wait_timeout,
        retry_times=0,
        run_id=None,
    ):
        target_template = str(target_selector or "").strip() or "xianyu/xianyu_user_center_title.png"
        entry_template = "xianyu/xianyu_floating_entry.png"
        attempts = max(1, int(retry_times or 0) + 1)
        attempt_results = []
        last_error = ""

        for attempt in range(1, attempts + 1):
            AndroidUiAutomationWorker.raise_if_stop_requested(run_id)
            attempt_payload = {"attempt": attempt, "screenshots": []}
            try:
                entry_node = AndroidUiAutomationWorker._wait_for_image(
                    adb_path,
                    serial,
                    entry_template,
                    min(12, max(3, int(wait_timeout or 1))),
                    log_lines,
                    should_exist=True,
                    run_id=run_id,
                )
                first_tap = dict(entry_node["center"])
                AndroidUiAutomationWorker._tap_point(
                    adb_path,
                    serial,
                    first_tap["x"],
                    first_tap["y"],
                    log_lines,
                )
                attempt_payload["first_tap"] = first_tap
                attempt_payload["screenshots"].append(
                    AndroidUiAutomationWorker._capture_xianyu_user_center_attempt(
                        adb_path,
                        serial,
                        workspace,
                        log_lines,
                        step,
                        attempt,
                        "first_tap",
                    )
                )

                try:
                    AndroidUiAutomationWorker._wait_for_image(
                        adb_path,
                        serial,
                        target_template,
                        min(5, max(2, int(wait_timeout or 1))),
                        log_lines,
                        should_exist=True,
                        run_id=run_id,
                    )
                    attempt_payload["confirmed_after"] = "first_tap"
                    attempt_payload["screenshots"].append(
                        AndroidUiAutomationWorker._capture_xianyu_user_center_attempt(
                            adb_path,
                            serial,
                            workspace,
                            log_lines,
                            step,
                            attempt,
                            "user_center_confirmed",
                        )
                    )
                    attempt_results.append(attempt_payload)
                    return {
                        "attempt_count": attempt,
                        "confirmed_after": "first_tap",
                        "attempts": attempt_results,
                    }
                except ServiceError:
                    pass

                try:
                    latest_entry = AndroidUiAutomationWorker._wait_for_image(
                        adb_path,
                        serial,
                        entry_template,
                        2,
                        log_lines,
                        should_exist=True,
                        run_id=run_id,
                    )
                    second_tap = dict(latest_entry["center"])
                    attempt_payload["second_tap_strategy"] = "latest_entry_image"
                except ServiceError:
                    second_tap = first_tap
                    attempt_payload["second_tap_strategy"] = "first_entry_point"
                AndroidUiAutomationWorker._tap_point(
                    adb_path,
                    serial,
                    second_tap["x"],
                    second_tap["y"],
                    log_lines,
                )
                attempt_payload["second_tap"] = second_tap
                attempt_payload["screenshots"].append(
                    AndroidUiAutomationWorker._capture_xianyu_user_center_attempt(
                        adb_path,
                        serial,
                        workspace,
                        log_lines,
                        step,
                        attempt,
                        "second_tap",
                    )
                )
                AndroidUiAutomationWorker._wait_for_image(
                    adb_path,
                    serial,
                    target_template,
                    max(3, int(wait_timeout or 1)),
                    log_lines,
                    should_exist=True,
                    run_id=run_id,
                )
                attempt_payload["confirmed_after"] = "second_tap"
                attempt_payload["screenshots"].append(
                    AndroidUiAutomationWorker._capture_xianyu_user_center_attempt(
                        adb_path,
                        serial,
                        workspace,
                        log_lines,
                        step,
                        attempt,
                        "user_center_confirmed",
                    )
                )
                attempt_results.append(attempt_payload)
                return {
                    "attempt_count": attempt,
                    "confirmed_after": "second_tap",
                    "attempts": attempt_results,
                }
            except ServiceError as exc:
                last_error = str(exc)
                attempt_payload["error"] = last_error
                try:
                    attempt_payload["screenshots"].append(
                        AndroidUiAutomationWorker._capture_xianyu_user_center_attempt(
                            adb_path,
                            serial,
                            workspace,
                            log_lines,
                            step,
                            attempt,
                            "failed",
                        )
                    )
                except Exception as screenshot_error:
                    attempt_payload["screenshot_error"] = str(screenshot_error)
                attempt_results.append(attempt_payload)
                AndroidUiAutomationWorker._log_line(
                    log_lines,
                    f"xianyu user center attempt {attempt}/{attempts} failed: {last_error}",
                )
                if attempt < attempts:
                    time.sleep(1)

        raise ServiceError(
            f"打开用户中心失败，已尝试 {attempts} 次：{last_error or target_template}"
        )

    @staticmethod
    def _find_node(root, selector_type, selector_value):
        selector = str(selector_value or "").strip()
        selector_kind = str(selector_type or "none").strip().lower()
        if not selector:
            return None
        if selector_kind == "xpath":
            try:
                matches = root.findall(selector)
            except SyntaxError:
                return None
            return matches[0] if matches else None
        if selector_kind == "text":
            clickable_match = AndroidUiAutomationWorker._find_clickable_text_container(root, selector)
            if clickable_match is not None:
                return clickable_match
        for node in root.iter():
            attrs = node.attrib or {}
            text_value = str(attrs.get("text") or "").strip()
            desc_value = str(attrs.get("content-desc") or "").strip()
            resource_id = str(attrs.get("resource-id") or "").strip()
            bounds = str(attrs.get("bounds") or "").strip()
            if selector_kind == "text":
                if selector == text_value or selector == desc_value or selector in text_value or selector in desc_value:
                    return node
            elif selector_kind == "resource_id":
                if selector == resource_id or resource_id.endswith(selector):
                    return node
            elif selector_kind == "bounds":
                if selector == bounds:
                    return node
        return None

    @staticmethod
    def _text_selector_matches(attrs, selector):
        text_value = str((attrs or {}).get("text") or "").strip()
        desc_value = str((attrs or {}).get("content-desc") or "").strip()
        return (
            selector == text_value
            or selector == desc_value
            or selector in text_value
            or selector in desc_value
        )

    @staticmethod
    def _subtree_contains_text(node, selector):
        if AndroidUiAutomationWorker._text_selector_matches(node.attrib or {}, selector):
            return True
        for child in list(node):
            if AndroidUiAutomationWorker._subtree_contains_text(child, selector):
                return True
        return False

    @staticmethod
    def _find_clickable_text_container(node, selector):
        for child in list(node):
            matched = AndroidUiAutomationWorker._find_clickable_text_container(child, selector)
            if matched is not None:
                return matched
        attrs = node.attrib or {}
        if str(attrs.get("clickable") or "").strip().lower() != "true":
            return None
        if AndroidUiAutomationWorker._subtree_contains_text(node, selector):
            return node
        return None

    @staticmethod
    def _wait_for_selector(
        adb_path,
        serial,
        selector_type,
        selector_value,
        timeout,
        log_lines,
        should_exist=True,
        visual_driver=None,
        run_id=None,
    ):
        deadline = time.monotonic() + max(1, int(timeout or 1))
        last_error = None
        while time.monotonic() <= deadline:
            AndroidUiAutomationWorker.raise_if_stop_requested(run_id)
            try:
                root = AndroidUiAutomationWorker._uiautomator_dump(adb_path, serial, log_lines)
                node = AndroidUiAutomationWorker._find_node(root, selector_type, selector_value)
                if should_exist and node is not None:
                    return node
                if not should_exist and node is None:
                    return None
            except ServiceError as exc:
                last_error = exc
            if str(selector_type or "").strip().lower() == "text" and visual_driver:
                try:
                    visual_node = AndroidUiAutomationWorker._find_ocr_node(visual_driver, selector_value)
                    if should_exist and visual_node is not None:
                        return visual_node
                    if not should_exist and visual_node is None:
                        return None
                except Exception as exc:
                    last_error = exc
            time.sleep(1)
        if should_exist:
            if last_error:
                raise last_error
            raise ServiceError(f"等待界面元素超时：{selector_type}={selector_value}")
        return None

    @staticmethod
    def _materialize_flow_steps(run):
        return AndroidUiAutomationService.materialize_run_steps(run)

    @staticmethod
    def _attach_step_artifact(step, file_path, artifact_type="screenshot"):
        normalized_path = Path(str(file_path or "").strip())
        if not step or not normalized_path:
            return None
        if not normalized_path.is_file():
            return None
        return AndroidUiAutomationService.create_run_step_artifact(
            run_step_id=step.id,
            artifact_type=artifact_type,
            file_path=str(normalized_path),
            file_name=normalized_path.name,
            file_size=normalized_path.stat().st_size,
        )

    @staticmethod
    def _execute_flow_step(
        adb_path,
        serial,
        workspace,
        log_lines,
        step,
        snapshot_item,
        visual_driver=None,
        run_id=None,
    ):
        step_type = str(snapshot_item.get("step_type") or "").strip().lower()
        selector_type = str(snapshot_item.get("selector_type") or "").strip().lower()
        selector_value = str(snapshot_item.get("selector_value") or "").strip()
        input_value = str(snapshot_item.get("input_value") or "").strip()
        wait_timeout = int(snapshot_item.get("wait_timeout_sec") or 20)
        result_payload = {}
        AndroidUiAutomationWorker.raise_if_stop_requested(run_id)
        if step_type == "sleep":
            for _ in range(max(1, wait_timeout)):
                AndroidUiAutomationWorker.raise_if_stop_requested(run_id)
                time.sleep(1)
        elif step_type == "wait_text" or step_type == "assert_exists":
            AndroidUiAutomationWorker._wait_for_selector(
                adb_path,
                serial,
                selector_type or "text",
                selector_value,
                wait_timeout,
                log_lines,
                should_exist=True,
                visual_driver=visual_driver,
                run_id=run_id,
            )
        elif step_type == "assert_not_exists":
            AndroidUiAutomationWorker._wait_for_selector(
                adb_path,
                serial,
                selector_type or "text",
                selector_value,
                wait_timeout,
                log_lines,
                should_exist=False,
                visual_driver=visual_driver,
                run_id=run_id,
            )
        elif step_type == "tap_text":
            node = AndroidUiAutomationWorker._wait_for_selector(
                adb_path,
                serial,
                selector_type or "text",
                selector_value,
                wait_timeout,
                log_lines,
                should_exist=True,
                visual_driver=visual_driver,
                run_id=run_id,
            )
            if hasattr(node, "click"):
                node.click()
                result_payload["tap_mode"] = "visual"
            else:
                x, y = AndroidUiAutomationWorker._parse_bounds_center((node.attrib or {}).get("bounds"))
                AndroidUiAutomationWorker._tap_point(adb_path, serial, x, y, log_lines)
                result_payload["tap_point"] = {"x": x, "y": y}
        elif step_type == "tap_left_of_text":
            node = AndroidUiAutomationWorker._wait_for_selector(
                adb_path,
                serial,
                selector_type or "text",
                selector_value,
                wait_timeout,
                log_lines,
                should_exist=True,
                visual_driver=visual_driver,
                run_id=run_id,
            )
            if hasattr(node, "rect") and getattr(node, "rect", None):
                rect = node.rect
                x1 = int(rect["x"])
                y1 = int(rect["y"])
                y2 = int(rect["y"] + rect["height"])
            else:
                x1, y1, _x2, y2 = AndroidUiAutomationWorker._parse_bounds_box((node.attrib or {}).get("bounds"))
            left_offset = max(1, int(input_value or 26))
            x = max(1, x1 - left_offset)
            y = (y1 + y2) // 2
            AndroidUiAutomationWorker._tap_point(adb_path, serial, x, y, log_lines)
            result_payload["tap_point"] = {"x": x, "y": y, "offset_left": left_offset}
        elif step_type == "tap_bounds":
            x, y = AndroidUiAutomationWorker._parse_bounds_center(selector_value)
            AndroidUiAutomationWorker._tap_point(adb_path, serial, x, y, log_lines)
            result_payload["tap_point"] = {"x": x, "y": y}
        elif step_type == "input_text":
            if selector_value:
                if selector_type == "image":
                    node = AndroidUiAutomationWorker._wait_for_image(
                        adb_path,
                        serial,
                        selector_value,
                        wait_timeout,
                        log_lines,
                        should_exist=True,
                        run_id=run_id,
                    )
                    tap_point = node["center"]
                    AndroidUiAutomationWorker._tap_point(
                        adb_path,
                        serial,
                        tap_point["x"],
                        tap_point["y"],
                        log_lines,
                    )
                    result_payload["tap_point"] = tap_point
                    result_payload["tap_mode"] = "image"
                else:
                    node = AndroidUiAutomationWorker._wait_for_selector(
                        adb_path,
                        serial,
                        selector_type or "text",
                        selector_value,
                        wait_timeout,
                        log_lines,
                        should_exist=True,
                        visual_driver=visual_driver,
                        run_id=run_id,
                    )
                    if hasattr(node, "click"):
                        node.click()
                    else:
                        x, y = AndroidUiAutomationWorker._parse_bounds_center((node.attrib or {}).get("bounds"))
                        AndroidUiAutomationWorker._tap_point(adb_path, serial, x, y, log_lines)
            AndroidUiAutomationWorker._input_text(adb_path, serial, input_value, log_lines)
        elif step_type == "handle_xianyu_post_login_consent":
            # This prompt is optional and may appear only after the first
            # login submission. If it appears, accept it and explicitly
            # submit the account form again so the action is visible in the
            # execution record rather than hidden inside a wait step.
            deadline = time.monotonic() + max(1, wait_timeout)
            consent = None
            login_failure_present = False
            while time.monotonic() <= deadline:
                AndroidUiAutomationWorker.raise_if_stop_requested(run_id)
                failure_message, _failure_node = AndroidUiAutomationWorker._detect_xianyu_login_failure(
                    adb_path,
                    serial,
                    log_lines,
                )
                if failure_message:
                    login_failure_present = True
                    result_payload["login_failure_present"] = failure_message
                    break
                try:
                    title = AndroidUiAutomationWorker._wait_for_image(
                        adb_path,
                        serial,
                        "xianyu/sdk_post_login_title.png",
                        1,
                        log_lines,
                        should_exist=True,
                        run_id=run_id,
                    )
                    consent = AndroidUiAutomationWorker._wait_for_image(
                        adb_path,
                        serial,
                        "xianyu/sdk_post_login_agree.png",
                        1,
                        log_lines,
                        should_exist=True,
                        run_id=run_id,
                    )
                    if title and consent:
                        break
                except Exception:
                    pass
                time.sleep(1)
            if login_failure_present:
                pass
            if consent:
                AndroidUiAutomationWorker._tap_point(
                    adb_path,
                    serial,
                    consent["center"]["x"],
                    consent["center"]["y"],
                    log_lines,
                )
                result_payload["consent_button"] = consent["center"]
                for _ in range(5):
                    AndroidUiAutomationWorker.raise_if_stop_requested(run_id)
                    time.sleep(1)
                login_button = AndroidUiAutomationWorker._wait_for_image(
                    adb_path,
                    serial,
                    "xianyu/sdk_post_login_resubmit_button.png",
                    10,
                    log_lines,
                    should_exist=True,
                    run_id=run_id,
                )
                AndroidUiAutomationWorker._tap_point(
                    adb_path,
                    serial,
                    login_button["center"]["x"],
                    login_button["center"]["y"],
                    log_lines,
                )
                result_payload["resubmit_login_button"] = login_button["center"]
                for _ in range(3):
                    AndroidUiAutomationWorker.raise_if_stop_requested(run_id)
                    time.sleep(1)
            else:
                result_payload["consent_present"] = False
        elif step_type == "wait_image" or step_type == "assert_image_exists":
            if "xianyu_floating_entry" in selector_value:
                # Login can trigger a second privacy prompt after a delay.
                # Keep checking both the prompt and the game entry until the
                # full resource timeout expires.
                deadline = time.monotonic() + max(1, wait_timeout)
                entry = None
                while time.monotonic() <= deadline:
                    AndroidUiAutomationWorker.raise_if_stop_requested(run_id)
                    failure_message, _failure_node = AndroidUiAutomationWorker._detect_xianyu_login_failure(
                        adb_path,
                        serial,
                        log_lines,
                    )
                    if failure_message:
                        raise ServiceError(f"SDK 登录失败：{failure_message}")
                    try:
                        entry = AndroidUiAutomationWorker._wait_for_image(
                            adb_path,
                            serial,
                            selector_value,
                            1,
                            log_lines,
                            should_exist=True,
                            run_id=run_id,
                        )
                    except Exception:
                        time.sleep(1)
                        continue
                    break
                if entry is None:
                    raise ServiceError(f"等待图像模板超时：{selector_value}")
            else:
                AndroidUiAutomationWorker._wait_for_image(
                    adb_path,
                    serial,
                    selector_value,
                    wait_timeout,
                    log_lines,
                    should_exist=True,
                    run_id=run_id,
                )
        elif step_type == "assert_image_not_exists":
            AndroidUiAutomationWorker._wait_for_image(
                adb_path,
                serial,
                selector_value,
                wait_timeout,
                log_lines,
                should_exist=False,
                run_id=run_id,
            )
        elif step_type == "tap_image":
            node = AndroidUiAutomationWorker._wait_for_image(
                adb_path,
                serial,
                selector_value,
                wait_timeout,
                log_lines,
                should_exist=True,
                run_id=run_id,
            )
            tap_point = node["center"]
            if "sdk_agreement_checkbox" in selector_value:
                # The template includes both the checkbox and its label. The
                # center lands on the label, which does not toggle this SDK
                # control; tap the circle on the left side instead.
                rect = node.get("rect") or {}
                tap_point = {
                    "x": int(rect.get("x", tap_point["x"]) + min(60, max(8, rect.get("width", 0) * 0.22))),
                    "y": tap_point["y"],
                }
            AndroidUiAutomationWorker._tap_point(adb_path, serial, tap_point["x"], tap_point["y"], log_lines)
            result_payload["tap_point"] = tap_point
            result_payload["tap_mode"] = "image"
            if "sdk_agree_confirm" in selector_value:
                for _ in range(5):
                    AndroidUiAutomationWorker.raise_if_stop_requested(run_id)
                    time.sleep(1)
                result_payload["transition_wait_sec"] = 5
        elif step_type == "open_xianyu_user_center":
            result_payload = AndroidUiAutomationWorker._open_xianyu_user_center(
                adb_path,
                serial,
                workspace,
                log_lines,
                step,
                selector_value,
                wait_timeout,
                retry_times=int(snapshot_item.get("retry_times") or 0),
                run_id=run_id,
            )
        elif step_type == "ensure_xianyu_account_login":
            # A previously authenticated APK opens directly in-game. In that
            # state, enter the SDK through the floating icon and switch account;
            # on a fresh install the phone login page is already visible.
            deadline = time.monotonic() + max(1, wait_timeout)
            login_candidates = (
                "xianyu/sdk_login_button.png",
                "xianyu/sdk_login_button_candidate2.png",
                "xianyu/sdk_login_button_candidate3.png",
            )
            account_candidates = (
                "xianyu/sdk_account_login_switch.png",
                "xianyu/sdk_account_login_switch_candidate2.png",
                "xianyu/sdk_account_login_switch_candidate3.png",
                "xianyu/sdk_account_login_tab.png",
            )
            floating_candidates = (
                "xianyu/xianyu_floating_entry.png",
                "xianyu/floating_candidate_1.png",
                "xianyu/floating_candidate_2.png",
                "xianyu/floating_candidate_3.png",
            )
            while time.monotonic() <= deadline:
                AndroidUiAutomationWorker.raise_if_stop_requested(run_id)
                try:
                    AndroidUiAutomationWorker._wait_for_any_image(
                        adb_path,
                        serial,
                        login_candidates,
                        1,
                        log_lines,
                        run_id=run_id,
                    )
                    result_payload["branch"] = "sdk_phone_login_visible"
                except Exception:
                    pass
                if not result_payload.get("branch"):
                    try:
                        AndroidUiAutomationWorker._wait_for_any_image(
                            adb_path,
                            serial,
                            account_candidates,
                            1,
                            log_lines,
                            run_id=run_id,
                        )
                        result_payload["branch"] = "sdk_account_login_visible"
                    except Exception:
                        pass
                if result_payload.get("branch"):
                    break
                try:
                    _selector, floating = AndroidUiAutomationWorker._wait_for_any_image(
                        adb_path,
                        serial,
                        floating_candidates,
                        1,
                        log_lines,
                        run_id=run_id,
                    )
                except Exception:
                    time.sleep(1)
                    continue
                AndroidUiAutomationWorker._tap_point(
                    adb_path,
                    serial,
                    floating["center"]["x"],
                    floating["center"]["y"],
                    log_lines,
                )
                result_payload["entry_point"] = floating["center"]
                try:
                    switch_node = AndroidUiAutomationWorker._wait_for_selector(
                        adb_path,
                        serial,
                        "text",
                        "切换账号",
                        min(8, max(2, wait_timeout)),
                        log_lines,
                        should_exist=True,
                        visual_driver=visual_driver,
                        run_id=run_id,
                    )
                    if hasattr(switch_node, "click"):
                        switch_node.click()
                    else:
                        x, y = AndroidUiAutomationWorker._parse_bounds_center((switch_node.attrib or {}).get("bounds"))
                        AndroidUiAutomationWorker._tap_point(adb_path, serial, x, y, log_lines)
                    result_payload["branch"] = "floating_user_center_switch_account_text"
                    break
                except Exception:
                    pass
                try:
                    switch_selector, switch_button = AndroidUiAutomationWorker._wait_for_any_image(
                        adb_path,
                        serial,
                        ("xianyu/sdk_switch_account.png", "xianyu/sdk_switch_account_candidate2.png") + account_candidates + login_candidates,
                        min(8, max(2, wait_timeout)),
                        log_lines,
                        run_id=run_id,
                    )
                except Exception:
                    time.sleep(1)
                    continue
                if switch_selector in {"xianyu/sdk_switch_account.png", "xianyu/sdk_switch_account_candidate2.png"}:
                    AndroidUiAutomationWorker._tap_point(
                        adb_path,
                        serial,
                        switch_button["center"]["x"],
                        switch_button["center"]["y"],
                        log_lines,
                    )
                    result_payload["branch"] = "floating_user_center_switch_account"
                    break
                if switch_selector in login_candidates:
                    result_payload["branch"] = "floating_direct_sdk_phone_login"
                    break
                if switch_selector in account_candidates:
                    result_payload["branch"] = "floating_direct_sdk_account_login"
                    break
            if not result_payload.get("branch"):
                raise ServiceError("等待 SDK 登录页或游戏悬浮窗超时")
        elif step_type == "keyevent":
            AndroidUiAutomationWorker._send_keyevent(adb_path, serial, input_value or selector_value, log_lines)
        elif step_type == "screenshot":
            pass
        else:
            raise ServiceError(f"暂未支持的步骤类型：{step_type}")
        screenshot_path = ""
        if snapshot_item.get("capture_on_success") or step_type == "screenshot":
            screenshot_file = AndroidUiAutomationWorker._capture_named_screenshot(
                adb_path,
                serial,
                workspace,
                log_lines,
                f"step_{int(step.step_no):02d}.png",
                )
            screenshot_path = str(screenshot_file)
        return result_payload, screenshot_path

    @staticmethod
    def _execute_project_flow(
        adb_path,
        serial,
        workspace,
        log_lines,
        run,
        package_name="",
        activity_name="",
        progress_callback=None,
    ):
        snapshot = getattr(run, "flow_snapshot", {}) or {}
        step_snapshots = snapshot.get("steps") or []
        if not step_snapshots:
            return ""
        run_steps = AndroidUiAutomationWorker._materialize_flow_steps(run)
        latest_screenshot = ""
        failure_messages = []
        visual_driver = None
        try:
            try:
                visual_driver = AndroidUiAutomationWorker._create_visual_driver(
                    serial,
                    package_name,
                    activity_name,
                    log_lines,
                )
            except Exception as exc:
                AndroidUiAutomationWorker._log_line(log_lines, f"visual driver init failed: {exc}")
                visual_driver = None
            for index, step in enumerate(run_steps):
                AndroidUiAutomationWorker.raise_if_stop_requested(run.id)
                snapshot_item = step_snapshots[index] if index < len(step_snapshots) else {}
                started_at = AndroidUiAutomationWorker._utc_now()
                step_started_perf = time.perf_counter()
                AndroidUiAutomationService.update_run_step(
                    step.id,
                    status="running",
                    started_at=started_at,
                    raw_result={"phase": "running"},
                )
                if progress_callback:
                    progress_callback(
                        stage="launch",
                        task_name=run.task.name if run.task else "",
                        progress_text=f"执行项目流程：{step.step_name}",
                        progress_percent=None,
                    )
                capture_on_failure = bool(snapshot_item.get("capture_on_failure"))
                continue_on_failure = bool(snapshot_item.get("continue_on_failure"))
                try:
                    raw_result, screenshot_path = AndroidUiAutomationWorker._execute_flow_step(
                        adb_path,
                        serial,
                        workspace,
                        log_lines,
                        step,
                        snapshot_item,
                        visual_driver=visual_driver,
                        run_id=run.id,
                    )
                    latest_screenshot = screenshot_path or latest_screenshot
                    AndroidUiAutomationService.update_run_step(
                        step.id,
                        status="passed",
                        screenshot_path=screenshot_path,
                        finished_at=AndroidUiAutomationWorker._utc_now(),
                        duration_ms=int((time.perf_counter() - step_started_perf) * 1000),
                        raw_result=raw_result,
                    )
                    if screenshot_path:
                        AndroidUiAutomationWorker._attach_step_artifact(step, screenshot_path)
                except Exception as exc:
                    failure_screenshot = ""
                    if capture_on_failure:
                        try:
                            failure_screenshot = str(
                                AndroidUiAutomationWorker._capture_named_screenshot(
                                    adb_path,
                                    serial,
                                    workspace,
                                    log_lines,
                                    f"step_{int(step.step_no):02d}_failed.png",
                                )
                            )
                            latest_screenshot = failure_screenshot or latest_screenshot
                        except Exception:
                            failure_screenshot = ""
                    AndroidUiAutomationService.update_run_step(
                        step.id,
                        status="failed",
                        screenshot_path=failure_screenshot,
                        error_message=str(exc),
                        finished_at=AndroidUiAutomationWorker._utc_now(),
                        duration_ms=int((time.perf_counter() - step_started_perf) * 1000),
                        raw_result={"error": str(exc)},
                    )
                    if failure_screenshot:
                        AndroidUiAutomationWorker._attach_step_artifact(step, failure_screenshot)
                    failure_messages.append(f"步骤{step.step_no} {step.step_name}: {exc}")
                    if not continue_on_failure:
                        raise ServiceError("项目流程执行失败：" + " | ".join(failure_messages))
            return latest_screenshot
        finally:
            AndroidUiAutomationWorker._close_visual_driver(visual_driver)

    @staticmethod
    def _uninstall_package(adb_path, serial, package_name, log_lines):
        if not package_name:
            return
        try:
            AndroidUiAutomationWorker._run_command(
                [adb_path, "-s", serial, "uninstall", package_name],
                timeout=40,
                log_lines=log_lines,
            )
        except Exception:
            return

    @staticmethod
    def _cleanup_old_run_workspaces():
        keep_latest = int(current_app.config.get("ANDROID_UI_WORKSPACE_KEEP_LATEST_RUNS", 30))
        run_ids = [
            run.id
            for run in AndroidUiTestRun.query.order_by(AndroidUiTestRun.created_at.desc()).limit(keep_latest).all()
        ]
        root = AndroidUiAutomationWorker.workspace_root()
        for child in root.iterdir():
            if not child.is_dir():
                continue
            try:
                run_id = int(child.name)
            except ValueError:
                continue
            if run_id in run_ids:
                continue
            shutil.rmtree(child, ignore_errors=True)

    @staticmethod
    def _run_started_at(run):
        return AndroidUiAutomationWorker._parse_datetime(getattr(run, "started_at", None))

    @staticmethod
    def _should_recover_run(run, worker_health=None, now=None):
        health = worker_health or {}
        current = now or AndroidUiAutomationWorker._utc_now()
        if health.get("online"):
            return False
        started_at = AndroidUiAutomationWorker._run_started_at(run)
        if not started_at:
            return True
        stale_seconds = int(current_app.config.get("ANDROID_UI_RUN_STALE_SECONDS", 1800))
        return (current - started_at).total_seconds() >= stale_seconds

    @staticmethod
    def recover_stale_runs():
        worker_health = AndroidUiAutomationWorker.get_worker_health()
        if worker_health.get("online"):
            return []
        now = AndroidUiAutomationWorker._utc_now()
        recovered_ids = []
        for run in AndroidUiAutomationWorker.list_running_runs():
            if not AndroidUiAutomationWorker._should_recover_run(
                run,
                worker_health=worker_health,
                now=now,
            ):
                continue
            AndroidUiAutomationService.mark_run_failed(
                run.id,
                stage=run.stage or "finished",
                error_type="worker",
                error_message="Worker heartbeat lost; recovered stale running task.",
            )
            recovered_ids.append(run.id)
        return recovered_ids

    @staticmethod
    def execute_run(run_id, progress_callback=None):
        run = AndroidUiAutomationWorker.get_run(run_id)
        if run.status == "running":
            raise ServiceError("该任务正在执行中。")
        if run.status not in {"pending", "failed"}:
            raise ServiceError("当前状态不允许执行。")

        workspace = AndroidUiAutomationWorker._prepare_workspace(run)
        log_lines = []
        started = time.perf_counter()
        log_path = workspace / "execution.log"
        package_name = run.package_name or ""
        selected_device = None
        adb_path = ""

        try:
            runtime = AndroidUiAutomationWorker.validate_runtime_dependencies()
            adb_path = runtime["adb_path"]
            aapt_path = runtime["aapt_path"]
            AndroidUiAutomationWorker._log_line(
                log_lines,
                f"runtime preflight passed: adb={adb_path}; aapt={aapt_path}",
            )
            AndroidUiAutomationWorker.raise_if_stop_requested(run.id)
            task = run.task
            selected_device = AndroidUiAutomationWorker._pick_device_with_auto_start(
                adb_path,
                expected_serial=task.device_serial if task else run.device_serial,
                log_lines=log_lines,
                progress_callback=progress_callback,
                task_name=task.name if task else "",
            )
            AndroidUiAutomationService.mark_run_started(
                run.id,
                device_serial=selected_device["serial"],
                device_name=selected_device["model"],
            )
            AndroidUiAutomationWorker._materialize_flow_steps(run)
            if progress_callback:
                progress_callback(
                    stage="download",
                    task_name=task.name if task else "",
                    progress_text="已开始处理任务，准备下载 APK",
                    progress_percent=0,
                )
            AndroidUiAutomationWorker._log_line(
                log_lines,
                f"device selected: {selected_device['serial']} {selected_device['model']}".strip(),
            )

            apk_path, download_size = AndroidUiAutomationWorker._download_apk(
                task.apk_url,
                workspace,
                log_lines,
                progress_callback=progress_callback,
                package_name_hint=task.package_name if task else "",
            )
            AndroidUiAutomationWorker.raise_if_stop_requested(run.id)
            AndroidUiAutomationService.update_run_stage(
                run.id,
                "download",
                download_status="passed",
                download_path=str(apk_path),
                download_size_bytes=download_size,
                log_path=str(log_path),
            )
            if progress_callback:
                progress_callback(
                    stage="apk_parse",
                    task_name=task.name if task else "",
                    progress_text="下载完成，开始解析 APK",
                    progress_percent=100,
                )

            package_name, activity_name = AndroidUiAutomationWorker._parse_badging(
                aapt_path,
                apk_path,
                log_lines,
            )
            apk_path = AndroidUiAutomationWorker._finalize_cached_apk(
                task.apk_url,
                apk_path,
                package_name,
                log_lines,
            )
            AndroidUiAutomationWorker.raise_if_stop_requested(run.id)
            component_name = AndroidUiAutomationWorker._normalize_component(
                package_name,
                activity_name,
            )
            AndroidUiAutomationService.update_run_stage(
                run.id,
                "apk_parse",
                aapt_status="passed",
                download_path=str(apk_path),
                package_name=package_name,
                launchable_activity=activity_name,
            )
            if progress_callback:
                progress_callback(
                    stage="install",
                    task_name=task.name if task else "",
                    progress_text="APK 解析完成，开始安装",
                    progress_percent=None,
                )

            AndroidUiAutomationWorker._install_apk(
                adb_path,
                selected_device["serial"],
                apk_path,
                timeout=int(task.install_timeout_sec or 900),
                log_lines=log_lines,
            )
            AndroidUiAutomationWorker.raise_if_stop_requested(run.id)
            AndroidUiAutomationService.update_run_stage(
                run.id,
                "install",
                install_status="passed",
                package_name=package_name,
            )
            if progress_callback:
                progress_callback(
                    stage="launch",
                    task_name=task.name if task else "",
                    progress_text="安装完成，开始启动应用",
                    progress_percent=None,
                )

            launch_timeout = max(30, int(task.launch_wait_sec or 35) + 20)
            launch_error = None
            if component_name:
                try:
                    AndroidUiAutomationWorker._launch_app(
                        adb_path,
                        selected_device["serial"],
                        component_name,
                        timeout=launch_timeout,
                        log_lines=log_lines,
                    )
                except ServiceError as exc:
                    launch_error = exc
                    AndroidUiAutomationWorker._log_line(
                        log_lines,
                        f"component launch failed, fallback to package resolve: {exc}",
                    )
            else:
                AndroidUiAutomationWorker._log_line(
                    log_lines,
                    "launchable activity missing from aapt, fallback to package resolve",
                )

            if launch_error or not component_name:
                resolved_component = AndroidUiAutomationWorker._resolve_activity_via_pm(
                    adb_path,
                    selected_device["serial"],
                    package_name,
                    log_lines,
                )
                if resolved_component:
                    component_name = resolved_component
                    AndroidUiAutomationWorker._launch_app(
                        adb_path,
                        selected_device["serial"],
                        resolved_component,
                        timeout=launch_timeout,
                        log_lines=log_lines,
                    )
                    activity_name = resolved_component.split("/", 1)[1]
                    AndroidUiAutomationService.update_run_stage(
                        run.id,
                        "apk_parse",
                        aapt_status="passed",
                        package_name=package_name,
                        launchable_activity=activity_name,
                    )
                else:
                    AndroidUiAutomationWorker._launch_app_with_monkey(
                        adb_path,
                        selected_device["serial"],
                        package_name,
                        timeout=launch_timeout,
                        log_lines=log_lines,
                    )

            wait_seconds = max(3, int(task.launch_wait_sec or 35))
            for _ in range(wait_seconds):
                AndroidUiAutomationWorker.raise_if_stop_requested(run.id)
                time.sleep(1)
            if progress_callback:
                progress_callback(
                    stage="screenshot",
                    task_name=task.name if task else "",
                    progress_text="应用已启动，开始截图取证",
                    progress_percent=None,
                )
            current_focus = AndroidUiAutomationWorker._read_current_focus(
                adb_path,
                selected_device["serial"],
                log_lines,
            )
            pid = AndroidUiAutomationWorker._read_pid(
                adb_path,
                selected_device["serial"],
                package_name,
                log_lines,
            )
            AndroidUiAutomationService.update_run_stage(
                run.id,
                "launch",
                launch_status="passed",
                current_focus=current_focus,
                pid=pid,
            )

            if package_name not in current_focus and not pid:
                raise ServiceError("应用启动后未检测到前台焦点或有效进程，疑似闪退。")

            flow_screenshot_path = AndroidUiAutomationWorker._execute_project_flow(
                adb_path,
                selected_device["serial"],
                workspace,
                log_lines,
                run,
                package_name=package_name,
                activity_name=component_name or "",
                progress_callback=progress_callback,
            )
            screenshot_path = flow_screenshot_path or str(
                AndroidUiAutomationWorker._capture_screenshot(
                    adb_path,
                    selected_device["serial"],
                    workspace,
                    log_lines,
                )
            )
            AndroidUiAutomationService.update_run_stage(
                run.id,
                "screenshot",
                screenshot_path=str(screenshot_path),
                crash_status="not_detected",
            )

            AndroidUiAutomationService.mark_run_passed(
                run.id,
                screenshot_path=str(screenshot_path),
                current_focus=current_focus,
                pid=pid,
            )
            if progress_callback:
                progress_callback(
                    stage="finished",
                    task_name=task.name if task else "",
                    progress_text="执行完成",
                    progress_percent=100,
                )
        except subprocess.TimeoutExpired as exc:
            AndroidUiAutomationWorker._log_line(log_lines, f"timeout: {exc}")
            AndroidUiAutomationService.mark_run_failed(
                run.id,
                stage=run.stage or "finished",
                error_type="timeout",
                error_message=f"执行超时：{exc}",
            )
            if progress_callback:
                progress_callback(
                    stage=run.stage or "finished",
                    task_name=run.task.name if run.task else "",
                    progress_text="执行超时",
                    progress_percent=None,
                    last_error=str(exc),
                )
        except ServiceError as exc:
            AndroidUiAutomationWorker._log_line(log_lines, f"service error: {exc}")
            error_message = str(exc)
            error_type = "manual_stop" if "手动停止" in error_message else "worker"
            AndroidUiAutomationService.mark_run_failed(
                run.id,
                stage=AndroidUiAutomationWorker.get_run(run.id).stage or "finished",
                error_type=error_type,
                error_message=error_message,
            )
            if progress_callback:
                progress_callback(
                    stage=AndroidUiAutomationWorker.get_run(run.id).stage or "finished",
                    task_name=run.task.name if run.task else "",
                    progress_text="执行已停止" if error_type == "manual_stop" else "执行失败",
                    progress_percent=None,
                    last_error=error_message,
                )
        except Exception as exc:
            AndroidUiAutomationWorker._log_line(log_lines, f"error: {exc}")
            AndroidUiAutomationService.mark_run_failed(
                run.id,
                stage=AndroidUiAutomationWorker.get_run(run.id).stage or "finished",
                error_type="worker",
                error_message=str(exc),
            )
            if progress_callback:
                progress_callback(
                    stage=AndroidUiAutomationWorker.get_run(run.id).stage or "finished",
                    task_name=run.task.name if run.task else "",
                    progress_text="执行失败",
                    progress_percent=None,
                    last_error=str(exc),
                )
        finally:
            if selected_device and package_name and run.task and run.task.auto_uninstall:
                AndroidUiAutomationWorker._uninstall_package(
                    adb_path,
                    selected_device["serial"],
                    package_name,
                    log_lines,
                )
            AndroidUiAutomationWorker._log_line(
                log_lines,
                f"worker duration_ms={int((time.perf_counter() - started) * 1000)}",
            )
            log_path = AndroidUiAutomationWorker._flush_log(workspace, log_lines)
            final_run = AndroidUiAutomationWorker.get_run(run.id)
            final_run.log_path = str(log_path)
            db.session.commit()
            AndroidUiAutomationWorker.clear_stop_request(run.id)
            AndroidUiAutomationWorker._cleanup_old_run_workspaces()

        return AndroidUiAutomationWorker.get_run(run.id)
