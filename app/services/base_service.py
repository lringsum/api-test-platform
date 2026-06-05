import json
from copy import deepcopy

from sqlalchemy.exc import IntegrityError

from app import db


class ServiceError(Exception):
    """统一业务异常，供路由层和页面层捕获展示。"""


def commit_session():
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ServiceError("数据唯一性约束冲突，请检查是否存在重复数据。") from exc
    except Exception as exc:
        db.session.rollback()
        raise ServiceError(f"数据库操作失败：{exc}") from exc


def parse_json_text(json_text, field_name="JSON"):
    if json_text is None:
        raise ServiceError(f"{field_name} 不能为空。")

    if isinstance(json_text, (dict, list)):
        return json_text

    text = str(json_text).strip()
    if not text:
        raise ServiceError(f"{field_name} 不能为空。")

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ServiceError(f"{field_name} 格式错误：{exc.msg}") from exc


def ensure_not_blank(value, field_name):
    if value is None or str(value).strip() == "":
        raise ServiceError(f"{field_name} 不能为空。")
    return str(value).strip()


def ensure_choice(value, field_name, allowed_values):
    value = ensure_not_blank(value, field_name)
    if value not in allowed_values:
        raise ServiceError(
            f"{field_name} 非法，必须是：{', '.join(allowed_values)}。"
        )
    return value


def validate_case_schema(case_data):
    if not isinstance(case_data, dict):
        raise ServiceError("用例 JSON 必须是对象。")

    required_fields = [
        "name",
        "method",
        "url",
        "headers",
        "params",
        "body",
        "extract",
        "assertions",
    ]

    for field in required_fields:
        if field not in case_data:
            raise ServiceError(f"用例 JSON 缺少必要字段：{field}。")

    name = ensure_not_blank(case_data.get("name"), "用例名称")
    method = ensure_choice(case_data.get("method"), "请求方法", ["GET", "POST"])
    url = ensure_not_blank(case_data.get("url"), "请求路径")

    if not url.startswith("/"):
        raise ServiceError("请求路径必须以 / 开头。")

    for field in ["headers", "params", "body", "extract"]:
        if not isinstance(case_data.get(field), dict):
            raise ServiceError(f"字段 {field} 必须是对象。")

    files = case_data.get("files", {})
    if files is None:
        files = {}
    if not isinstance(files, dict):
        raise ServiceError("字段 files 必须是对象。")

    assertions = case_data.get("assertions")
    if not isinstance(assertions, list) or not assertions:
        raise ServiceError("assertions 必须是非空数组。")

    allowed_assert_types = ["status_code", "json_path", "contains", "response_time"]
    for index, item in enumerate(assertions, start=1):
        if not isinstance(item, dict):
            raise ServiceError(f"第 {index} 条断言必须是对象。")
        assert_type = item.get("type")
        if assert_type not in allowed_assert_types:
            raise ServiceError(
                f"第 {index} 条断言类型非法，必须是：{', '.join(allowed_assert_types)}。"
            )
        if "expected" not in item:
            raise ServiceError(f"第 {index} 条断言缺少 expected 字段。")
        if assert_type == "json_path" and not item.get("path"):
            raise ServiceError(f"第 {index} 条 json_path 断言缺少 path 字段。")

    pre_script = normalize_pre_script_config(case_data.get("pre_script"))

    body_type = str(case_data.get("body_type") or "json").strip().lower()
    if body_type not in ["json", "form", "multipart"]:
        raise ServiceError("body_type 非法，必须是 json、form 或 multipart。")

    if body_type == "multipart" and not files:
        raise ServiceError("body_type 为 multipart 时，files 不能为空。")

    return {
        "name": name,
        "method": method,
        "url": url,
        "headers": case_data["headers"],
        "params": case_data["params"],
        "body": case_data["body"],
        "files": files,
        "body_type": body_type,
        "extract": case_data["extract"],
        "assertions": assertions,
        "pre_script": pre_script,
    }


def normalize_pre_script_config(pre_script):
    default_config = {
        "enabled": False,
        "language": "python",
        "template_id": None,
        "content": "",
    }

    if pre_script is None:
        return deepcopy(default_config)

    if not isinstance(pre_script, dict):
        raise ServiceError("pre_script 必须是对象。")

    enabled = bool(pre_script.get("enabled", False))
    language = str(pre_script.get("language") or "python").strip().lower()
    if language != "python":
        raise ServiceError("pre_script.language 目前仅支持 python。")

    content = str(pre_script.get("content") or "").strip()
    template_id = pre_script.get("template_id")
    if template_id in ("", None):
        template_id = None

    if enabled and not content:
        raise ServiceError("启用前置脚本时，脚本内容不能为空。")

    return {
        "enabled": enabled,
        "language": language,
        "template_id": template_id,
        "content": content,
    }
