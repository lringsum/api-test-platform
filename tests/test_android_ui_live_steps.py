from flask import Flask

from app import db
from app.models import AndroidUiRunStep, AndroidUiTestRun, AndroidUiTestTask, Project
from app.services.android_ui_automation_service import AndroidUiAutomationService


def _build_run(tmp_path, status="running"):
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'android_live_steps.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    with app.app_context():
        db.create_all()
        project = Project(name="android live project")
        db.session.add(project)
        db.session.flush()
        task = AndroidUiTestTask(
            project_id=project.id,
            name="android live task",
            package_key="android-live",
            apk_url="https://example.com/app.apk",
        )
        db.session.add(task)
        db.session.flush()
        run = AndroidUiTestRun(task_id=task.id, project_id=project.id, status=status, stage="launch")
        db.session.add(run)
        db.session.flush()
        for step_no, step_status in [(1, "passed"), (2, "running"), (3, "pending")]:
            db.session.add(
                AndroidUiRunStep(
                    run_id=run.id,
                    step_no=step_no,
                    step_name=f"step {step_no}",
                    step_type="tap",
                    status=step_status,
                )
            )
        db.session.commit()
        return app, run.id


def test_failed_run_finalizes_active_and_pending_steps(tmp_path):
    app, run_id = _build_run(tmp_path)
    with app.app_context():
        AndroidUiAutomationService.mark_run_failed(run_id, error_type="worker", error_message="device offline")
        steps = AndroidUiAutomationService.list_run_steps(run_id)
        assert [step.status for step in steps] == ["passed", "failed", "skipped"]


def test_manual_stop_finalizes_active_and_pending_steps(tmp_path):
    app, run_id = _build_run(tmp_path)
    with app.app_context():
        AndroidUiAutomationService.mark_run_failed(run_id, error_type="manual_stop", error_message="stopped")
        steps = AndroidUiAutomationService.list_run_steps(run_id)
        assert [step.status for step in steps] == ["passed", "stopped", "skipped"]
        assert steps[1].error_message == "执行已被手动停止。"


def test_passed_run_never_marks_unexecuted_step_as_passed(tmp_path):
    app, run_id = _build_run(tmp_path)
    with app.app_context():
        AndroidUiAutomationService.mark_run_passed(run_id)
        steps = AndroidUiAutomationService.list_run_steps(run_id)
        assert [step.status for step in steps] == ["passed", "passed", "skipped"]
