import base64
import hashlib
import json
import uuid
import urllib.parse
from copy import deepcopy
from time import time

from app.services.base_service import ServiceError, normalize_pre_script_config


class PreScriptService:
    _BLOCKED_KEYWORDS = [
        "__import__",
        "import ",
        "open(",
        "exec(",
        "eval(",
        "compile(",
        "os.",
        "sys.",
        "subprocess",
        "requests.",
        "globals(",
        "locals(",
        "input(",
    ]
    _SAFE_BUILTINS = {
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "len": len,
        "min": min,
        "max": max,
        "sum": sum,
        "sorted": sorted,
        "round": round,
        "abs": abs,
        "range": range,
        "list": list,
        "dict": dict,
        "set": set,
        "tuple": tuple,
        "enumerate": enumerate,
        "zip": zip,
        "isinstance": isinstance,
        "issubclass": issubclass,
        "hasattr": hasattr,
        "getattr": getattr,
        "setattr": setattr,
        "delattr": delattr,
        "print": print,
        "type": type,
        "Exception": Exception,
        "ValueError": ValueError,
        "TypeError": TypeError,
        "KeyError": KeyError,
    }

    @staticmethod
    def get_normalized_config(testcase_data):
        testcase_data = testcase_data or {}
        return normalize_pre_script_config(testcase_data.get("pre_script"))

    @staticmethod
    def prepare_context(
        env=None,
        project_vars=None,
        runtime_vars=None,
        headers=None,
        params=None,
        body=None,
    ):
        return {
            "env": deepcopy(env or {}),
            "project_vars": deepcopy(project_vars or {}),
            "runtime_vars": deepcopy(runtime_vars or {}),
            "headers": deepcopy(headers or {}),
            "params": deepcopy(params or {}),
            "body": deepcopy(body or {}),
        }

    @staticmethod
    def execute_script(script_config, context):
        config = normalize_pre_script_config(script_config)
        execution_context = PreScriptService.prepare_context(
            env=(context or {}).get("env"),
            project_vars=(context or {}).get("project_vars"),
            runtime_vars=(context or {}).get("runtime_vars"),
            headers=(context or {}).get("headers"),
            params=(context or {}).get("params"),
            body=(context or {}).get("body"),
        )

        if not config.get("enabled"):
            return execution_context

        script_content = config.get("content", "")
        PreScriptService._validate_script_content(script_content)

        globals_dict = {"__builtins__": PreScriptService._SAFE_BUILTINS}
        locals_dict = PreScriptService._build_locals(execution_context)

        try:
            exec(script_content, globals_dict, locals_dict)
        except Exception as exc:
            raise ServiceError(f"前置脚本执行失败：{exc}") from exc

        return {
            "env": deepcopy(execution_context["env"]),
            "project_vars": deepcopy(execution_context["project_vars"]),
            "runtime_vars": deepcopy(locals_dict["runtime_vars"]),
            "headers": deepcopy(locals_dict["headers"]),
            "params": deepcopy(locals_dict["params"]),
            "body": deepcopy(locals_dict["body"]),
        }

    @staticmethod
    def _validate_script_content(script_content):
        for keyword in PreScriptService._BLOCKED_KEYWORDS:
            if keyword in script_content:
                raise ServiceError(f"前置脚本包含不允许的内容：{keyword}")

    @staticmethod
    def _build_locals(execution_context):
        helper_functions = {
            "md5": PreScriptService.md5,
            "sha256": PreScriptService.sha256,
            "base64_encode": PreScriptService.base64_encode,
            "base64_decode": PreScriptService.base64_decode,
            "url_encode": PreScriptService.url_encode,
            "url_decode": PreScriptService.url_decode,
            "timestamp": PreScriptService.timestamp,
            "uuid4": PreScriptService.uuid4,
            "json_dumps": PreScriptService.json_dumps,
            "json_dumps_compact": PreScriptService.json_dumps_compact,
            "json_loads": PreScriptService.json_loads,
        }
        return {
            "env": execution_context["env"],
            "project_vars": execution_context["project_vars"],
            "runtime_vars": execution_context["runtime_vars"],
            "headers": execution_context["headers"],
            "params": execution_context["params"],
            "body": execution_context["body"],
            **helper_functions,
        }

    @staticmethod
    def md5(value):
        return hashlib.md5(str(value).encode("utf-8")).hexdigest()

    @staticmethod
    def sha256(value):
        return hashlib.sha256(str(value).encode("utf-8")).hexdigest()

    @staticmethod
    def base64_encode(value):
        return base64.b64encode(str(value).encode("utf-8")).decode("utf-8")

    @staticmethod
    def base64_decode(value):
        return base64.b64decode(str(value).encode("utf-8")).decode("utf-8")

    @staticmethod
    def url_encode(value):
        return urllib.parse.quote(str(value))

    @staticmethod
    def url_decode(value):
        return urllib.parse.unquote(str(value))

    @staticmethod
    def timestamp():
        return int(time())

    @staticmethod
    def uuid4():
        return str(uuid.uuid4())

    @staticmethod
    def json_dumps(value):
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def json_dumps_compact(value):
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'))

    @staticmethod
    def json_loads(value):
        return json.loads(value)
