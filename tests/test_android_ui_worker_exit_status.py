from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from app.services.android_ui_automation_worker import AndroidUiAutomationWorker
from app.services.base_service import ServiceError
from scripts import run_android_ui_automation_worker as worker_script


class FakeApp:
    config = {"ANDROID_UI_WORKER_HEARTBEAT_INTERVAL": 5}

    def app_context(self):
        return nullcontext()


class FakeLock:
    instance = None

    def __init__(self, _path):
        self.released = False
        type(self).instance = self

    def acquire(self):
        return True, {}

    def release(self):
        self.released = True


class FakeMonitor:
    instance = None

    def __init__(self, _app, _interval):
        self.states = []
        self.final_state = None
        type(self).instance = self

    def start(self):
        pass

    def set_state(self, state, **payload):
        self.states.append((state, payload))

    def stop(self, final_state):
        self.final_state = final_state


def test_unexpected_failure_preserves_error_state(monkeypatch, tmp_path):
    fake_app = FakeApp()
    fake_worker = SimpleNamespace(
        worker_lock_path=lambda: tmp_path / "worker.lock",
        recover_stale_runs=lambda: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )
    monkeypatch.setattr(worker_script, "create_app", lambda: fake_app)
    monkeypatch.setattr(worker_script, "AndroidUiAutomationWorker", fake_worker)
    monkeypatch.setattr(worker_script, "SingleInstanceLock", FakeLock)
    monkeypatch.setattr(worker_script, "WorkerMonitor", FakeMonitor)
    monkeypatch.setattr(
        worker_script,
        "parse_args",
        lambda: SimpleNamespace(once=False, run_id=None, interval=0.2),
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        worker_script.main()

    assert FakeMonitor.instance.final_state == "error"
    assert FakeMonitor.instance.states == [
        ("error", {"current_run_id": None, "last_error": "database unavailable"})
    ]
    assert FakeLock.instance.released is True


def test_dependency_preflight_failure_marks_only_the_run_failed(monkeypatch, tmp_path):
    run = SimpleNamespace(
        id=7,
        status="pending",
        stage="queued",
        package_name="",
        task=None,
    )
    failures = []
    workspace = tmp_path / "7"

    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "get_run",
        staticmethod(lambda _run_id: run),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_prepare_workspace",
        staticmethod(lambda _run: (workspace.mkdir(), workspace)[1]),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "validate_runtime_dependencies",
        staticmethod(
            lambda: (_ for _ in ()).throw(ServiceError("aapt is unavailable"))
        ),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_flush_log",
        staticmethod(lambda path, _lines: path / "execution.log"),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "clear_stop_request",
        staticmethod(lambda _run_id: None),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_cleanup_old_run_workspaces",
        staticmethod(lambda: None),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_log_line",
        staticmethod(lambda lines, text: lines.append(text)),
    )
    monkeypatch.setattr(
        "app.services.android_ui_automation_worker.AndroidUiAutomationService.mark_run_failed",
        lambda run_id, **payload: failures.append({"run_id": run_id, **payload}),
    )
    monkeypatch.setattr(
        "app.services.android_ui_automation_worker.db.session.commit",
        lambda: None,
    )

    result = AndroidUiAutomationWorker.execute_run(run.id)

    assert result is run
    assert failures == [
        {
            "run_id": 7,
            "stage": "queued",
            "error_type": "worker",
            "error_message": "aapt is unavailable",
        }
    ]
