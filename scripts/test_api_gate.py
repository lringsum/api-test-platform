import json
import sys
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ui_regression_registry import API_SCENARIOS


BASE_URL = "http://127.0.0.1:5000"


def execute_request(session, scenario):
    method = scenario["method"].upper()
    kwargs = {"timeout": 10}
    if "params" in scenario:
        kwargs["params"] = scenario["params"]
    if "json" in scenario:
        kwargs["json"] = scenario["json"]
    response = session.request(method, f"{BASE_URL}{scenario['path']}", **kwargs)
    response.raise_for_status()
    return response.json()


def validate_payload(payload, scenario):
    missing = []
    success = payload.get("success")
    if success is not scenario.get("expect_success", True):
        missing.append("success_flag")

    data = payload.get("data") or {}
    for key in scenario.get("expect_non_empty_keys", ()):
        if not data.get(key):
            missing.append(f"{key}_non_empty")

    for key in scenario.get("expect_empty_keys", ()):
        if data.get(key):
            missing.append(f"{key}_empty")

    return missing


def run_scenario(session, scenario):
    payload = execute_request(session, scenario)
    missing = validate_payload(payload, scenario)
    return {
        "name": scenario["name"],
        "module": scenario["module"],
        "method": scenario["method"],
        "path": scenario["path"],
        "status": "PASS" if not missing else "FAIL",
        "missing": missing,
    }


def main():
    session = requests.Session()
    results = [run_scenario(session, scenario) for scenario in API_SCENARIOS]
    overall = "PASS" if all(item["status"] == "PASS" for item in results) else "FAIL"
    payload = {
        "gate": "api",
        "overall": overall,
        "results": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(0 if overall == "PASS" else 1)


if __name__ == "__main__":
    main()
