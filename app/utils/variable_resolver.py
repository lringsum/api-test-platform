import re

from app.services.base_service import ServiceError


VARIABLE_PATTERN = re.compile(r"\$\{([a-zA-Z0-9_]+)\}")
FULL_VARIABLE_PATTERN = re.compile(r"^\$\{([a-zA-Z0-9_]+)\}$")


def resolve_variables(value, variables):
    if isinstance(value, str):
        return _replace_in_string(value, variables)
    if isinstance(value, dict):
        return {k: resolve_variables(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_variables(item, variables) for item in value]
    return value


def _replace_in_string(text, variables):
    full_match = FULL_VARIABLE_PATTERN.fullmatch(text)
    if full_match:
        key = full_match.group(1)
        if key not in variables:
            raise ServiceError(f"变量未定义：{key}")
        return variables[key]

    def replacer(match):
        key = match.group(1)
        if key not in variables:
            raise ServiceError(f"变量未定义：{key}")
        return str(variables[key])

    return VARIABLE_PATTERN.sub(replacer, text)
