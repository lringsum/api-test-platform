from urllib.parse import urljoin

from app.utils.variable_resolver import resolve_variables


def build_full_url(base_url, path):
    normalized_base = str(base_url).rstrip("/") + "/"
    normalized_path = str(path).lstrip("/")
    return urljoin(normalized_base, normalized_path)


def build_request_data(testcase_data, environment, runtime_variables, timeout):
    resolved_headers = resolve_variables(
        testcase_data.get("headers", {}), runtime_variables
    )
    resolved_params = resolve_variables(
        testcase_data.get("params", {}), runtime_variables
    )
    resolved_body = resolve_variables(testcase_data.get("body", {}), runtime_variables)
    resolved_files = resolve_variables(testcase_data.get("files", {}), runtime_variables)
    resolved_path = resolve_variables(testcase_data.get("url", ""), runtime_variables)

    merged_headers = {}
    merged_headers.update(environment.headers or {})
    merged_headers.update(resolved_headers)

    method = testcase_data.get("method", "GET").upper()
    full_url = build_full_url(environment.base_url, resolved_path)

    request_snapshot = {
        "method": method,
        "url": full_url,
        "path": resolved_path,
        "headers": merged_headers,
        "params": resolved_params,
        "body": resolved_body,
        "files": resolved_files,
        "body_type": testcase_data.get("body_type", "json"),
        "timeout": timeout,
    }

    return request_snapshot
