import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent


def run_gate(script_name):
    command = [sys.executable, str(SCRIPTS_DIR / script_name)]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    stdout = (completed.stdout or "").strip()
    payload = {}
    if stdout:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = {"gate": script_name, "overall": "FAIL", "raw_output": stdout}

    payload.setdefault("gate", script_name)
    payload.setdefault("overall", "PASS" if completed.returncode == 0 else "FAIL")
    payload["return_code"] = completed.returncode
    payload["stderr"] = (completed.stderr or "").strip()
    return payload


def main():
    route_result = run_gate("test_ui_routes.py")
    browser_result = run_gate("test_ui_browser.py")
    api_gate_path = SCRIPTS_DIR / "test_api_gate.py"
    if api_gate_path.exists():
        api_result = run_gate("test_api_gate.py")
    else:
        api_result = {"gate": "api", "overall": "SKIP", "reason": "scripts/test_api_gate.py not found"}

    overall = "PASSED"
    if (
        route_result["overall"] != "PASS"
        or browser_result["overall"] != "PASS"
        or api_result["overall"] not in {"PASS", "SKIP"}
    ):
        overall = "FAILED"

    summary = {
        "route": route_result,
        "browser": browser_result,
        "api": api_result,
        "overall": overall,
    }

    # Keep console output ASCII-safe to avoid GBK/UTF-8 terminal encoding crashes.
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    raise SystemExit(0 if overall == "PASSED" else 1)


if __name__ == "__main__":
    main()
