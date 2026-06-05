import json
import sys
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ui_regression_registry import PAGE_REGISTRY


BASE_URL = "http://127.0.0.1:5000"


def check_page(session, spec):
    response = session.get(f"{BASE_URL}{spec.path}", timeout=10)
    response.raise_for_status()
    html = response.text

    missing = []
    if spec.page_title not in html:
        missing.append(f"page_title={spec.page_title}")

    for marker in spec.ready_markers:
        if marker not in html:
            missing.append(f"marker={marker}")

    return {
        "name": spec.name,
        "module": spec.module,
        "path": spec.path,
        "status": "PASS" if not missing else "FAIL",
        "missing": missing,
    }


def main():
    session = requests.Session()
    results = [check_page(session, spec) for spec in PAGE_REGISTRY]
    overall = "PASS" if all(item["status"] == "PASS" for item in results) else "FAIL"

    payload = {
        "gate": "route",
        "overall": overall,
        "results": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(0 if overall == "PASS" else 1)


if __name__ == "__main__":
    main()
