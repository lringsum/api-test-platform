from types import SimpleNamespace
from xml.etree import ElementTree

from app.services.android_ui_automation_service import AndroidUiAutomationService
from app.services.android_ui_automation_worker import AndroidUiAutomationWorker
from app.services.base_service import ServiceError


def test_flow_preset_contains_xianyu_sdk_login_steps():
    preset = AndroidUiAutomationService.get_flow_preset("xianyu_leyuan_account_login")

    assert preset["name"] == "仙遇-乐享元游 SDK 账号登录"
    assert [step["step_name"] for step in preset["steps"][:5]] == [
        "等待启动协议弹窗",
        "点击启动协议同意",
        "检测已登录状态并进入 SDK",
        "校验手机号登录页元素",
        "点击账号登录入口",
    ]
    assert preset["steps"][0]["selector_type"] == "image"
    assert preset["steps"][1]["selector_type"] == "image"
    assert preset["steps"][3]["selector_type"] == "image"
    assert preset["steps"][4]["selector_type"] == "image"
    assert any(step["step_type"] == "input_text" and step["selector_type"] == "image" for step in preset["steps"])
    assert any(step["step_name"] == "等待进入游戏界面" for step in preset["steps"])
    assert preset["steps"][-1]["step_type"] == "screenshot"


def test_flow_configuration_exposes_visual_step_types():
    assert "tap_image" in AndroidUiAutomationService.flow_step_type_options()
    assert "wait_image" in AndroidUiAutomationService.flow_step_type_options()
    assert "assert_image_exists" in AndroidUiAutomationService.flow_step_type_options()
    assert "assert_image_not_exists" in AndroidUiAutomationService.flow_step_type_options()
    assert "image" in AndroidUiAutomationService.flow_selector_type_options()


def test_flow_presets_cover_xianyu_sdk_interaction_scenarios():
    presets = AndroidUiAutomationService.flow_presets()
    preset_map = {item["key"]: item for item in presets}

    assert {
        "xianyu_leyuan_account_management_page",
        "xianyu_leyuan_change_password_page",
        "xianyu_leyuan_cancel_authorization_dialog",
        "xianyu_leyuan_account_cancellation_page",
        "xianyu_leyuan_phone_bound_page",
        "xianyu_leyuan_real_name_info_page",
        "xianyu_leyuan_third_party_sdk_directory_page",
        "xianyu_leyuan_in_game_sdk_floating_panel",
        "xianyu_leyuan_sdk_login_standard_template",
        "xianyu_leyuan_sdk_surface_audit",
        "xianyu_leyuan_switch_account_login",
        "xianyu_leyuan_account_login",
        "xianyu_leyuan_forgot_password_entry",
        "xianyu_leyuan_protocol_required_guard",
        "xianyu_leyuan_invalid_input_guard",
    }.issubset(set(preset_map))

    assert any(step["selector_value"] == "忘记密码" for step in preset_map["xianyu_leyuan_forgot_password_entry"]["steps"])
    assert any(step["step_type"] == "tap_left_of_text" for step in preset_map["xianyu_leyuan_protocol_required_guard"]["steps"]) is False
    assert any(step.get("input_value") == "zsr005!@#" for step in preset_map["xianyu_leyuan_invalid_input_guard"]["steps"])
    assert any(step.get("input_value") == "12" for step in preset_map["xianyu_leyuan_invalid_input_guard"]["steps"])


def test_flow_preset_exposes_sdk_ui_elements():
    preset = AndroidUiAutomationService.get_flow_preset("xianyu_leyuan_account_login")
    resource_ids = {item["resource_id"] for item in preset["ui_elements"] if item.get("resource_id")}
    labels = {item["label"] for item in preset["ui_elements"]}

    assert "com.xianyui.qs.cn:id/btn_confirm" in resource_ids
    assert "com.xianyui.qs.cn:id/qs_base_btn_cancel" in resource_ids
    assert "com.xianyui.qs.cn:id/tv_single_account_login" in resource_ids
    assert "com.xianyui.qs.cn:id/tv_single_fofget_pwd" in resource_ids
    assert "com.xianyui.qs.cn:id/cb_register" in resource_ids
    assert "账号密码登录切换" in labels
    assert "登录游戏" in labels
    assert "关闭弹窗" in labels


def test_standard_sdk_login_template_sections_and_steps():
    preset = AndroidUiAutomationService.get_flow_preset("xianyu_leyuan_sdk_login_standard_template")

    assert len(preset["template_sections"]) == 4
    assert preset["template_sections"][0]["title"] == "启动协议确认"
    assert preset["template_sections"][2]["goal"] == "输入账号密码并进入游戏主界面。"
    assert any(step["step_name"] == "勾选登录协议圆圈" for step in preset["steps"])
    assert any(step.get("input_value") == "zsr005!@#" for step in preset["steps"])
    assert any(step.get("input_value") == "12" for step in preset["steps"])
    assert any(step["step_type"] == "tap_left_of_text" for step in preset["steps"])


def test_in_game_sdk_floating_panel_preset_contains_user_center_controls():
    preset = AndroidUiAutomationService.get_flow_preset("xianyu_leyuan_in_game_sdk_floating_panel")
    labels = {item["label"] for item in preset["ui_elements"]}

    assert preset["name"] == "仙遇-游戏内 SDK 悬浮窗面板"
    assert len(preset["template_sections"]) == 5
    assert "悬浮窗入口" in labels
    assert "切换账号" in labels
    assert "账号管理" in labels
    assert "客服" in labels
    assert "用户协议" in labels
    assert "隐私政策" in labels
    assert "订单列表" in labels
    assert "加速" in labels
    assert any(step["step_name"] == "点击切换账号" for step in preset["steps"])
    assert any(step["step_name"] == "校验切换账号弹窗出现" for step in preset["steps"])
    assert any(step["step_name"] == "点击账号管理" for step in preset["steps"])
    assert any(step["step_name"] == "校验账号管理页出现" for step in preset["steps"])
    assert any(step["step_name"] == "点击客服" for step in preset["steps"])
    assert any(step["step_name"] == "校验客服弹窗出现" for step in preset["steps"])
    assert any(step["step_name"] == "点击订单列表" for step in preset["steps"])
    assert any(step["step_name"] == "校验订单列表页出现" for step in preset["steps"])
    assert any(step["step_name"] == "点击加速" for step in preset["steps"])
    assert any(step["step_name"] == "校验加速页出现" for step in preset["steps"])
    assert any(step["step_name"] == "校验协议页出现" for step in preset["steps"])
    assert any(step["step_name"] == "校验隐私页出现" for step in preset["steps"])
    assert any(step["step_name"] == "点击关闭弹窗" for step in preset["steps"])


def test_in_game_sdk_floating_panel_uses_image_templates_for_entry_and_close():
    preset = AndroidUiAutomationService.get_flow_preset("xianyu_leyuan_in_game_sdk_floating_panel")
    image_steps = [step for step in preset["steps"] if step["step_type"] == "tap_image"]
    user_center_steps = [
        step
        for step in preset["steps"]
        if step["step_type"] == "open_xianyu_user_center"
    ]

    assert any(
        step["selector_value"].endswith("xianyu_user_center_title.png")
        and step.get("retry_times") == 2
        for step in user_center_steps
    )
    assert any(step["selector_value"].endswith("xianyu_user_center_close.png") for step in image_steps)


def test_account_management_page_preset_contains_elements_and_branches():
    preset = AndroidUiAutomationService.get_flow_preset("xianyu_leyuan_account_management_page")
    labels = {item["label"] for item in preset["ui_elements"]}

    assert preset["name"] == "仙遇-用户中心账号管理页"
    assert len(preset["template_sections"]) == 4
    assert "页面标题" in labels
    assert "刷新" in labels
    assert "关闭" in labels
    assert "修改密码" in labels
    assert "取消授权" in labels
    assert "账号注销" in labels
    assert "手机号" in labels
    assert "实名信息" in labels
    assert "第三方SDK目录" in labels
    assert any(step["step_name"] == "点击修改密码" for step in preset["steps"])
    assert any(step["step_name"] == "校验修改密码页出现" for step in preset["steps"])
    assert any(step["step_name"] == "点击取消授权" for step in preset["steps"])
    assert any(step["step_name"] == "校验取消授权页出现" for step in preset["steps"])
    assert any(step["step_name"] == "点击账号注销" for step in preset["steps"])
    assert any(step["step_name"] == "校验账号注销确认页出现" for step in preset["steps"])
    assert any(step["step_name"] == "点击手机号" for step in preset["steps"])
    assert any(step["step_name"] == "校验手机号详情页出现" for step in preset["steps"])
    assert any(step["step_name"] == "点击实名信息" for step in preset["steps"])
    assert any(step["step_name"] == "校验实名信息页出现" for step in preset["steps"])
    assert any(step["step_name"] == "点击第三方SDK目录" for step in preset["steps"])
    assert any(step["step_name"] == "校验目录页出现" for step in preset["steps"])
    assert any(step["step_name"] == "点击刷新" for step in preset["steps"])
    assert any(step["step_name"] == "点击关闭" for step in preset["steps"])


def test_account_management_detail_presets_cover_actual_entry_pages():
    change_password = AndroidUiAutomationService.get_flow_preset("xianyu_leyuan_change_password_page")
    cancel_authorization = AndroidUiAutomationService.get_flow_preset("xianyu_leyuan_cancel_authorization_dialog")
    account_cancellation = AndroidUiAutomationService.get_flow_preset("xianyu_leyuan_account_cancellation_page")
    phone_bound = AndroidUiAutomationService.get_flow_preset("xianyu_leyuan_phone_bound_page")
    real_name = AndroidUiAutomationService.get_flow_preset("xianyu_leyuan_real_name_info_page")
    sdk_directory = AndroidUiAutomationService.get_flow_preset("xianyu_leyuan_third_party_sdk_directory_page")

    change_labels = {item["label"] for item in change_password["ui_elements"]}
    cancel_labels = {item["label"] for item in cancel_authorization["ui_elements"]}
    cancel_account_labels = {item["label"] for item in account_cancellation["ui_elements"]}
    phone_labels = {item["label"] for item in phone_bound["ui_elements"]}
    real_name_labels = {item["label"] for item in real_name["ui_elements"]}
    sdk_labels = {item["label"] for item in sdk_directory["ui_elements"]}

    assert change_password["name"] == "仙遇-账号管理-修改密码页"
    assert "短信验证码输入框" in change_labels
    assert "新密码输入框" in change_labels
    assert "确认新密码输入框" in change_labels
    assert "完成" in change_labels
    assert any(step["step_name"] == "校验短信验证码输入框" for step in change_password["steps"])
    assert any(step["step_name"] == "校验完成按钮" for step in change_password["steps"])

    assert cancel_authorization["name"] == "仙遇-账号管理-取消授权弹窗"
    assert "页面标题" in cancel_labels
    assert "协议勾选框" in cancel_labels
    assert "确认" in cancel_labels
    assert any(step["step_name"] == "勾选协议" for step in cancel_authorization["steps"])
    assert any(step["step_name"] == "校验确认按钮可点击" for step in cancel_authorization["steps"])

    assert account_cancellation["name"] == "仙遇-账号管理-账号注销页"
    assert "协议勾选框" in cancel_account_labels
    assert "确认" in cancel_account_labels
    assert any(step["step_name"] == "校验账号注销页出现" for step in account_cancellation["steps"])
    assert any(step["step_name"] == "校验确认按钮可点击" for step in account_cancellation["steps"])

    assert phone_bound["name"] == "仙遇-账号管理-手机号已绑定页"
    assert "页面标题" in phone_labels
    assert "更换手机号码" in phone_labels
    assert any(step["step_name"] == "校验更换手机号码按钮" for step in phone_bound["steps"])

    assert real_name["name"] == "仙遇-账号管理-实名信息页"
    assert "页面标题" in real_name_labels
    assert "实名状态提示" in real_name_labels
    assert "联系客服中心" in real_name_labels
    assert any(step["step_name"] == "校验实名状态提示" for step in real_name["steps"])
    assert any(step["step_name"] == "校验联系客服中心入口" for step in real_name["steps"])

    assert sdk_directory["name"] == "仙遇-账号管理-第三方SDK目录页"
    assert "页面标题" in sdk_labels
    assert "广点通SDK" in sdk_labels
    assert "QuickSDK" in sdk_labels
    assert "确认" in sdk_labels
    assert any(step["step_name"] == "校验目录页SDK列表" for step in sdk_directory["steps"])
    assert any(step["step_name"] == "校验确认按钮" for step in sdk_directory["steps"])


def test_account_management_page_close_uses_image_template():
    preset = AndroidUiAutomationService.get_flow_preset("xianyu_leyuan_account_management_page")
    image_steps = [step for step in preset["steps"] if step["step_type"] == "tap_image"]

    assert any(step["selector_value"].endswith("xianyu_user_center_close.png") for step in image_steps)


def test_execute_flow_step_supports_tap_left_of_text(monkeypatch, tmp_path):
    tapped_points = []
    fake_node = SimpleNamespace(attrib={"bounds": "[100,200][300,260]"})

    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_wait_for_selector",
        staticmethod(lambda *args, **kwargs: fake_node),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_tap_point",
        staticmethod(lambda adb_path, serial, x, y, log_lines: tapped_points.append((x, y)) or True),
    )

    result_payload, screenshot_path = AndroidUiAutomationWorker._execute_flow_step(
        adb_path="adb",
        serial="127.0.0.1:16384",
        workspace=tmp_path,
        log_lines=[],
        step=SimpleNamespace(step_no=1),
        snapshot_item={
            "step_type": "tap_left_of_text",
            "selector_type": "text",
            "selector_value": "我已详细阅读并同意",
            "input_value": "26",
            "wait_timeout_sec": 20,
            "capture_on_success": False,
        },
    )

    assert tapped_points == [(74, 230)]
    assert result_payload["tap_point"] == {"x": 74, "y": 230, "offset_left": 26}
    assert screenshot_path == ""


def test_execute_flow_step_taps_clickable_text_container_from_uiautomator_dump(monkeypatch, tmp_path):
    tapped_points = []
    xml_root = ElementTree.fromstring(
        """
        <hierarchy>
          <node class="android.view.View" clickable="false" bounds="[0,0][1080,1920]">
            <node class="android.view.View" clickable="true" bounds="[469,340][608,424]">
              <node class="android.widget.TextView" clickable="false" text="账号管理" bounds="[469,398][608,424]" />
            </node>
          </node>
        </hierarchy>
        """
    )

    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_uiautomator_dump",
        staticmethod(lambda *args, **kwargs: xml_root),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_tap_point",
        staticmethod(lambda adb_path, serial, x, y, log_lines: tapped_points.append((x, y)) or True),
    )

    result_payload, screenshot_path = AndroidUiAutomationWorker._execute_flow_step(
        adb_path="adb",
        serial="127.0.0.1:16384",
        workspace=tmp_path,
        log_lines=[],
        step=SimpleNamespace(step_no=1),
        snapshot_item={
            "step_type": "tap_text",
            "selector_type": "text",
            "selector_value": "账号管理",
            "wait_timeout_sec": 5,
            "capture_on_success": False,
        },
    )

    assert tapped_points == [(538, 382)]
    assert result_payload["tap_point"] == {"x": 538, "y": 382}
    assert screenshot_path == ""


def test_send_keyevent_splits_multiple_key_values(monkeypatch):
    calls = []

    def fake_adb_shell(adb_path, serial, shell_args, timeout, log_lines):
        calls.append(shell_args)

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(AndroidUiAutomationWorker, "_adb_shell", staticmethod(fake_adb_shell))

    AndroidUiAutomationWorker._send_keyevent(
        "adb",
        "device",
        "123 67,67 67",
        [],
    )

    assert calls == [["input", "keyevent", "123", "67", "67", "67"]]


def test_execute_flow_step_supports_ocr_text_fallback(monkeypatch, tmp_path):
    clicked = []

    class FakeOcrNode:
        rect = {"x": 100, "y": 200, "width": 120, "height": 40}

        def click(self):
            clicked.append("clicked")

    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_uiautomator_dump",
        staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(ServiceError("no xml"))),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_find_ocr_node",
        staticmethod(lambda driver, selector_value: FakeOcrNode()),
    )

    result_payload, screenshot_path = AndroidUiAutomationWorker._execute_flow_step(
        adb_path="adb",
        serial="127.0.0.1:16384",
        workspace=tmp_path,
        log_lines=[],
        step=SimpleNamespace(step_no=1),
        snapshot_item={
            "step_type": "tap_text",
            "selector_type": "text",
            "selector_value": "同意",
            "wait_timeout_sec": 5,
            "capture_on_success": False,
        },
        visual_driver=object(),
    )

    assert clicked == ["clicked"]
    assert result_payload["tap_mode"] == "visual"
    assert screenshot_path == ""


def test_execute_flow_step_supports_tap_image(monkeypatch, tmp_path):
    tapped_points = []

    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_wait_for_image",
        staticmethod(lambda *args, **kwargs: {"center": {"x": 222, "y": 333}, "score": 0.9}),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_tap_point",
        staticmethod(lambda adb_path, serial, x, y, log_lines: tapped_points.append((x, y)) or True),
    )

    result_payload, screenshot_path = AndroidUiAutomationWorker._execute_flow_step(
        adb_path="adb",
        serial="127.0.0.1:16384",
        workspace=tmp_path,
        log_lines=[],
        step=SimpleNamespace(step_no=1),
        snapshot_item={
            "step_type": "tap_image",
            "selector_value": "xianyu/xianyu_floating_entry.png",
            "wait_timeout_sec": 5,
            "capture_on_success": False,
        },
        visual_driver=object(),
    )

    assert tapped_points == [(222, 333)]
    assert result_payload["tap_mode"] == "image"
    assert result_payload["tap_point"] == {"x": 222, "y": 333}
    assert screenshot_path == ""


def test_execute_flow_step_taps_agreement_circle_not_label(monkeypatch, tmp_path):
    tapped_points = []
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_wait_for_image",
        staticmethod(lambda *args, **kwargs: {
            "center": {"x": 769, "y": 769},
            "rect": {"x": 629, "y": 750, "width": 280, "height": 38},
            "score": 0.9,
        }),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_tap_point",
        staticmethod(lambda adb_path, serial, x, y, log_lines: tapped_points.append((x, y)) or True),
    )

    result_payload, _ = AndroidUiAutomationWorker._execute_flow_step(
        adb_path="adb",
        serial="127.0.0.1:16384",
        workspace=tmp_path,
        log_lines=[],
        step=SimpleNamespace(step_no=11),
        snapshot_item={
            "step_type": "tap_image",
            "selector_value": "xianyu/sdk_agreement_checkbox.png",
            "wait_timeout_sec": 5,
            "capture_on_success": False,
        },
    )

    assert tapped_points == [(689, 769)]
    assert result_payload["tap_point"] == {"x": 689, "y": 769}


def test_execute_flow_step_detects_delayed_phone_login_page(monkeypatch, tmp_path):
    calls = []

    def wait_for_any_image(adb_path, serial, selector_values, timeout, log_lines, run_id=None):
        calls.append(tuple(selector_values))
        if "xianyu/sdk_login_button.png" in selector_values:
            return "xianyu/sdk_login_button.png", {"center": {"x": 1, "y": 1}, "score": 0.9}
        raise ServiceError("not visible")

    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_wait_for_any_image",
        staticmethod(wait_for_any_image),
    )

    result_payload, screenshot_path = AndroidUiAutomationWorker._execute_flow_step(
        adb_path="adb",
        serial="127.0.0.1:16384",
        workspace=tmp_path,
        log_lines=[],
        step=SimpleNamespace(step_no=3),
        snapshot_item={
            "step_type": "ensure_xianyu_account_login",
            "wait_timeout_sec": 5,
            "capture_on_success": False,
        },
    )

    assert result_payload["branch"] == "sdk_phone_login_visible"
    assert calls
    assert "xianyu/sdk_login_button.png" in calls[0]
    assert "xianyu/sdk_login_button_candidate2.png" in calls[0]
    assert screenshot_path == ""


def test_execute_flow_step_handles_auto_login_floating_branch(monkeypatch, tmp_path):
    tapped_points = []
    calls = []

    def wait_for_any_image(adb_path, serial, selector_values, timeout, log_lines, run_id=None):
        calls.append(tuple(selector_values))
        if "xianyu/xianyu_floating_entry.png" in selector_values:
            return "xianyu/floating_candidate_2.png", {"center": {"x": 88, "y": 666}, "score": 0.92}
        if "xianyu/sdk_switch_account.png" in selector_values:
            return "xianyu/sdk_switch_account.png", {"center": {"x": 777, "y": 444}, "score": 0.91}
        raise ServiceError("not visible")

    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_wait_for_any_image",
        staticmethod(wait_for_any_image),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_tap_point",
        staticmethod(lambda adb_path, serial, x, y, log_lines: tapped_points.append((x, y)) or True),
    )

    result_payload, screenshot_path = AndroidUiAutomationWorker._execute_flow_step(
        adb_path="adb",
        serial="127.0.0.1:16384",
        workspace=tmp_path,
        log_lines=[],
        step=SimpleNamespace(step_no=3),
        snapshot_item={
            "step_type": "ensure_xianyu_account_login",
            "wait_timeout_sec": 5,
            "capture_on_success": False,
        },
    )

    assert result_payload["branch"] == "floating_user_center_switch_account"
    assert result_payload["entry_point"] == {"x": 88, "y": 666}
    assert tapped_points == [(88, 666), (777, 444)]
    assert screenshot_path == ""


def test_execute_flow_step_prefers_switch_account_text_in_user_center(monkeypatch, tmp_path):
    tapped_points = []

    def wait_for_any_image(adb_path, serial, selector_values, timeout, log_lines, run_id=None):
        if "xianyu/xianyu_floating_entry.png" in selector_values:
            return "xianyu/xianyu_floating_entry.png", {"center": {"x": 91, "y": 501}, "score": 0.92}
        raise ServiceError("not visible")

    fake_node = SimpleNamespace(attrib={"bounds": "[1200,180][1500,290]"})

    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_wait_for_any_image",
        staticmethod(wait_for_any_image),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_wait_for_selector",
        staticmethod(lambda *args, **kwargs: fake_node),
    )
    monkeypatch.setattr(
        AndroidUiAutomationWorker,
        "_tap_point",
        staticmethod(lambda adb_path, serial, x, y, log_lines: tapped_points.append((x, y)) or True),
    )

    result_payload, screenshot_path = AndroidUiAutomationWorker._execute_flow_step(
        adb_path="adb",
        serial="127.0.0.1:16384",
        workspace=tmp_path,
        log_lines=[],
        step=SimpleNamespace(step_no=3),
        snapshot_item={
            "step_type": "ensure_xianyu_account_login",
            "wait_timeout_sec": 5,
            "capture_on_success": False,
        },
    )

    assert result_payload["branch"] == "floating_user_center_switch_account_text"
    assert result_payload["entry_point"] == {"x": 91, "y": 501}
    assert tapped_points == [(91, 501), (1350, 235)]
    assert screenshot_path == ""


def test_flow_mode_normalization_and_label_support_two_user_facing_modes():
    assert AndroidUiAutomationService.normalize_flow_mode("basic") == "basic"
    assert AndroidUiAutomationService.normalize_flow_mode("full") == "full"
    assert AndroidUiAutomationService.normalize_flow_mode("default") == "full"
    assert AndroidUiAutomationService.normalize_flow_mode("specified") == "full"
    assert AndroidUiAutomationService.flow_mode_label("basic") == "仅基础装包验证"
    assert AndroidUiAutomationService.flow_mode_label("full") == "安装包+SDK全功能验证"
    assert AndroidUiAutomationService.flow_mode_label("default") == "安装包+SDK全功能验证"
    assert AndroidUiAutomationService.flow_mode_label("specified") == "安装包+SDK全功能验证"


def test_full_flow_mode_uses_selected_template_or_project_default(monkeypatch):
    selected_flow = SimpleNamespace(id=21, name="专用流程")
    default_flow = SimpleNamespace(id=22, name="默认流程")

    monkeypatch.setattr(
        AndroidUiAutomationService,
        "get_project_flow",
        staticmethod(lambda flow_id: selected_flow if flow_id == 21 else None),
    )
    monkeypatch.setattr(
        AndroidUiAutomationService,
        "get_default_project_flow",
        staticmethod(lambda project_id: default_flow if project_id == 9 else None),
    )

    specified_task = SimpleNamespace(flow_mode="full", flow_id=21, project_id=9)
    default_task = SimpleNamespace(flow_mode="full", flow_id=None, project_id=9)
    legacy_specified_task = SimpleNamespace(flow_mode="specified", flow_id=21, project_id=9)
    legacy_default_task = SimpleNamespace(flow_mode="default", flow_id=None, project_id=9)

    assert AndroidUiAutomationService.resolve_task_flow(specified_task) is selected_flow
    assert AndroidUiAutomationService.resolve_task_flow(default_task) is default_flow
    assert AndroidUiAutomationService.resolve_task_flow(legacy_specified_task) is selected_flow
    assert AndroidUiAutomationService.resolve_task_flow(legacy_default_task) is default_flow


def test_full_flow_mode_binding_accepts_optional_template(monkeypatch):
    selected_flow = SimpleNamespace(id=31, project_id=5)

    monkeypatch.setattr(
        AndroidUiAutomationService,
        "get_project_flow",
        staticmethod(lambda flow_id: selected_flow if flow_id == 31 else None),
    )

    assert AndroidUiAutomationService.resolve_task_flow_binding(
        project_id=5,
        flow_mode="full",
        flow_id=None,
    ) == ("full", None, False)
    assert AndroidUiAutomationService.resolve_task_flow_binding(
        project_id=5,
        flow_mode="full",
        flow_id=31,
    ) == ("full", 31, True)
