from app.services.ui_automation_service import UiAutomationService
import pytest


class _Step:
    def __init__(self, status="failed", step_title="", step_type="", locator="", error_message=""):
        self.status = status
        self.step_title = step_title
        self.step_type = step_type
        self.locator = locator
        self.error_message = error_message
        self.step_index = 54


class _Run:
    def __init__(self, status="failed", error_message="", steps=None):
        self.status = status
        self.error_message = error_message
        self.steps = steps or []


def test_failed_assertion_with_timeout_text_is_not_classified_as_run_timeout():
    run = _Run(
        status="failed",
        error_message=(
            'AssertionError: Locator expected to have attribute "true"\n'
            'Call log:\n'
            '  - Expect "to_have_attribute" with timeout 5000ms\n'
            '  - unexpected value "false"\n'
        ),
        steps=[
            _Step(
                status="failed",
                step_title="断言媒体渠道下拉框已展开",
                step_type="assert",
                locator="媒体渠道下拉框",
            )
        ],
    )

    result = UiAutomationService.analyze_run_failure(run)

    assert result["has_failure"] is True
    assert result["category"] == "assertion"
    assert result["step_index"] == 54


def test_run_timeout_status_still_uses_timeout_category():
    run = _Run(status="timeout", error_message="Playwright 脚本执行超时（300 秒）。")

    result = UiAutomationService.analyze_run_failure(run)

    assert result["has_failure"] is True
    assert result["category"] == "timeout"


@pytest.mark.parametrize(
    ("status", "expected_label"),
    [("queued", "排队中"), ("pending", "等待执行"), ("running", "执行中")],
)
def test_active_run_status_does_not_report_failure(status, expected_label):
    run = _Run(status=status)

    result = UiAutomationService.analyze_run_failure(run)

    assert result["has_failure"] is False
    assert result["category"] == status
    assert result["category_label"] == expected_label
    assert result["summary"] == ""


def test_missing_element_is_classified_before_assertion():
    run = _Run(
        status="failed",
        error_message="pytest summary containing several failures",
        steps=[
            _Step(
                status="failed",
                step_title="选择设计师",
                step_type="click",
                locator="设计师下拉框",
                error_message=(
                    "AssertionError: Locator expected to be visible\n"
                    "Actual value: None\n"
                    "Error: element(s) not found\n"
                    "waiting for locator(\"//input[@placeholder='请选择设计师']\")"
                ),
            )
        ],
    )

    result = UiAutomationService.analyze_run_failure(run)

    assert result["category"] == "locator_not_found"
    assert result["category_label"] == "元素定位不到"
    assert result["match_count"] == 0
    assert "选择设计师" in result["summary"]


def test_strict_mode_violation_reports_non_unique_match_count():
    step = _Step(
        status="failed",
        step_title="读取分页总数",
        step_type="assert",
        locator="分页总数",
        error_message=(
            "Error: strict mode violation: locator(\"//div[contains(@class,'el-pagination')]\") "
            "resolved to 2 elements"
        ),
    )

    result = UiAutomationService.analyze_step_failure(step)

    assert result["category"] == "locator_not_unique"
    assert result["category_label"] == "元素不唯一"
    assert result["match_count"] == 2
    assert "同时命中了 2 个元素" in result["root_cause"]
