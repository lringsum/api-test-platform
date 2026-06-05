def get_value_by_path(data, path, default=None):
    if data is None or not path:
        return default

    current = data
    for part in str(path).split("."):
        if isinstance(current, dict):
            if part not in current:
                return default
            current = current[part]
            continue

        if isinstance(current, list):
            if not part.isdigit():
                return default
            index = int(part)
            if index < 0 or index >= len(current):
                return default
            current = current[index]
            continue

        return default

    return current


def extract_variables(extract_rules, response_json):
    extract_rules = extract_rules or {}
    result = {}
    extracted_values = {}

    if not isinstance(extract_rules, dict):
        return extracted_values, {
            "_error": {
                "success": False,
                "message": "extract 必须是对象",
            }
        }

    for variable_name, path in extract_rules.items():
        value = get_value_by_path(response_json, path, default=None)
        success = value is not None
        result[variable_name] = {
            "path": path,
            "value": value,
            "success": success,
            "message": "" if success else "提取路径不存在或响应不是 JSON",
        }
        if success:
            extracted_values[variable_name] = value

    return extracted_values, result
