from app.services.ui_automation_service import UiAutomationService


def test_change_summary_guard_detects_garbled_text():
    assert UiAutomationService.is_suspect_change_summary("???? selector ????????????")
    assert UiAutomationService.is_suspect_change_summary("说明含有�替换字符")
    assert UiAutomationService.is_suspect_change_summary("锟斤拷锟斤拷")


def test_change_summary_guard_preserves_normal_text():
    assert not UiAutomationService.is_suspect_change_summary("新增登录断言")
    assert UiAutomationService.sanitize_change_summary("新增登录断言") == "新增登录断言"


def test_change_summary_guard_falls_back_for_bad_text():
    assert UiAutomationService.sanitize_change_summary("????") == UiAutomationService.CHANGE_SUMMARY_FALLBACK
    assert (
        UiAutomationService.display_change_summary("????")
        == UiAutomationService.CHANGE_SUMMARY_GARBLED_FALLBACK
    )
