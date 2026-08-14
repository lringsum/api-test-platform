from dataclasses import dataclass


@dataclass(frozen=True)
class PageSpec:
    name: str
    module: str
    legacy_path: str
    spa_path: str


# The UI is served by the Vue application.  Each legacy path is retained only
# as a GET redirect so bookmarks can be moved without rendering Jinja pages.
PAGE_REGISTRY = [
    PageSpec("dashboard", "dashboard", "/", "/app/"),
    PageSpec("projects", "project", "/projects/", "/app/projects"),
    PageSpec("modules", "module", "/modules/", "/app/modules"),
    PageSpec("environments", "environment", "/environments/", "/app/environments"),
    PageSpec("variables", "variable", "/variables/", "/app/variables"),
    PageSpec("testcases", "testcase", "/testcases/", "/app/testcases"),
    PageSpec("scenarios", "scenario", "/scenarios/", "/app/scenarios"),
    PageSpec("executions", "execution", "/executions/records", "/app/executions"),
    PageSpec("reports", "report", "/reports/", "/app/executions"),
    PageSpec("security", "security", "/admin/users", "/app/security"),
    PageSpec("web_automation", "web-automation", "/ui-automation/scripts", "/app/web-automation"),
    PageSpec("android_automation", "android-automation", "/android-ui-automation/flows", "/app/android-automation"),
]


# Browser-facing checks intentionally cover Vue shell delivery, legacy-link
# redirects and API availability.  Full domain contracts are covered by
# API_SCENARIOS in the same registry.
BROWSER_SCENARIOS = [
    {"name": "vue_shell", "module": "spa", "kind": "smoke"},
    {"name": "navigation_hierarchy", "module": "shell", "kind": "smoke"},
    {"name": "ai_features_removed", "module": "shell", "kind": "anomaly"},
    {"name": "android_screenshot_preview", "module": "android-automation", "kind": "smoke"},
    {"name": "web_replay_drawer", "module": "web-automation", "kind": "smoke"},
    {"name": "web_locator_page_filter", "module": "web-automation", "kind": "smoke"},
    {"name": "web_locator_filter_safety", "module": "web-automation", "kind": "anomaly"},
    {"name": "automation_live_progress", "module": "automation", "kind": "smoke"},
    {"name": "automation_toolbar_layout", "module": "automation", "kind": "smoke"},
    {"name": "execution_list_scroll", "module": "execution", "kind": "smoke"},
    {"name": "automation_detail_list_scroll", "module": "automation", "kind": "smoke"},
    {"name": "icon_alignment", "module": "shell", "kind": "smoke"},
    {"name": "legacy_deep_link", "module": "spa", "kind": "smoke"},
    {"name": "global_search_contract", "module": "shell", "kind": "smoke"},
    {"name": "global_search_empty", "module": "shell", "kind": "anomaly"},
    {"name": "auth_login_layout", "module": "auth", "kind": "smoke"},
    {"name": "auth_forbidden", "module": "auth", "kind": "smoke"},
    {"name": "auth_logout", "module": "auth", "kind": "smoke"},
]


API_SCENARIOS = [
    {"name": "dashboard", "module": "dashboard", "method": "GET", "path": "/api/v1/dashboard"},
    {"name": "projects", "module": "resource", "method": "GET", "path": "/api/v1/projects"},
    {"name": "modules", "module": "resource", "method": "GET", "path": "/api/v1/modules"},
    {"name": "environments", "module": "resource", "method": "GET", "path": "/api/v1/environments"},
    {"name": "variables", "module": "resource", "method": "GET", "path": "/api/v1/variables"},
    {"name": "testcases", "module": "resource", "method": "GET", "path": "/api/v1/testcases"},
    {"name": "scenarios", "module": "scenario", "method": "GET", "path": "/api/v1/scenarios"},
    {"name": "execution_options", "module": "execution", "method": "GET", "path": "/api/v1/execution-options"},
    {"name": "executions", "module": "execution", "method": "GET", "path": "/api/v1/executions"},
    {"name": "security_options", "module": "security", "method": "GET", "path": "/api/v1/security/options"},
    {"name": "web_automation_overview", "module": "web-automation", "method": "GET", "path": "/api/v1/ui-automation/overview"},
    {"name": "android_automation_overview", "module": "android-automation", "method": "GET", "path": "/api/v1/android-automation/overview"},
]
