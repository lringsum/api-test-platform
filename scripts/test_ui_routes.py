import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ui_regression_registry import PAGE_REGISTRY


BASE_URL = "http://127.0.0.1:5000"
SPA_MARKERS = ('<div id="app"></div>', '/app/assets/')


def login(session):
    response = session.post(
        f"{BASE_URL}/login",
        data={"username": "admin", "password": "admin123"},
        timeout=10,
        allow_redirects=True,
    )
    response.raise_for_status()


def check_page(session, spec):
    response = session.get(f"{BASE_URL}{spec.legacy_path}", timeout=10)
    response.raise_for_status()
    final_path = urlparse(response.url).path.rstrip("/") or "/"
    expected_path = spec.spa_path.rstrip("/") or "/"
    missing = []
    if final_path != expected_path:
        missing.append(f"redirect={final_path}")
    for marker in SPA_MARKERS:
        if marker not in response.text:
            missing.append(f"spa_marker={marker}")
    return {"name": spec.name, "module": spec.module, "path": spec.legacy_path, "status": "PASS" if not missing else "FAIL", "missing": missing}


def main():
    session = requests.Session()
    login(session)
    results = [check_page(session, spec) for spec in PAGE_REGISTRY]
    overall = "PASS" if all(item["status"] == "PASS" for item in results) else "FAIL"
    print(json.dumps({"gate": "route", "overall": overall, "results": results}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if overall == "PASS" else 1)


if __name__ == "__main__":
    main()
