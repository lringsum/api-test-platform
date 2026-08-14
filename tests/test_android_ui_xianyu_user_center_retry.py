from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask

from app import db
from app.models import AndroidUiProjectFlow, AndroidUiProjectFlowStep, Project
from app.services.android_ui_automation_service import AndroidUiAutomationService
from app.services.android_ui_automation_worker import AndroidUiAutomationWorker
from app.services.base_service import ServiceError


def test_open_xianyu_user_center_retries_and_saves_attempt_artifacts(monkeypatch, tmp_path):
    calls = {"target": 0, "taps": [], "artifacts": []}
    step = SimpleNamespace(id=20, step_no=2)

    def wait_for_image(_adb, _serial, selector, *_args, **_kwargs):
        if selector == "xianyu/xianyu_floating_entry.png":
            return {"center": {"x": 22, "y": 585}}
        calls["target"] += 1
        if calls["target"] < 3:
            raise ServiceError("等待图像模板超时")
        return {"center": {"x": 960, "y": 150}}

    def capture(_adb, _serial, workspace, _log_lines, name):
        path = Path(workspace) / name
        path.write_bytes(b"image")
        return path

    monkeypatch.setattr(AndroidUiAutomationWorker, "_wait_for_image", staticmethod(wait_for_image))
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_tap_point",
        staticmethod(lambda _adb, _serial, x, y, _logs: calls["taps"].append((x, y))),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_capture_named_screenshot",
        staticmethod(capture),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_attach_step_artifact",
        staticmethod(lambda _step, path, artifact_type: calls["artifacts"].append((Path(path).name, artifact_type))),
    )
    monkeypatch.setattr("app.services.android_ui_automation_worker.time.sleep", lambda _seconds: None)

    result = AndroidUiAutomationWorker._open_xianyu_user_center(
        "adb.exe",
        "127.0.0.1:16384",
        tmp_path,
        [],
        step,
        "xianyu/xianyu_user_center_title.png",
        wait_timeout=8,
        retry_times=2,
    )

    assert result["attempt_count"] == 2
    assert result["confirmed_after"] == "first_tap"
    assert calls["taps"] == [(22, 585), (22, 585), (22, 585)]
    assert any("attempt_01_failed" in name for name, _kind in calls["artifacts"])
    assert any("attempt_02_user_center_confirmed" in name for name, _kind in calls["artifacts"])
    assert all(kind == "attempt_screenshot" for _name, kind in calls["artifacts"])


def test_open_xianyu_user_center_reports_all_attempt_failures(monkeypatch, tmp_path):
    step = SimpleNamespace(id=20, step_no=2)
    attempts = []

    def wait_for_image(_adb, _serial, selector, *_args, **_kwargs):
        if selector == "xianyu/xianyu_floating_entry.png":
            return {"center": {"x": 22, "y": 585}}
        raise ServiceError("等待图像模板超时：用户中心")

    def capture(_adb, _serial, workspace, _log_lines, name):
        attempts.append(name)
        path = Path(workspace) / name
        path.write_bytes(b"image")
        return path

    monkeypatch.setattr(AndroidUiAutomationWorker, "_wait_for_image", staticmethod(wait_for_image))
    monkeypatch.setattr(AndroidUiAutomationWorker, "_tap_point", staticmethod(lambda *_args: None))
    monkeypatch.setattr(AndroidUiAutomationWorker, "_capture_named_screenshot", staticmethod(capture))
    monkeypatch.setattr(AndroidUiAutomationWorker, "_attach_step_artifact", staticmethod(lambda *_args, **_kwargs: None))
    monkeypatch.setattr("app.services.android_ui_automation_worker.time.sleep", lambda _seconds: None)

    with pytest.raises(ServiceError, match="打开用户中心失败，已尝试 3 次"):
        AndroidUiAutomationWorker._open_xianyu_user_center(
            "adb.exe",
            "127.0.0.1:16384",
            tmp_path,
            [],
            step,
            "xianyu/xianyu_user_center_title.png",
            wait_timeout=8,
            retry_times=2,
        )

    assert sum("_failed.png" in name for name in attempts) == 3


def test_user_center_step_type_is_available_to_flow_configuration():
    assert (
        AndroidUiAutomationService.normalize_step_type("open_xianyu_user_center")
        == "open_xianyu_user_center"
    )


def test_delete_flow_step_reindexes_without_unique_constraint_collision(tmp_path):
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'flow_steps.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)

    with app.app_context():
        db.create_all()
        project = Project(name="flow reindex project")
        db.session.add(project)
        db.session.flush()
        flow = AndroidUiProjectFlow(
            project_id=project.id,
            name="flow reindex",
            code="flow_reindex",
        )
        db.session.add(flow)
        db.session.flush()
        for step_no in range(1, 6):
            db.session.add(
                AndroidUiProjectFlowStep(
                    flow_id=flow.id,
                    step_no=step_no,
                    sort_order=step_no,
                    step_name=f"step {step_no}",
                    step_type="sleep",
                )
            )
        db.session.commit()

        middle_step = AndroidUiProjectFlowStep.query.filter_by(
            flow_id=flow.id,
            step_no=3,
        ).one()
        AndroidUiAutomationService.delete_flow_step(middle_step.id)

        remaining = AndroidUiAutomationService.list_flow_steps(flow.id)
        assert [item.step_no for item in remaining] == [1, 2, 3, 4]
        assert [item.sort_order for item in remaining] == [1, 2, 3, 4]
