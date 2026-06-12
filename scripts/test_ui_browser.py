import json
import sys
import uuid
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app, db
from app.models import (
    Execution,
    Report,
    UiAutomationArtifact,
    UiAutomationAIRecord,
    UiAutomationEnvironment,
    UiAutomationLocator,
    UiAutomationRun,
    UiAutomationRunStep,
    UiAutomationScript,
    UiAutomationScriptVersion,
    User,
)
from app.services.ui_automation_service import UiAutomationService
from app.services.ui_automation_worker import UiAutomationWorker
from scripts.ui_regression_registry import BROWSER_SCENARIOS


BASE_URL = "http://127.0.0.1:5000"


def login(session):
    session.get(f"{BASE_URL}/login", timeout=10)
    response = session.post(
        f"{BASE_URL}/login",
        data={"username": "admin", "password": "admin123"},
        timeout=10,
        allow_redirects=True,
    )
    response.raise_for_status()


def get_latest_execution_with_report():
    app = create_app()
    with app.app_context():
        report = Report.query.order_by(Report.id.desc()).first()
        if not report:
            return None, None
        execution = db.session.get(Execution, report.execution_id)
        return execution.id if execution else None, report.id


def run_execution_smoke(session, scenario):
    project_id = scenario["project_id"]
    page_response = session.get(f"{BASE_URL}/executions/run?project_id={project_id}", timeout=10)
    page_response.raise_for_status()
    html = page_response.text

    markers = [
        scenario["expected_environment_name"],
        scenario["expected_module_name"],
    ]
    missing = [marker for marker in markers if marker not in html]
    if scenario.get("expect_checklist") and "selectedTestcaseList" not in html:
        missing.append("selectedTestcaseList")
    if "加载数据" in html:
        missing.append("load_button_removed")

    options_response = session.get(
        f"{BASE_URL}/executions/api/run/options",
        params={"project_id": project_id},
        timeout=10,
    )
    options_response.raise_for_status()
    payload = options_response.json()
    data = payload.get("data") or {}
    testcase_names = [item.get("name", "") for item in data.get("testcases", [])]

    if not payload.get("success"):
        missing.append("options_api_success")
    if not data.get("environments"):
        missing.append("environments")
    if not data.get("modules"):
        missing.append("modules")
    if not any(scenario["expected_testcase_keyword"] in name for name in testcase_names):
        missing.append("testcases")

    return {
        "name": scenario["name"],
        "module": scenario["module"],
        "kind": scenario["kind"],
        "status": "PASS" if not missing else "FAIL",
        "missing": missing,
    }


def run_execution_anomaly(session, scenario):
    project_id = scenario["project_id"]
    options_response = session.get(
        f"{BASE_URL}/executions/api/run/options",
        params={"project_id": project_id},
        timeout=10,
    )
    options_response.raise_for_status()
    payload = options_response.json()
    data = payload.get("data") or {}

    is_empty = not data.get("environments") and not data.get("modules") and not data.get("testcases")
    missing = []
    if not payload.get("success"):
        missing.append("options_api_success")
    if scenario.get("expected_empty") and not is_empty:
        missing.append("expected_empty")

    return {
        "name": scenario["name"],
        "module": scenario["module"],
        "kind": scenario["kind"],
        "status": "PASS" if not missing else "FAIL",
        "missing": missing,
    }


def run_ui_locator_smoke(session, scenario):
    project_id = scenario["project_id"]
    other_project_id = scenario["other_project_id"]
    locator_code = f"gate.locator_{uuid.uuid4().hex[:8]}"
    imported_locator_code = f"gate.imported_{uuid.uuid4().hex[:8]}"
    locator_name = "门禁定位器"
    missing = []

    create_response = session.post(
        f"{BASE_URL}/ui-automation/locators/create",
        data={
            "project_id": project_id,
            "locator_name": locator_name,
            "locator_code": locator_code,
            "locator_type": "role",
            "locator_value": '{"role":"button","name":"保存"}',
            "page_name": "门禁页面",
            "page_url_pattern": "/gate",
            "description": "UI 回归门禁临时数据",
            "usage_scene": "验证定位器库创建和项目隔离",
            "is_stable": "1",
            "status": "active",
        },
        timeout=10,
        allow_redirects=True,
    )
    create_response.raise_for_status()

    try:
        page_response = session.get(
            f"{BASE_URL}/ui-automation/locators",
            params={"project_id": project_id},
            timeout=10,
        )
        page_response.raise_for_status()
        html = page_response.text
        for marker in (
            locator_name,
            locator_code,
            "定位器管理洞察",
            "引用",
            'id="locatorDrawer"',
            'id="locatorImportDrawer"',
            'id="locatorBatchActionForm"',
            'id="locatorExportButton"',
            'name="keyword"',
            'name="locator_type"',
            'name="stable"',
        ):
            if marker not in html:
                missing.append(marker)

        export_response = session.get(
            f"{BASE_URL}/ui-automation/locators/export",
            params={"project_id": project_id},
            timeout=10,
        )
        export_response.raise_for_status()
        exported_payload = export_response.json()
        exported_items = exported_payload.get("items") or []
        if not any(item.get("locator_code") == locator_code for item in exported_items):
            missing.append("locator_export")

        import_response = session.post(
            f"{BASE_URL}/ui-automation/locators/batch-import",
            data={
                "project_id": project_id,
                "batch_locators_json": json.dumps(
                    [
                        {
                            "locator_name": "批量导入定位器",
                            "locator_code": imported_locator_code,
                            "locator_type": "role",
                            "locator_value": '{"role":"button","name":"批量导入"}',
                            "page_name": "导入页",
                            "page_url_pattern": "/batch-import",
                            "description": "UI 回归批量导入数据",
                            "usage_scene": "验证定位器批量导入能力",
                            "is_stable": True,
                            "status": "active",
                        }
                    ],
                    ensure_ascii=False,
                ),
            },
            timeout=10,
            allow_redirects=True,
        )
        import_response.raise_for_status()
        if imported_locator_code not in import_response.text:
            missing.append("locator_batch_import")

        other_response = session.get(
            f"{BASE_URL}/ui-automation/locators",
            params={"project_id": other_project_id},
            timeout=10,
        )
        other_response.raise_for_status()
        if locator_code in other_response.text:
            missing.append("project_isolation")
    finally:
        app = create_app()
        with app.app_context():
            for code in (locator_code, imported_locator_code):
                locator = UiAutomationLocator.query.filter_by(
                    project_id=project_id,
                    locator_code=code,
                ).first()
                if locator:
                    db.session.delete(locator)
            db.session.commit()

    return {
        "name": scenario["name"],
        "module": scenario["module"],
        "kind": scenario["kind"],
        "status": "PASS" if not missing else "FAIL",
        "missing": missing,
    }


def run_ui_worker_smoke(session, scenario):
    project_id = scenario["project_id"]
    app = create_app()
    run_id = script_id = environment_id = None
    workspace = None
    missing = []

    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        environment = UiAutomationEnvironment(
            project_id=project_id,
            name=f"gate_worker_env_{uuid.uuid4().hex[:8]}",
            base_url=BASE_URL,
            browser_default="chromium",
            headless_default=True,
            timeout_ms=30000,
            retry_times=0,
            viewport_width=1280,
            viewport_height=720,
            storage_state_path="",
            description="UI worker regression gate",
        )
        db.session.add(environment)
        db.session.flush()
        environment_id = environment.id
        script = UiAutomationService.create_script(
            project_id=project_id,
            name="Worker 门禁脚本",
            code=f"gate_worker_{uuid.uuid4().hex[:8]}",
            description="UI worker regression gate",
            status="active",
            entry_file="tests/test_worker_gate.py",
            script_content=(
                "from playwright.sync_api import expect\n\n"
                "def test_worker_gate(page):\n"
                "    page.set_content('<h1>Worker Gate Ready</h1>')\n"
                "    expect(page.get_by_role('heading', name='Worker Gate Ready')).to_be_visible()\n"
            ),
            owner_id=admin.id,
            created_by=admin.id,
        )
        script_id = script.id
        run = UiAutomationService.create_run(
            project_id=project_id,
            script_id=script.id,
            environment_id=environment.id,
            browser_type="chromium",
            trigger_source="ui_gate",
            trigger_user_id=admin.id,
        )
        run_id = run.id

    try:
        page_response = session.get(
            f"{BASE_URL}/ui-automation/executions",
            params={"project_id": project_id},
            timeout=10,
        )
        page_response.raise_for_status()
        if "立即执行" not in page_response.text:
            missing.append("execute_button")

        execute_response = session.post(
            f"{BASE_URL}/ui-automation/executions/{run_id}/execute",
            timeout=30,
            allow_redirects=True,
        )
        execute_response.raise_for_status()

        with app.app_context():
            run = db.session.get(UiAutomationRun, run_id)
            artifacts = UiAutomationArtifact.query.filter_by(run_id=run_id).all()
            if not run or run.status != "passed":
                missing.append("worker_passed")
            if not any(item.artifact_type == "log" for item in artifacts):
                missing.append("execution_log")
            if not any(item.artifact_type == "script" for item in artifacts):
                missing.append("script_snapshot")
            workspace = UiAutomationWorker.workspace_root() / str(run_id)
    finally:
        with app.app_context():
            run = db.session.get(UiAutomationRun, run_id) if run_id else None
            script = db.session.get(UiAutomationScript, script_id) if script_id else None
            environment = (
                db.session.get(UiAutomationEnvironment, environment_id)
                if environment_id
                else None
            )
            if run:
                db.session.delete(run)
            if script:
                db.session.delete(script)
            if environment:
                db.session.delete(environment)
            db.session.commit()
        if workspace and workspace.exists():
            import shutil

            shutil.rmtree(workspace)

    return {
        "name": scenario["name"],
        "module": scenario["module"],
        "kind": scenario["kind"],
        "status": "PASS" if not missing else "FAIL",
        "missing": missing,
    }


def run_ui_script_ai_generate_smoke(session, scenario):
    project_id = scenario["project_id"]
    app = create_app()
    script_id = record_id = None
    missing = []

    script_code = f"ai_gate_{uuid.uuid4().hex[:8]}"
    script_name = "AI 生成冒烟脚本"
    goal_text = "登录后进入 Dashboard，确认页面核心统计卡片可见"

    try:
        response = session.get(
            f"{BASE_URL}/ui-automation/scripts",
            params={"project_id": project_id},
            timeout=10,
        )
        response.raise_for_status()
        markers = ("aiScriptDrawer", 'data-bs-target="#aiScriptDrawer"')
        if not any(marker in response.text for marker in markers):
            missing.append("ai_generate_button")

        generate_response = session.post(
            f"{BASE_URL}/ui-automation/scripts/ai-generate",
            data={
                "project_id": project_id,
                "script_name": script_name,
                "script_code": script_code,
                "test_goal": goal_text,
                "page_url": "/dashboard",
                "page_name": "Dashboard",
                "need_login": "1",
                "login_url": "/login",
                "login_username": "admin",
                "login_password": "admin123",
                "assert_text": "Dashboard",
                "locator_codes": "",
                "description": "UI AI 生成门禁",
                "entry_file": "tests/test_ai_generated.py",
            },
            timeout=20,
            allow_redirects=True,
        )
        generate_response.raise_for_status()

        with app.app_context():
            script = UiAutomationScript.query.filter_by(project_id=project_id, code=script_code).first()
            current_version = script.versions[0] if script and script.versions else None
            record = (
                UiAutomationAIRecord.query.filter_by(script_id=script.id, record_type="script_generate").first()
                if script
                else None
            )
            if not script or not current_version:
                missing.append("script_created")
            if not script or not script.current_version_id:
                missing.append("version_created")
            if not current_version or not current_version.ai_generated:
                missing.append("version_ai_flag")
            if not current_version or "page.goto" not in current_version.script_content:
                missing.append("generated_code")
            if not record:
                missing.append("ai_record")
            else:
                record_id = record.id
                if goal_text not in record.prompt_text:
                    missing.append("prompt_text")
            script_id = script.id if script else None
    finally:
        with app.app_context():
            record = db.session.get(UiAutomationAIRecord, record_id) if record_id else None
            script = db.session.get(UiAutomationScript, script_id) if script_id else None
            if record:
                db.session.delete(record)
            if script:
                db.session.delete(script)
            db.session.commit()

    return {
        "name": scenario["name"],
        "module": scenario["module"],
        "kind": scenario["kind"],
        "status": "PASS" if not missing else "FAIL",
        "missing": missing,
    }


def run_ui_script_version_history_smoke(session, scenario):
    project_id = scenario["project_id"]
    app = create_app()
    script_id = None
    version_one_id = None
    missing = []

    script_code = f"version_gate_{uuid.uuid4().hex[:8]}"
    script_name = "版本历史冒烟脚本"
    script_entry = "tests/test_version_gate.py"

    version_one = (
        "from playwright.sync_api import expect\n\n"
        "def test_version_one(page):\n"
        "    page.set_content('<h1>Version One</h1>')\n"
        "    expect(page.get_by_role('heading', name='Version One')).to_be_visible()\n"
    )
    version_two = (
        "from playwright.sync_api import expect\n\n"
        "def test_version_two(page):\n"
        "    page.set_content('<h1>Version Two</h1>')\n"
        "    expect(page.get_by_role('heading', name='Version Two')).to_be_visible()\n"
    )

    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        script = UiAutomationService.create_script(
            project_id=project_id,
            name=script_name,
            code=script_code,
            description="版本历史门禁",
            language="python",
            framework="playwright",
            status="active",
            tags_text="version, history",
            entry_file=script_entry,
            script_content=version_one,
            owner_id=admin.id if admin else None,
            created_by=admin.id if admin else None,
            ai_generated=False,
            ai_prompt="",
        )
        script_id = script.id
        version_one_id = script.current_version_id

    try:
        create_page = session.get(
            f"{BASE_URL}/ui-automation/scripts",
            params={"project_id": project_id},
            timeout=10,
        )
        create_page.raise_for_status()
        if "版本" not in create_page.text:
            missing.append("version_button")

        edit_response = session.post(
            f"{BASE_URL}/ui-automation/scripts/{script_id}/edit",
            data={
                "project_id": project_id,
                "name": script_name,
                "code": script_code,
                "description": "版本历史门禁",
                "language": "python",
                "framework": "playwright",
                "status": "active",
                "tags": "version, history",
                "entry_file": script_entry,
                "script_content": version_two,
                "owner_id": "",
                "change_summary": "新增第二版",
            },
            timeout=20,
            allow_redirects=True,
        )
        edit_response.raise_for_status()

        versions_page = session.get(
            f"{BASE_URL}/ui-automation/scripts/{script_id}/versions",
            timeout=10,
        )
        versions_page.raise_for_status()
        if "版本历史" not in versions_page.text:
            missing.append("versions_title")
        if "v2" not in versions_page.text:
            missing.append("v2_missing")
        if "当前版本" not in versions_page.text:
            missing.append("current_version_flag")

        restore_response = session.post(
            f"{BASE_URL}/ui-automation/scripts/{script_id}/versions/{version_one_id}/restore",
            data={"change_summary": "回滚到首版"},
            timeout=20,
            allow_redirects=True,
        )
        restore_response.raise_for_status()

        with app.app_context():
            script = db.session.get(UiAutomationScript, script_id)
            versions = UiAutomationScriptVersion.query.filter_by(script_id=script_id).order_by(UiAutomationScriptVersion.version_no.asc()).all()
            if not script or not script.current_version_id:
                missing.append("restore_current_version")
            if not versions or len(versions) < 3:
                missing.append("restore_new_version")
            if script and script.current_version_id:
                current_version = db.session.get(UiAutomationScriptVersion, script.current_version_id)
            else:
                current_version = None
            if not current_version or current_version.version_no != 3:
                missing.append("latest_version_not_3")
            if not versions or versions[-1].change_summary != "回滚到首版":
                missing.append("restore_summary")
    finally:
        with app.app_context():
            script = db.session.get(UiAutomationScript, script_id) if script_id else None
            if script:
                db.session.delete(script)
            db.session.commit()

    return {
        "name": scenario["name"],
        "module": scenario["module"],
        "kind": scenario["kind"],
        "status": "PASS" if not missing else "FAIL",
        "missing": missing,
    }


def run_ui_script_version_history_compare_smoke(session, scenario):
    project_id = scenario["project_id"]
    app = create_app()
    script_id = None
    version_one_id = None
    missing = []

    version_one = (
        "from playwright.sync_api import expect\n\n"
        "def test_version_one(page):\n"
        "    page.set_content('<h1>Version One</h1>')\n"
        "    expect(page.get_by_role('heading', name='Version One')).to_be_visible()\n"
    )
    version_two = (
        "from playwright.sync_api import expect\n\n"
        "def test_version_two(page):\n"
        "    page.set_content('<h1>Version Two</h1>')\n"
        "    expect(page.get_by_role('heading', name='Version Two')).to_be_visible()\n"
    )

    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        script_name = "脚本版本对比门禁"
        script_code = f"version_compare_gate_{uuid.uuid4().hex[:8]}"
        script_entry = "tests/test_version_compare_gate.py"
        script = UiAutomationService.create_script(
            project_id=project_id,
            name=script_name,
            code=script_code,
            description="版本对比门禁",
            language="python",
            framework="playwright",
            status="active",
            tags_text="version, compare",
            entry_file=script_entry,
            script_content=version_one,
            owner_id=admin.id if admin else None,
            created_by=admin.id if admin else None,
            ai_generated=False,
            ai_prompt="",
        )
        script_id = script.id
        version_one_id = script.current_version_id

    try:
        session.post(
            f"{BASE_URL}/ui-automation/scripts/{script_id}/edit",
            data={
                "project_id": project_id,
                "name": script_name,
                "code": script_code,
                "description": "版本对比门禁",
                "language": "python",
                "framework": "playwright",
                "status": "active",
                "tags": "version, compare",
                "entry_file": script_entry,
                "script_content": version_two,
                "owner_id": "",
                "change_summary": "新增第二版",
            },
            timeout=20,
            allow_redirects=True,
        ).raise_for_status()

        versions_page = session.get(
            f"{BASE_URL}/ui-automation/scripts/{script_id}/versions",
            timeout=10,
        )
        versions_page.raise_for_status()
        if "uiScriptVersionsPage" not in versions_page.text:
            missing.append("uiScriptVersionsPage")

        with app.app_context():
            versions = (
                UiAutomationScriptVersion.query.filter_by(script_id=script_id)
                .order_by(UiAutomationScriptVersion.version_no.asc())
                .all()
            )
        if len(versions) < 2:
            missing.append("version_count")
        else:
            compare_response = session.get(
                f"{BASE_URL}/ui-automation/scripts/{script_id}/versions/compare",
                params={
                    "from_version_id": versions[0].id,
                    "to_version_id": versions[-1].id,
                },
                timeout=10,
            )
            compare_response.raise_for_status()
            compare_html = compare_response.text
            for marker in ("uiScriptVersionComparePage", "统一差异", "返回版本历史", "Version One", "Version Two"):
                if marker not in compare_html:
                    missing.append(marker)

        restore_response = session.post(
            f"{BASE_URL}/ui-automation/scripts/{script_id}/versions/{version_one_id}/restore",
            data={"change_summary": "回滚到首版"},
            timeout=20,
            allow_redirects=True,
        )
        restore_response.raise_for_status()
    finally:
        with app.app_context():
            script = db.session.get(UiAutomationScript, script_id) if script_id else None
            if script:
                db.session.delete(script)
            db.session.commit()

    return {
        "name": scenario["name"],
        "module": scenario["module"],
        "kind": scenario["kind"],
        "status": "PASS" if not missing else "FAIL",
        "missing": missing,
    }


def run_ui_script_detail_smoke(session, scenario):
    project_id = scenario["project_id"]
    app = create_app()
    script_id = None
    missing = []

    script_code = f"detail_gate_{uuid.uuid4().hex[:8]}"
    script_name = "脚本详情冒烟脚本"
    script_content = (
        "from playwright.sync_api import expect\n\n"
        "def test_detail(page):\n"
        "    page.set_content('<h1>Detail Gate</h1>')\n"
        "    expect(page.get_by_role('heading', name='Detail Gate')).to_be_visible()\n"
    )

    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        script = UiAutomationService.create_script(
            project_id=project_id,
            name=script_name,
            code=script_code,
            description="脚本详情门禁",
            language="python",
            framework="playwright",
            status="active",
            tags_text="detail, smoke",
            entry_file="tests/test_detail_gate.py",
            script_content=script_content,
            owner_id=admin.id if admin else None,
            created_by=admin.id if admin else None,
            ai_generated=False,
            ai_prompt="",
        )
        script_id = script.id

    try:
        response = session.get(
            f"{BASE_URL}/ui-automation/scripts",
            params={"project_id": project_id},
            timeout=10,
        )
        response.raise_for_status()
        html = response.text
        for marker in ("脚本详情", "scriptDetailDrawer", "data-bs-target=\"#scriptDetailDrawer\"", script_name):
            if marker not in html:
                missing.append(marker)
    finally:
        with app.app_context():
            script = db.session.get(UiAutomationScript, script_id) if script_id else None
            if script:
                db.session.delete(script)
            db.session.commit()

    return {
        "name": scenario["name"],
        "module": scenario["module"],
        "kind": scenario["kind"],
        "status": "PASS" if not missing else "FAIL",
        "missing": missing,
    }


def run_ui_replay_smoke(session, scenario):
    project_id = scenario["project_id"]
    app = create_app()
    run_id = script_id = environment_id = None
    workspace = None
    missing = []

    script_code = f"replay_gate_{uuid.uuid4().hex[:8]}"
    script_name = "回放闂ㄧ鑴氭湰"
    script_content = (
        "from playwright.sync_api import expect\n\n"
        "def test_replay(page):\n"
        "    page.set_content('<label>Password<input aria-label=\"Password\"></label><button>Run</button><h1>Replay Gate</h1>')\n"
        "    page.get_by_label('Password').fill('secret-value')\n"
        "    page.get_by_role('button', name='Run').click()\n"
        "    expect(page.get_by_role('heading', name='Replay Gate')).to_be_visible()\n"
    )

    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        environment = UiAutomationEnvironment(
            project_id=project_id,
            name=f"gate_replay_env_{uuid.uuid4().hex[:8]}",
            base_url=BASE_URL,
            browser_default="chromium",
            headless_default=True,
            timeout_ms=30000,
            retry_times=0,
            viewport_width=1280,
            viewport_height=720,
            storage_state_path="",
            description="UI replay regression gate",
        )
        db.session.add(environment)
        db.session.flush()
        environment_id = environment.id
        script = UiAutomationService.create_script(
            project_id=project_id,
            name=script_name,
            code=script_code,
            description="UI replay regression gate",
            status="active",
            entry_file="tests/test_replay_gate.py",
            script_content=script_content,
            owner_id=admin.id,
            created_by=admin.id,
        )
        script_id = script.id
        run = UiAutomationService.create_run(
            project_id=project_id,
            script_id=script.id,
            environment_id=environment.id,
            browser_type="chromium",
            trigger_source="ui_gate",
            trigger_user_id=admin.id,
        )
        run_id = run.id

    try:
        execute_response = session.post(
            f"{BASE_URL}/ui-automation/executions/{run_id}/execute",
            timeout=30,
            allow_redirects=True,
        )
        execute_response.raise_for_status()

        with app.app_context():
            run = db.session.get(UiAutomationRun, run_id)
            artifacts = UiAutomationArtifact.query.filter_by(run_id=run_id).all()
            steps = UiAutomationRunStep.query.filter_by(run_id=run_id).order_by(UiAutomationRunStep.step_index.asc()).all()
            if not run or run.status != "passed":
                missing.append("replay_worker_passed")
            if not any(item.artifact_type == "log" for item in artifacts):
                missing.append("replay_log")
            if not any(item.artifact_type == "steps" for item in artifacts):
                missing.append("runtime_steps_artifact")
            if not any(item.artifact_type == "screenshot" for item in artifacts):
                missing.append("runtime_step_screenshots")
            if not steps:
                missing.append("replay_steps")
            elif not all(step.duration_ms > 0 for step in steps):
                missing.append("runtime_step_duration")
            elif not all(
                step.raw_log
                and step.raw_log[0].get("source") == "runtime"
                and step.raw_log[0].get("method")
                for step in steps
            ):
                missing.append("runtime_step_metadata")
            methods = {
                step.raw_log[0].get("method")
                for step in steps
                if step.raw_log
            }
            if not {"set_content", "fill", "click", "to_be_visible"}.issubset(methods):
                missing.append("runtime_step_methods")
            password_step = next(
                (
                    step
                    for step in steps
                    if step.raw_log
                    and step.raw_log[0].get("method") == "fill"
                ),
                None,
            )
            if not password_step or password_step.input_value != "******":
                missing.append("runtime_step_secret_mask")
            if not run or run.summary.get("step_source") != "runtime":
                missing.append("runtime_step_source")
            workspace = UiAutomationWorker.workspace_root() / str(run_id)

        list_response = session.get(
            f"{BASE_URL}/ui-automation/replays",
            params={"project_id": project_id},
            timeout=10,
        )
        list_response.raise_for_status()
        list_html = list_response.text
        for marker in ("uiReplayPage", "replayFilterForm", script_name, script_code):
            if marker not in list_html:
                missing.append(marker)

        detail_response = session.get(f"{BASE_URL}/ui-automation/replays/{run_id}", timeout=10)
        detail_response.raise_for_status()
        detail_html = detail_response.text
        for marker in (
            "uiReplayDetailPage",
            "基础信息",
            "日志浏览",
            "执行步骤与页面截图",
            script_name,
        ):
            if marker not in detail_html:
                missing.append(marker)
        for marker in ("设置页面内容", "断言结果", "运行时采集", "方法 set_content", "查看大图"):
            if marker not in detail_html:
                missing.append(marker)
    finally:
        with app.app_context():
            run = db.session.get(UiAutomationRun, run_id) if run_id else None
            script = db.session.get(UiAutomationScript, script_id) if script_id else None
            environment = (
                db.session.get(UiAutomationEnvironment, environment_id)
                if environment_id
                else None
            )
            if run:
                db.session.delete(run)
            if script:
                db.session.delete(script)
            if environment:
                db.session.delete(environment)
            db.session.commit()
        if workspace and workspace.exists():
            import shutil

            shutil.rmtree(workspace)

    return {
        "name": scenario["name"],
        "module": scenario["module"],
        "kind": scenario["kind"],
        "status": "PASS" if not missing else "FAIL",
        "missing": missing,
    }


def run_ui_script_repair_smoke(session, scenario):
    project_id = scenario["project_id"]
    app = create_app()
    run_id = script_id = environment_id = None
    workspace = None
    missing = []

    script_code = f"repair_gate_{uuid.uuid4().hex[:8]}"
    script_name = "AI 修复门禁脚本"
    script_content = (
        "from playwright.sync_api import expect\n\n"
        "def test_repair(page):\n"
        "    page.set_content('<h1>Repair Gate</h1>')\n"
        "    expect(page.get_by_role('heading', name='Missing Heading')).to_be_visible()\n"
    )

    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        environment = UiAutomationEnvironment(
            project_id=project_id,
            name=f"gate_repair_env_{uuid.uuid4().hex[:8]}",
            base_url=BASE_URL,
            browser_default="chromium",
            headless_default=True,
            timeout_ms=30000,
            retry_times=0,
            viewport_width=1280,
            viewport_height=720,
            storage_state_path="",
            description="UI repair regression gate",
        )
        db.session.add(environment)
        db.session.flush()
        environment_id = environment.id
        script = UiAutomationService.create_script(
            project_id=project_id,
            name=script_name,
            code=script_code,
            description="UI repair regression gate",
            status="active",
            entry_file="tests/test_repair_gate.py",
            script_content=script_content,
            owner_id=admin.id,
            created_by=admin.id,
        )
        script_id = script.id
        run = UiAutomationService.create_run(
            project_id=project_id,
            script_id=script.id,
            environment_id=environment.id,
            browser_type="chromium",
            trigger_source="ui_gate",
            trigger_user_id=admin.id,
        )
        run_id = run.id

    try:
        execute_response = session.post(
            f"{BASE_URL}/ui-automation/executions/{run_id}/execute",
            timeout=30,
            allow_redirects=True,
        )
        execute_response.raise_for_status()

        with app.app_context():
            run = db.session.get(UiAutomationRun, run_id)
            if not run or run.status == "passed":
                missing.append("repair_failed_run")
            if not (run and run.summary.get("failure_analysis")):
                missing.append("failure_analysis")
            workspace = UiAutomationWorker.workspace_root() / str(run_id)

        detail_response = session.get(f"{BASE_URL}/ui-automation/replays/{run_id}", timeout=10)
        detail_response.raise_for_status()
        detail_html = detail_response.text
        for marker in ("执行失败", "建议：", "执行步骤与页面截图"):
            if marker not in detail_html:
                missing.append(marker)

        with app.app_context():
            version_count_before = UiAutomationScriptVersion.query.filter_by(script_id=script_id).count()

        repair_response = session.post(
            f"{BASE_URL}/ui-automation/scripts/{script_id}/ai-repair",
            data={
                "run_id": run_id,
                "auto_execute": "0",
                "instruction": "优先修复失败断言，尽量保留原脚本结构。",
                "locator_codes": "",
            },
            timeout=30,
            allow_redirects=True,
        )
        repair_response.raise_for_status()

        with app.app_context():
            script = db.session.get(UiAutomationScript, script_id)
            versions = (
                UiAutomationScriptVersion.query.filter_by(script_id=script_id)
                .order_by(UiAutomationScriptVersion.version_no.asc())
                .all()
            )
            record = UiAutomationAIRecord.query.filter_by(script_id=script_id, record_type="script_repair").first()
            if len(versions) <= version_count_before:
                missing.append("repair_version_created")
            if not record:
                missing.append("repair_ai_record")
            elif "执行失败分析" not in record.prompt_text or "修复要求" not in record.prompt_text:
                missing.append("repair_prompt")
            if not script or script.current_version_id != versions[-1].id:
                missing.append("repair_current_version")
    finally:
        with app.app_context():
            run = db.session.get(UiAutomationRun, run_id) if run_id else None
            script = db.session.get(UiAutomationScript, script_id) if script_id else None
            environment = (
                db.session.get(UiAutomationEnvironment, environment_id)
                if environment_id
                else None
            )
            if run:
                db.session.delete(run)
            if script:
                db.session.delete(script)
            if environment:
                db.session.delete(environment)
            db.session.commit()
        if workspace and workspace.exists():
            import shutil

            shutil.rmtree(workspace)

    return {
        "name": scenario["name"],
        "module": scenario["module"],
        "kind": scenario["kind"],
        "status": "PASS" if not missing else "FAIL",
        "missing": missing,
    }


def run_ui_script_batch_smoke(session, scenario):
    project_id = scenario["project_id"]
    app = create_app()
    imported_codes = []
    generated_codes = []
    record_ids = []
    missing = []

    batch_import_items = [
        {
            "name": "Batch Import Alpha",
            "code": f"batch_import_{uuid.uuid4().hex[:8]}",
            "description": "批量导入烟测 A",
            "status": "draft",
            "entry_file": "tests/test_batch_import_a.py",
            "script_content": (
                "from playwright.sync_api import expect\n\n"
                "def test_batch_import_alpha(page):\n"
                "    page.set_content('<h1>Batch Import Alpha</h1>')\n"
                "    expect(page.get_by_role('heading', name='Batch Import Alpha')).to_be_visible()\n"
            ),
        },
        {
            "name": "Batch Import Beta",
            "code": f"batch_import_{uuid.uuid4().hex[:8]}",
            "description": "批量导入烟测 B",
            "status": "active",
            "entry_file": "tests/test_batch_import_b.py",
            "script_content": (
                "from playwright.sync_api import expect\n\n"
                "def test_batch_import_beta(page):\n"
                "    page.set_content('<h1>Batch Import Beta</h1>')\n"
                "    expect(page.get_by_role('heading', name='Batch Import Beta')).to_be_visible()\n"
            ),
        },
    ]
    batch_generate_items = [
        {
            "script_name": "Batch Generate Alpha",
            "script_code": f"batch_generate_{uuid.uuid4().hex[:8]}",
            "test_goal": "打开 Dashboard 并校验标题",
            "page_url": "/dashboard",
            "page_name": "Dashboard",
            "need_login": "1",
            "login_url": "/login",
            "login_username": "admin",
            "login_password": "admin123",
            "assert_text": "Dashboard",
            "locator_codes": "",
            "description": "批量生成烟测 A",
            "entry_file": "tests/test_batch_generate_a.py",
        }
    ]

    try:
        page_response = session.get(
            f"{BASE_URL}/ui-automation/scripts",
            params={"project_id": project_id},
            timeout=10,
        )
        page_response.raise_for_status()
        html = page_response.text
        for marker in ("batchImportDrawer", "batchGenerateDrawer", "批量导入", "批量生成"):
            if marker not in html:
                missing.append(marker)

        import_response = session.post(
            f"{BASE_URL}/ui-automation/scripts/batch-import",
            data={
                "project_id": project_id,
                "batch_scripts_json": json.dumps(batch_import_items, ensure_ascii=False),
            },
            timeout=20,
            allow_redirects=True,
        )
        import_response.raise_for_status()
        imported_codes = [item["code"] for item in batch_import_items]

        generate_response = session.post(
            f"{BASE_URL}/ui-automation/scripts/batch-generate",
            data={
                "project_id": project_id,
                "batch_jobs_json": json.dumps(batch_generate_items, ensure_ascii=False),
            },
            timeout=30,
            allow_redirects=True,
        )
        generate_response.raise_for_status()
        generated_codes = [item["script_code"] for item in batch_generate_items]

        list_response = session.get(
            f"{BASE_URL}/ui-automation/scripts",
            params={"project_id": project_id},
            timeout=10,
        )
        list_response.raise_for_status()
        list_html = list_response.text
        for marker in ["Batch Import Alpha", "Batch Import Beta", "Batch Generate Alpha", *imported_codes, *generated_codes]:
            if marker not in list_html:
                missing.append(marker)

        with app.app_context():
            for code in imported_codes + generated_codes:
                script = UiAutomationScript.query.filter_by(project_id=project_id, code=code).first()
                if not script:
                    missing.append(f"missing_script:{code}")
                    continue
                if code in generated_codes:
                    record = UiAutomationAIRecord.query.filter_by(script_id=script.id, record_type="script_generate").first()
                    if not record:
                        missing.append(f"missing_ai_record:{code}")
                    else:
                        record_ids.append(record.id)
    finally:
        with app.app_context():
            records = UiAutomationAIRecord.query.filter(UiAutomationAIRecord.id.in_(record_ids)).all() if record_ids else []
            for record in records:
                db.session.delete(record)
            scripts = UiAutomationScript.query.filter(
                UiAutomationScript.project_id == project_id,
                UiAutomationScript.code.in_(imported_codes + generated_codes),
            ).all()
            for script in scripts:
                db.session.delete(script)
            db.session.commit()

    return {
        "name": scenario["name"],
        "module": scenario["module"],
        "kind": scenario["kind"],
        "status": "PASS" if not missing else "FAIL",
        "missing": missing,
    }


def run_scenario(session, scenario):
    if scenario["name"] == "execution_smoke":
        return run_execution_smoke(session, scenario)
    if scenario["name"] == "execution_anomaly_empty":
        return run_execution_anomaly(session, scenario)
    if scenario["name"] == "execution_report_smoke":
        execution_id, report_id = get_latest_execution_with_report()
        if not execution_id or not report_id:
            return {
                "name": scenario["name"],
                "module": scenario["module"],
                "kind": scenario["kind"],
                "status": "FAIL",
                "missing": ["latest_report"],
            }
        execution_response = session.get(f"{BASE_URL}/executions/{execution_id}", timeout=10)
        execution_response.raise_for_status()
        execution_html = execution_response.text
        report_response = session.get(f"{BASE_URL}/executions/{execution_id}/report", timeout=10, allow_redirects=True)
        report_response.raise_for_status()
        report_html = report_response.text
        missing = []
        if "报告回放" not in execution_html:
            missing.append("execution_report_panel")
        if "查看执行详情" not in report_html:
            missing.append("report_back_link")
        if "回放" not in report_html:
            missing.append("report_title_marker")
        return {
            "name": scenario["name"],
            "module": scenario["module"],
            "kind": scenario["kind"],
            "status": "PASS" if not missing else "FAIL",
            "missing": missing,
        }
    if scenario["name"] == "ui_locator_smoke":
        return run_ui_locator_smoke(session, scenario)
    if scenario["name"] == "ui_worker_smoke":
        return run_ui_worker_smoke(session, scenario)
    if scenario["name"] == "ui_script_ai_generate_smoke":
        return run_ui_script_ai_generate_smoke(session, scenario)
    if scenario["name"] == "ui_script_version_history_smoke":
        return run_ui_script_version_history_compare_smoke(session, scenario)
    if scenario["name"] == "ui_script_detail_smoke":
        return run_ui_script_detail_smoke(session, scenario)
    if scenario["name"] == "ui_replay_smoke":
        return run_ui_replay_smoke(session, scenario)
    if scenario["name"] == "ui_script_repair_smoke":
        return run_ui_script_repair_smoke(session, scenario)
    if scenario["name"] == "ui_script_batch_smoke":
        return run_ui_script_batch_smoke(session, scenario)
    return {
        "name": scenario["name"],
        "module": scenario["module"],
        "kind": scenario["kind"],
        "status": "FAIL",
        "missing": ["scenario_not_implemented"],
    }


def main():
    session = requests.Session()
    login(session)
    results = [run_scenario(session, scenario) for scenario in BROWSER_SCENARIOS]
    overall = "PASS" if all(item["status"] == "PASS" for item in results) else "FAIL"

    payload = {
        "gate": "browser",
        "overall": overall,
        "results": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(0 if overall == "PASS" else 1)


if __name__ == "__main__":
    main()
