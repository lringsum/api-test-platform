from types import SimpleNamespace

import pytest
from flask import Flask

from app.services.android_ui_automation_worker import AndroidUiAutomationWorker
from app.services.base_service import ServiceError


def _build_app(**config):
    app = Flask(__name__)
    app.config.update(
        ANDROID_UI_AUTO_START_DEVICE=True,
        ANDROID_UI_DEVICE_START_WAIT_SECONDS=75,
    )
    app.config.update(config)
    return app


def test_offline_local_mumu_device_is_started_then_selected(monkeypatch):
    app = _build_app()
    calls = []
    progress = []
    log_lines = []

    def pick_device(_adb_path, expected_serial):
        calls.append(("pick", expected_serial))
        if len([call for call in calls if call[0] == "pick"]) == 1:
            raise ServiceError(f"未找到目标设备：{expected_serial}")
        return {"serial": expected_serial, "model": "MuMu"}

    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_pick_device",
        staticmethod(pick_device),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "bring_device_online",
        staticmethod(
            lambda serial, wait_seconds: calls.append(
                ("start", serial, wait_seconds)
            )
            or {"serial": serial, "auto_started": True}
        ),
    )

    with app.app_context():
        result = AndroidUiAutomationWorker._pick_device_with_auto_start(
            "adb.exe",
            expected_serial="127.0.0.1:16384",
            log_lines=log_lines,
            progress_callback=lambda **payload: progress.append(payload),
            task_name="APK smoke",
        )

    assert result == {"serial": "127.0.0.1:16384", "model": "MuMu"}
    assert calls == [
        ("pick", "127.0.0.1:16384"),
        ("start", "127.0.0.1:16384", 75),
        ("pick", "127.0.0.1:16384"),
    ]
    assert progress == [
        {
            "stage": "queued",
            "task_name": "APK smoke",
            "progress_text": "目标设备离线，正在自动启动 MuMu",
            "progress_percent": None,
        }
    ]
    assert any("auto-starting MuMu" in line for line in log_lines)
    assert any("auto-started and selected" in line for line in log_lines)


def test_auto_start_can_be_disabled(monkeypatch):
    app = _build_app(ANDROID_UI_AUTO_START_DEVICE=False)
    calls = []

    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_pick_device",
        staticmethod(
            lambda _adb_path, expected_serial: (_ for _ in ()).throw(
                ServiceError(f"未找到目标设备：{expected_serial}")
            )
        ),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "bring_device_online",
        staticmethod(lambda *_args, **_kwargs: calls.append("start")),
    )

    with app.app_context(), pytest.raises(ServiceError, match="未找到目标设备"):
        AndroidUiAutomationWorker._pick_device_with_auto_start(
            "adb.exe",
            expected_serial="127.0.0.1:16384",
        )

    assert calls == []


def test_auto_start_failure_keeps_the_cause(monkeypatch):
    app = _build_app()
    log_lines = []

    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_pick_device",
        staticmethod(
            lambda _adb_path, expected_serial: (_ for _ in ()).throw(
                ServiceError(f"未找到目标设备：{expected_serial}")
            )
        ),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "bring_device_online",
        staticmethod(
            lambda _serial, wait_seconds: (_ for _ in ()).throw(
                ServiceError("MuMu 实例启动超时")
            )
        ),
    )

    with app.app_context(), pytest.raises(
        ServiceError,
        match="自动拉起 MuMu 失败：127.0.0.1:16384。MuMu 实例启动超时",
    ):
        AndroidUiAutomationWorker._pick_device_with_auto_start(
            "adb.exe",
            expected_serial="127.0.0.1:16384",
            log_lines=log_lines,
        )

    assert any("device auto-start failed" in line for line in log_lines)


def test_mumu_cli_error_is_reported_without_undefined_variables(monkeypatch):
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_simple_run",
        staticmethod(
            lambda *_args, **_kwargs: SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="mumu command failed",
            )
        ),
    )

    with pytest.raises(ServiceError, match="读取 MuMu 实例信息失败：mumu command failed"):
        AndroidUiAutomationWorker._list_mumu_instances("mumu-cli.exe")
