import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from flask import Flask

from app.services import ui_automation_worker as worker_module
from app.services.ui_automation_worker import UiAutomationWorker


class _FakeRun:
    def __init__(self, run_id, started_at):
        self.id = run_id
        self.status = "running"
        self.started_at = started_at
        self.finished_at = None
        self.error_stage = ""
        self.error_message = ""
        self.summary = {}


def _build_app(tmp_path):
    app = Flask(__name__, instance_path=str(tmp_path / "instance"))
    app.config["UI_AUTOMATION_WORKER_STALE_SECONDS"] = 30
    app.config["UI_AUTOMATION_RUN_STALE_SECONDS"] = 60
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    return app


def test_worker_health_is_online_with_recent_heartbeat(tmp_path):
    app = _build_app(tmp_path)
    with app.app_context():
        UiAutomationWorker.write_worker_status(
            {
                "pid": os.getpid(),
                "state": "idle",
                "current_run_id": None,
                "last_heartbeat_at": datetime.now(UTC).isoformat(),
                "python_executable": "python",
            }
        )
        health = UiAutomationWorker.get_worker_health()

    assert health["online"] is True
    assert health["state"] == "idle"


def test_worker_health_is_offline_when_heartbeat_is_stale(tmp_path):
    app = _build_app(tmp_path)
    with app.app_context():
        UiAutomationWorker.write_worker_status(
            {
                "pid": os.getpid(),
                "state": "idle",
                "current_run_id": None,
                "last_heartbeat_at": (
                    datetime.now(UTC) - timedelta(seconds=120)
                ).isoformat(),
                "python_executable": "python",
            }
        )
        health = UiAutomationWorker.get_worker_health()

    assert health["online"] is False


def test_recover_stale_runs_marks_orphaned_run_failed(tmp_path, monkeypatch):
    app = _build_app(tmp_path)
    run = _FakeRun(
        run_id=34,
        started_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=10),
    )
    workspace = tmp_path / "instance" / "ui_automation" / "runs" / "34"
    workspace.mkdir(parents=True, exist_ok=True)
    step_path = workspace / "runtime-steps.jsonl"
    step_path.write_text("[]\n", encoding="utf-8")
    stale_time = datetime.now(UTC) - timedelta(minutes=5)
    os.utime(step_path, (stale_time.timestamp(), stale_time.timestamp()))

    committed = {"called": False}

    monkeypatch.setattr(
        worker_module.UiAutomationWorker,
        "list_running_runs",
        staticmethod(lambda: [run]),
    )
    monkeypatch.setattr(
        worker_module.db.session,
        "commit",
        lambda: committed.__setitem__("called", True),
    )

    with app.app_context():
        UiAutomationWorker.write_worker_status(
            {
                "pid": 999999,
                "state": "running",
                "current_run_id": 34,
                "last_heartbeat_at": (
                    datetime.now(UTC) - timedelta(minutes=5)
                ).isoformat(),
                "python_executable": "python",
            }
        )
        recovered_ids = UiAutomationWorker.recover_stale_runs()

    assert recovered_ids == [34]
    assert run.status == "failed"
    assert run.error_stage == "worker"
    assert run.summary["worker_recovered"] is True
    assert committed["called"] is True
