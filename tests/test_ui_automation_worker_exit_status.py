from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from scripts import run_ui_automation_worker as worker_script


class FakeApp:
    config = {"UI_AUTOMATION_WORKER_HEARTBEAT_INTERVAL": 5}

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
    monkeypatch.setattr(worker_script, "UiAutomationWorker", fake_worker)
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
