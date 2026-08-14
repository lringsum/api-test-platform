from types import SimpleNamespace

from flask import Flask

from app.services.android_ui_automation_worker import AndroidUiAutomationWorker


def _build_app(tmp_path):
    instance_path = tmp_path / "instance"
    instance_path.mkdir(parents=True, exist_ok=True)
    return Flask(__name__, instance_path=str(instance_path))


def test_force_stop_run_terminates_current_worker_and_restarts(tmp_path, monkeypatch):
    app = _build_app(tmp_path)
    run = SimpleNamespace(id=50, status="running", stage="install")
    events = []

    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "get_run",
        staticmethod(lambda run_id: run),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "get_worker_health",
        staticmethod(
            lambda: {
                "pid": 3456,
                "online": True,
                "current_run_id": 50,
                "python_executable": "python.exe",
                "script": "scripts/run_android_ui_automation_worker.py",
            }
        ),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "terminate_worker_process",
        staticmethod(lambda pid: events.append(("terminate", pid)) or True),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "clear_stop_request",
        staticmethod(lambda run_id: events.append(("clear_stop", run_id))),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "write_worker_status",
        staticmethod(lambda payload: events.append(("write_status", payload.get("state"), payload.get("current_run_id")))),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "start_worker_process",
        staticmethod(lambda: events.append(("restart", None)) or {"pid": 7890}),
    )

    service_events = []
    monkeypatch.setattr(
        "app.services.android_ui_automation_worker.AndroidUiAutomationService.mark_run_failed",
        lambda run_id, stage="", error_type="", error_message="": service_events.append(
            (run_id, stage, error_type, error_message)
        ),
    )

    with app.app_context():
        result = AndroidUiAutomationWorker.force_stop_run(50, requested_by=9)

    assert result["state"] == "stopped"
    assert result["worker_terminated"] is True
    assert result["worker_restarted"] is True
    assert ("terminate", 3456) in events
    assert ("clear_stop", 50) in events
    assert ("restart", None) in events
    assert ("write_status", "stopped", None) in events
    assert service_events == [(50, "install", "manual_stop", "任务已被手动终止。")]


def test_force_stop_run_marks_pending_without_worker_restart(tmp_path, monkeypatch):
    app = _build_app(tmp_path)
    run = SimpleNamespace(id=12, status="pending", stage="queued")
    events = []

    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "get_run",
        staticmethod(lambda run_id: run),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "clear_stop_request",
        staticmethod(lambda run_id: events.append(("clear_stop", run_id))),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "start_worker_process",
        staticmethod(lambda: events.append(("restart", None)) or {"pid": 7890}),
    )

    service_events = []
    monkeypatch.setattr(
        "app.services.android_ui_automation_worker.AndroidUiAutomationService.mark_run_failed",
        lambda run_id, stage="", error_type="", error_message="": service_events.append(
            (run_id, stage, error_type, error_message)
        ),
    )

    with app.app_context():
        result = AndroidUiAutomationWorker.force_stop_run(12, requested_by=9)

    assert result == {"run_id": 12, "state": "stopped", "worker_restarted": False}
    assert events == [("clear_stop", 12)]
    assert service_events == [(12, "queued", "manual_stop", "任务已手动终止，未进入执行。")]
