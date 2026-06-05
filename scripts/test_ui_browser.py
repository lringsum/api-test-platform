import json
import sys
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ui_regression_registry import BROWSER_SCENARIOS


BASE_URL = "http://127.0.0.1:5000"


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


def run_scenario(session, scenario):
    if scenario["name"] == "execution_smoke":
        return run_execution_smoke(session, scenario)
    if scenario["name"] == "execution_anomaly_empty":
        return run_execution_anomaly(session, scenario)
    return {
        "name": scenario["name"],
        "module": scenario["module"],
        "kind": scenario["kind"],
        "status": "FAIL",
        "missing": ["scenario_not_implemented"],
    }


def main():
    session = requests.Session()
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
