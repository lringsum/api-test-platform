from urllib.parse import urlencode

from flask import Blueprint, redirect, request


legacy_spa_bp = Blueprint("legacy_spa", __name__)


_PREFIX_MAP = (
    ("admin", "security"), ("projects", "projects"), ("modules", "modules"),
    ("environments", "environments"), ("variables", "variables"),
    ("testcases", "testcases"), ("scenarios", "scenarios"), ("executions", "executions"),
    ("reports", "executions"),
    ("ui-automation", "web-automation"), ("android-ui-automation", "android-automation"),
)


@legacy_spa_bp.route("/", defaults={"legacy_path": ""}, methods=["GET"])
@legacy_spa_bp.route("/<path:legacy_path>", methods=["GET"])
def legacy_page_redirect(legacy_path):
    head = str(legacy_path or "").split("/", 1)[0]
    target = next((spa_path for prefix, spa_path in _PREFIX_MAP if prefix == head), "")
    query = urlencode(request.args, doseq=True)
    return redirect(f"/app/{target}{f'?{query}' if query else ''}")
