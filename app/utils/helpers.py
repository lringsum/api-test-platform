import json


def truncate_text(text, max_length=5000):
    if text is None:
        return ""
    text = str(text)
    if len(text) <= max_length:
        return text
    return text[:max_length] + "...<truncated>"


def safe_response_json(response):
    try:
        return response.json()
    except ValueError:
        return None


def pretty_json(data):
    try:
        return json.dumps(data, ensure_ascii=False, indent=2)
    except TypeError:
        return str(data)


def build_text_preview(text, max_length=4000):
    normalized = "" if text is None else str(text)
    return {
        "text": truncate_text(normalized, max_length=max_length),
        "length": len(normalized),
        "truncated": len(normalized) > max_length,
    }
