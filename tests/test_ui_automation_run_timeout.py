from flask import Flask

from app.services import ui_automation_worker as worker_module
from app.services.ui_automation_worker import UiAutomationWorker


class _Run:
    def __init__(self, summary=None, environment_id=1):
        self.summary = summary or {}
        self.environment_id = environment_id


class _Environment:
    def __init__(self, runtime_variables=None):
        self.runtime_variables = runtime_variables or {}


def test_worker_prefers_run_timeout_over_environment_and_config(monkeypatch):
    app = Flask(__name__)
    app.config["UI_AUTOMATION_RUN_TIMEOUT"] = 300
    run = _Run(summary={"configured_timeout_seconds": 480})
    environment = _Environment(runtime_variables={"UI_AUTOMATION_RUN_TIMEOUT": "600"})
    monkeypatch.setattr(worker_module.db.session, "get", lambda *_args, **_kwargs: environment)
    with app.app_context():
        timeout_seconds, timeout_source = UiAutomationWorker._resolve_run_timeout_seconds(run)
    assert (timeout_seconds, timeout_source) == (480, "run")


def test_worker_falls_back_to_environment_timeout(monkeypatch):
    app = Flask(__name__)
    app.config["UI_AUTOMATION_RUN_TIMEOUT"] = 300
    run = _Run()
    environment = _Environment(runtime_variables={"UI_AUTOMATION_RUN_TIMEOUT": "600"})
    monkeypatch.setattr(worker_module.db.session, "get", lambda *_args, **_kwargs: environment)
    with app.app_context():
        timeout_seconds, timeout_source = UiAutomationWorker._resolve_run_timeout_seconds(run)
    assert (timeout_seconds, timeout_source) == (600, "environment")


def test_default_timeout_is_extended_when_runtime_steps_keep_progressing():
    assert not UiAutomationWorker._has_process_timed_out(
        started_at=0,
        last_progress_at=290,
        timeout_seconds=300,
        extend_on_progress=True,
        now=301,
    )


def test_default_timeout_still_stops_a_process_without_step_progress():
    assert UiAutomationWorker._has_process_timed_out(
        started_at=0,
        last_progress_at=10,
        timeout_seconds=300,
        extend_on_progress=True,
        now=311,
    )


def test_explicit_timeout_remains_an_absolute_run_limit():
    assert UiAutomationWorker._has_process_timed_out(
        started_at=0,
        last_progress_at=290,
        timeout_seconds=300,
        extend_on_progress=False,
        now=301,
    )
