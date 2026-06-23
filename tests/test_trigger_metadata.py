from app.models import TriggerInfoMixin
from app.utils.trigger import normalize_trigger_type


class _User:
    username = "zhangsenrong"
    display_name = "张森荣"


class _Run(TriggerInfoMixin):
    def __init__(self, trigger_type, trigger_user=None):
        self.trigger_type = trigger_type
        self.trigger_user = trigger_user


def test_trigger_type_is_normalized_to_two_values():
    assert normalize_trigger_type("manual") == "manual"
    assert normalize_trigger_type("scheduled") == "automatic"
    assert normalize_trigger_type("ai_repair") == "automatic"
    assert normalize_trigger_type(None) == "automatic"


def test_manual_trigger_displays_current_user():
    run = _Run("manual", _User())

    assert run.trigger_type_label == "手动触发"
    assert run.trigger_person_name == "张森荣"


def test_automatic_trigger_without_user_displays_system():
    run = _Run("automatic")

    assert run.trigger_type_label == "自动触发"
    assert run.trigger_person_name == "系统"


def test_legacy_manual_trigger_without_user_displays_dash():
    run = _Run("manual")

    assert run.trigger_person_name == "-"
