from dataclasses import dataclass, field


@dataclass(frozen=True)
class PageSpec:
    name: str
    module: str
    path: str
    page_title: str
    ready_markers: tuple[str, ...] = field(default_factory=tuple)
    anomaly_path: str | None = None


PAGE_REGISTRY = [
    PageSpec(
        name="dashboard",
        module="dashboard",
        path="/",
        page_title="Dashboard",
        ready_markers=("项目数量",),
    ),
    PageSpec(
        name="projects",
        module="project",
        path="/projects/",
        page_title="项目管理",
        ready_markers=("查询条件",),
    ),
    PageSpec(
        name="modules",
        module="module",
        path="/modules/",
        page_title="模块管理",
        ready_markers=("模块管理",),
    ),
    PageSpec(
        name="environments",
        module="environment",
        path="/environments/",
        page_title="环境管理",
        ready_markers=("环境管理",),
    ),
    PageSpec(
        name="variables",
        module="variable",
        path="/variables/",
        page_title="变量管理",
        ready_markers=("变量管理",),
    ),
    PageSpec(
        name="testcases",
        module="testcase",
        path="/testcases/",
        page_title="用例管理",
        ready_markers=("查询条件",),
    ),
    PageSpec(
        name="scenarios",
        module="scenario",
        path="/scenarios/",
        page_title="场景管理",
        ready_markers=("查询条件",),
    ),
    PageSpec(
        name="ai-parser",
        module="ai",
        path="/ai/parser",
        page_title="AI 接口解析",
        ready_markers=("解析结果输出",),
    ),
    PageSpec(
        name="execution-run",
        module="execution",
        path="/executions/run",
        page_title="接口执行",
        ready_markers=("执行配置", "执行返回"),
    ),
    PageSpec(
        name="execution-history",
        module="execution",
        path="/executions/history",
        page_title="执行历史",
        ready_markers=("执行记录",),
    ),
    PageSpec(
        name="ui-scripts",
        module="ui-automation",
        path="/ui-automation/scripts",
        page_title="UI 脚本管理",
        ready_markers=("aiScriptDrawer", "scriptDetailDrawer"),
    ),
    PageSpec(
        name="ui-locators",
        module="ui-automation",
        path="/ui-automation/locators",
        page_title="UI 定位器库",
        ready_markers=("筛选条件", "定位器列表", "定位器管理洞察"),
    ),
    PageSpec(
        name="ui-executions",
        module="ui-automation",
        path="/ui-automation/executions",
        page_title="UI 执行计划",
        ready_markers=("执行配置", "Playwright Worker 已接入"),
    ),
    PageSpec(
        name="ui-replays",
        module="ui-automation",
        path="/ui-automation/replays",
        page_title="UI 报告回放",
        ready_markers=("uiReplayPage", "replayFilterForm"),
    ),
    PageSpec(
        name="reports",
        module="report",
        path="/reports/",
        page_title="测试报告",
        ready_markers=("查询条件",),
    ),
    PageSpec(
        name="prompts",
        module="prompt",
        path="/prompts/",
        page_title="Prompt 模板管理",
        ready_markers=("模板列表",),
    ),
]


BROWSER_SCENARIOS = [
    {
        "name": "execution_smoke",
        "module": "execution",
        "kind": "smoke",
        "project_id": 3,
        "expected_environment_name": "预发布环境",
        "expected_module_name": "初始化模块",
        "expected_testcase_keyword": "init",
        "expect_checklist": True,
    },
    {
        "name": "execution_anomaly_empty",
        "module": "execution",
        "kind": "anomaly",
        "project_id": 999999,
        "expected_empty": True,
    },
    {
        "name": "execution_report_smoke",
        "module": "execution",
        "kind": "smoke",
    },
    {
        "name": "ui_locator_smoke",
        "module": "ui-automation",
        "kind": "smoke",
        "project_id": 4,
        "other_project_id": 3,
    },
    {
        "name": "ui_worker_smoke",
        "module": "ui-automation",
        "kind": "smoke",
        "project_id": 4,
    },
    {
        "name": "ui_script_ai_generate_smoke",
        "module": "ui-automation",
        "kind": "smoke",
        "project_id": 4,
    },
    {
        "name": "ui_script_version_history_smoke",
        "module": "ui-automation",
        "kind": "smoke",
        "project_id": 4,
    },
    {
        "name": "ui_replay_smoke",
        "module": "ui-automation",
        "kind": "smoke",
        "project_id": 4,
    },
    {
        "name": "ui_script_repair_smoke",
        "module": "ui-automation",
        "kind": "smoke",
        "project_id": 4,
    },
    {
        "name": "ui_script_batch_smoke",
        "module": "ui-automation",
        "kind": "smoke",
        "project_id": 4,
    },
    {
        "name": "ui_script_detail_smoke",
        "module": "ui-automation",
        "kind": "smoke",
        "project_id": 4,
    },
]


API_SCENARIOS = [
    {
        "name": "execution_options_smoke",
        "module": "execution",
        "method": "GET",
        "path": "/executions/api/run/options",
        "params": {"project_id": 3},
        "expect_success": True,
        "expect_non_empty_keys": ("environments", "modules", "testcases"),
    },
    {
        "name": "execution_options_anomaly_empty",
        "module": "execution",
        "method": "GET",
        "path": "/executions/api/run/options",
        "params": {"project_id": 999999},
        "expect_success": True,
        "expect_empty_keys": ("environments", "modules", "testcases"),
    },
    {
        "name": "validate_case_json_smoke",
        "module": "testcase",
        "method": "POST",
        "path": "/testcases/api/validate-json",
        "json": {
            "case_data": {
                "name": "API Gate Smoke",
                "method": "GET",
                "url": "/health",
                "headers": {},
                "params": {},
                "body": {},
                "extract": {},
                "assertions": [
                    {
                        "type": "status_code",
                        "expected": 200
                    }
                ]
            }
        },
        "expect_success": True,
    },
]
