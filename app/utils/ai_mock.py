import re


def infer_method(document_text):
    text = document_text.lower()
    if "post" in text:
        return "POST"
    return "GET"


def infer_url(document_text):
    matches = re.findall(r"(/api/[a-zA-Z0-9_/\-]+)", document_text)
    if matches:
        return matches[0]
    return "/api/mock-endpoint"


def infer_case_name(document_text):
    if "登录" in document_text or "login" in document_text.lower():
        return "登录成功"
    if "查询用户" in document_text or "user" in document_text.lower():
        return "查询用户信息"
    return "AI生成示例用例"


def build_mock_case(document_text):
    text = document_text.lower()
    method = infer_method(document_text)
    url = infer_url(document_text)
    case_name = infer_case_name(document_text)

    if "登录" in document_text or "login" in text:
        return {
            "name": "登录成功",
            "method": "POST",
            "url": "/api/login",
            "headers": {
                "Content-Type": "application/json"
            },
            "params": {},
            "body": {
                "username": "${username}",
                "password": "${password}"
            },
            "extract": {
                "token": "data.token"
            },
            "assertions": [
                {
                    "type": "status_code",
                    "expected": 200
                },
                {
                    "type": "json_path",
                    "path": "code",
                    "expected": 0
                },
                {
                    "type": "contains",
                    "expected": "success"
                },
                {
                    "type": "response_time",
                    "expected": 3000
                }
            ]
        }

    if "token" in text and method == "GET":
        return {
            "name": case_name,
            "method": "GET",
            "url": url,
            "headers": {
                "Authorization": "Bearer ${token}"
            },
            "params": {},
            "body": {},
            "extract": {},
            "assertions": [
                {
                    "type": "status_code",
                    "expected": 200
                },
                {
                    "type": "response_time",
                    "expected": 3000
                }
            ]
        }

    return {
        "name": case_name,
        "method": method,
        "url": url,
        "headers": {},
        "params": {},
        "body": {},
        "extract": {},
        "assertions": [
            {
                "type": "status_code",
                "expected": 200
            }
        ]
    }
