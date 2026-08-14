import json

from flask import Flask

from app import db
from app.models import Project, UiAutomationRun, UiAutomationRunStep, UiAutomationScript, UiAutomationScriptVersion
from app.services.ui_automation_worker import UiAutomationWorker


def _create_run(tmp_path):
    app = Flask(__name__, instance_path=str(tmp_path / "instance"))
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'live_steps.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    with app.app_context():
        db.create_all()
        project = Project(name="live steps project")
        db.session.add(project)
        db.session.flush()
        script = UiAutomationScript(project_id=project.id, name="live", code="live", status="active")
        db.session.add(script)
        db.session.flush()
        version = UiAutomationScriptVersion(script_id=script.id, version_no=1, script_content="def test_live():\n    pass\n")
        db.session.add(version)
        db.session.flush()
        script.current_version_id = version.id
        run = UiAutomationRun(
            project_id=project.id,
            script_id=script.id,
            script_version_id=version.id,
            status="running",
        )
        db.session.add(run)
        db.session.commit()
        return app, run.id


def test_runtime_step_events_are_deduplicated_and_updated(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    step_file = workspace / "runtime-steps.jsonl"
    events = [
        {"attempt": 1, "sequence": 1, "step_type": "click", "step_title": "点击查询", "status": "running"},
        {"attempt": 1, "sequence": 1, "step_type": "click", "step_title": "点击查询", "status": "passed", "duration_ms": 120},
        {"attempt": 1, "sequence": 2, "step_type": "assert", "step_title": "断言结果", "status": "running"},
    ]
    step_file.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in events), encoding="utf-8")

    loaded = UiAutomationWorker._load_runtime_steps(workspace)

    assert len(loaded) == 2
    assert loaded[0]["status"] == "passed"
    assert loaded[0]["duration_ms"] == 120
    assert loaded[1]["status"] == "running"


def test_incremental_sync_updates_existing_step_without_duplicates(tmp_path):
    app, run_id = _create_run(tmp_path)
    with app.app_context():
        run = db.session.get(UiAutomationRun, run_id)
        UiAutomationWorker._sync_runtime_steps(
            run,
            [{"attempt": 1, "sequence": 1, "step_type": "click", "step_title": "点击查询", "status": "running"}],
        )
        UiAutomationWorker._sync_runtime_steps(
            run,
            [{"attempt": 1, "sequence": 1, "step_type": "click", "step_title": "点击查询", "status": "passed", "duration_ms": 120}],
        )

        steps = UiAutomationRunStep.query.filter_by(run_id=run_id).all()
        assert len(steps) == 1
        assert steps[0].status == "passed"
        assert steps[0].duration_ms == 120
