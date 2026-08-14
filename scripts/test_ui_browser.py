import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ui_regression_registry import BROWSER_SCENARIOS


BASE_URL = "http://127.0.0.1:5000"


def login(session):
    response = session.post(
        f"{BASE_URL}/login",
        data={"username": "admin", "password": "admin123"},
        timeout=10,
        allow_redirects=True,
    )
    response.raise_for_status()


def result(scenario, missing):
    return {
        "name": scenario["name"],
        "module": scenario["module"],
        "kind": scenario["kind"],
        "status": "PASS" if not missing else "FAIL",
        "missing": missing,
    }


def run_scenario(session, scenario):
    name = scenario["name"]
    if name == "vue_shell":
        response = session.get(f"{BASE_URL}/app/projects", timeout=10)
        response.raise_for_status()
        missing = [marker for marker in ('<div id="app"></div>', '/app/assets/') if marker not in response.text]
        return result(scenario, missing)
    if name == "navigation_hierarchy":
        shell = (ROOT / "frontend" / "src" / "components" / "AppShell.vue").read_text(encoding="utf-8")
        required = ("navigationGroups", "a-sub-menu", "api-testing", "automation", "execution", "security", "activeGroupKey", "app-workspace", "overflow-hidden")
        return result(scenario, [marker for marker in required if marker not in shell])
    if name == "ai_features_removed":
        shell = (ROOT / "frontend" / "src" / "components" / "AppShell.vue").read_text(encoding="utf-8")
        web_page = (ROOT / "frontend" / "src" / "views" / "WebAutomationPage.vue").read_text(encoding="utf-8")
        router = (ROOT / "frontend" / "src" / "router.ts").read_text(encoding="utf-8")
        forbidden = ("AI 解析", "Prompt 模板", "AI 生成", "AI 修复", "name: 'ai'", "name: 'prompts'")
        sources = {"shell": shell, "web": web_page, "router": router}
        missing = [f"{name}:{marker}" for name, source in sources.items() for marker in forbidden if marker in source]
        return result(scenario, missing)
    if name == "android_screenshot_preview":
        page = (ROOT / "frontend" / "src" / "views" / "AndroidAutomationPage.vue").read_text(encoding="utf-8")
        required = ("screenshotPreviewOpen", "handleScreenshotLink", "event.preventDefault()", "mask-closable", "执行步骤截图")
        return result(scenario, [marker for marker in required if marker not in page])
    if name == "web_replay_drawer":
        page = (ROOT / "frontend" / "src" / "views" / "WebAutomationPage.vue").read_text(encoding="utf-8")
        required = ("replayDrawerOpen", "执行详情与产物", "openArtifactPreview", "screenshotPreviewOpen", "screenshotUrl", "<a-drawer")
        missing = [marker for marker in required if marker not in page]
        missing.extend(f"unexpected:{marker}" for marker in ("nonScreenshotArtifacts", "artifact-grid") if marker in page)
        return result(scenario, missing)
    if name == "web_locator_page_filter":
        page = (ROOT / "frontend" / "src" / "views" / "WebAutomationPage.vue").read_text(encoding="utf-8")
        required = ("locatorPageGroups", "filteredLocators", "页面功能", "locator-page-chip", "locatorKeyword", "页面功能筛选")
        return result(scenario, [marker for marker in required if marker not in page])
    if name == "web_locator_filter_safety":
        page = (ROOT / "frontend" / "src" / "views" / "WebAutomationPage.vue").read_text(encoding="utf-8")
        required = ("UNCLASSIFIED_LOCATOR_PAGE", "clearLocatorSelection", "watch(locatorKeyword", "watch(() => platform.activeProjectId", "locatorCurrentPage.value = 1")
        return result(scenario, [marker for marker in required if marker not in page])
    if name == "automation_live_progress":
        web_page = (ROOT / "frontend" / "src" / "views" / "WebAutomationPage.vue").read_text(encoding="utf-8")
        android_page = (ROOT / "frontend" / "src" / "views" / "AndroidAutomationPage.vue").read_text(encoding="utf-8")
        web_required = ("refreshReplay", "scheduleReplayPolling", "实时更新中", "已记录 {{ replay.steps.length }} 步")
        android_required = ("refreshRunDetail", "scheduleDetailPolling", "selectedRunProgress", "步骤进度", "已跳过")
        missing = [f"web:{marker}" for marker in web_required if marker not in web_page]
        missing.extend(f"android:{marker}" for marker in android_required if marker not in android_page)
        return result(scenario, missing)
    if name == "automation_toolbar_layout":
        web_page = (ROOT / "frontend" / "src" / "views" / "WebAutomationPage.vue").read_text(encoding="utf-8")
        android_page = (ROOT / "frontend" / "src" / "views" / "AndroidAutomationPage.vue").read_text(encoding="utf-8")
        required = ("automation-tabs", "automation-toolbar", "justify-between", "pt-1")
        missing = [f"web:{marker}" for marker in required if marker not in web_page]
        missing.extend(f"android:{marker}" for marker in ("automation-tabs", "automation-toolbar", "pt-1") if marker not in android_page)
        return result(scenario, missing)
    if name == "execution_list_scroll":
        page = (ROOT / "frontend" / "src" / "views" / "ExecutionsPage.vue").read_text(encoding="utf-8")
        required = ("execution-page", "execution-list-panel", "execution-table", "tableScrollY", "ResizeObserver", "overflow: hidden")
        return result(scenario, [marker for marker in required if marker not in page])

    if name == "automation_detail_list_scroll":
        android_page = (ROOT / "frontend" / "src" / "views" / "AndroidAutomationPage.vue").read_text(encoding="utf-8")
        web_page = (ROOT / "frontend" / "src" / "views" / "WebAutomationPage.vue").read_text(encoding="utf-8")
        required = ("execution-detail-drawer", "execution-detail-content", "execution-detail-steps-panel", "min-height: 0", "overflow: 'hidden'", "y: '100%'")
        missing = [f"android:{marker}" for marker in required if marker not in android_page]
        missing.extend(f"web:{marker}" for marker in required if marker not in web_page)
        return result(scenario, missing)

    if name == "icon_alignment":
        styles = (ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")
        required = (
            ".anticon { display: inline-flex;",
            "align-items: center",
            ".anticon > svg { display: block; }",
            ".ant-avatar { display: inline-flex;",
        )
        return result(scenario, [marker for marker in required if marker not in styles])
    if name == "legacy_deep_link":
        response = session.get(f"{BASE_URL}/projects/?project_id=1", timeout=10)
        response.raise_for_status()
        missing = []
        if urlparse(response.url).path != "/app/projects":
            missing.append("legacy_redirect")
        if "project_id=1" not in response.url:
            missing.append("query_preservation")
        return result(scenario, missing)
    if name in {"global_search_contract", "global_search_empty"}:
        shell = (ROOT / "frontend" / "src" / "components" / "AppShell.vue").read_text(encoding="utf-8")
        required = (
            "searchOpen",
            "searchResults",
            "handleKeyboardSearch",
            "event.key.toLowerCase() === 'k'",
            "a-empty",
        )
        return result(scenario, [marker for marker in required if marker not in shell])
    if name == "auth_login_layout":
        page = (ROOT / "frontend" / "src" / "views" / "AuthPage.vue").read_text(encoding="utf-8")
        required = ("auth-grid", "brand-mark", "login-sheet", "sheet-content", "账号权限由平台统一管理", "@submit.prevent=\"login\"")
        return result(scenario, [marker for marker in required if marker not in page])
    if name == "auth_forbidden":
        response = session.get(f"{BASE_URL}/forbidden", timeout=10)
        response.raise_for_status()
        missing = []
        if urlparse(response.url).path != "/app/forbidden":
            missing.append("forbidden_redirect")
        if '<div id="app"></div>' not in response.text:
            missing.append("spa_shell")
        return result(scenario, missing)
    if name == "auth_logout":
        response = session.post(f"{BASE_URL}/api/v1/session/logout", timeout=10)
        response.raise_for_status()
        login_page = session.get(f"{BASE_URL}/login", timeout=10)
        login_page.raise_for_status()
        missing = []
        if urlparse(login_page.url).path != "/app/login":
            missing.append("login_redirect")
        if '<div id="app"></div>' not in login_page.text:
            missing.append("spa_shell")
        return result(scenario, missing)
    return result(scenario, ["scenario_not_implemented"])


def main():
    session = requests.Session()
    login(session)
    results = [run_scenario(session, scenario) for scenario in BROWSER_SCENARIOS]
    overall = "PASS" if all(item["status"] == "PASS" for item in results) else "FAIL"
    print(json.dumps({"gate": "browser", "overall": overall, "results": results}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if overall == "PASS" else 1)


if __name__ == "__main__":
    main()
