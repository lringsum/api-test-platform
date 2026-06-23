from app.utils.extractor import get_value_by_path
from app.utils.variable_resolver import resolve_variables


def run_assertions(assertions, response_snapshot, duration_ms, runtime_variables=None):
    results = []
    assertions = resolve_variables(assertions or [], runtime_variables or {})

    for item in assertions:
        assert_type = item.get("type")
        expected = item.get("expected")
        passed = False
        actual = None
        message = ""

        if assert_type == "status_code":
            actual = response_snapshot.get("status_code")
            passed = actual == expected
            if not passed:
                message = f"期望状态码 {expected}，实际 {actual}"

        elif assert_type == "json_path":
            response_json = response_snapshot.get("json")
            path = item.get("path")
            actual = get_value_by_path(response_json, path, default=None)
            passed = actual == expected
            if response_json is None:
                message = "响应不是合法 JSON，无法执行 json_path 断言"
            elif not passed:
                message = f"路径 {path} 期望值 {expected}，实际 {actual}"

        elif assert_type == "contains":
            actual = response_snapshot.get("text", "")
            passed = str(expected) in str(actual)
            if not passed:
                message = f"响应内容不包含期望文本：{expected}"

        elif assert_type == "json_array_contains":
            response_json = response_snapshot.get("json")
            path = item.get("path")
            item_path = item.get("item_path")
            actual = get_value_by_path(response_json, path, default=None)
            if isinstance(actual, list):
                if item_path:
                    passed = any(
                        get_value_by_path(value, item_path, default=None) == expected
                        for value in actual
                    )
                else:
                    passed = expected in actual
            if response_json is None:
                message = "响应不是合法 JSON，无法执行 json_array_contains 断言"
            elif not isinstance(actual, list):
                message = f"路径 {path} 的实际值不是数组"
            elif not passed:
                message = f"路径 {path} 的数组中不包含期望值 {expected}"

        elif assert_type == "response_time":
            actual = duration_ms
            try:
                threshold = int(expected)
            except (TypeError, ValueError):
                threshold = -1
            passed = threshold >= 0 and duration_ms <= threshold
            if not passed:
                message = f"响应耗时 {duration_ms}ms，超过阈值 {expected}ms"

        else:
            passed = False
            message = f"不支持的断言类型：{assert_type}"

        results.append(
            {
                "type": assert_type,
                "expected": expected,
                "actual": actual,
                "passed": passed,
                "message": message,
            }
        )

    overall_passed = all(item["passed"] for item in results) if results else False
    return overall_passed, results
