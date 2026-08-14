import pytest

from app.services.base_service import ServiceError
from app.services.ui_automation_worker import UiAutomationWorker


def test_worker_finds_test_function_as_login_precondition_entrypoint():
    content = "def helper():\n    pass\n\ndef test_login(page, base_url):\n    pass\n"

    assert UiAutomationWorker._infer_precondition_entrypoint(content) == "test_login"


def test_worker_rejects_login_precondition_without_test_function():
    with pytest.raises(ServiceError, match="缺少可调用"):
        UiAutomationWorker._infer_precondition_entrypoint("def login(page):\n    pass\n")
