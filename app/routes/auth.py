from urllib.parse import urlencode, urlparse

from flask import Blueprint, redirect, request, url_for

from app.security import get_current_user, login_user, logout_user
from app.services.base_service import ServiceError
from app.services.security_service import SecurityService

auth_bp = Blueprint("auth", __name__, url_prefix="")


def _safe_next_url(value):
    fallback = "/app/"
    candidate = str(value or "").strip()
    if not candidate:
        return fallback
    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc:
        if parsed.netloc != request.host:
            return fallback
        candidate = f"{parsed.path or '/'}{f'?{parsed.query}' if parsed.query else ''}"
    return candidate if candidate.startswith("/") else fallback


def _spa_login_redirect(next_url="", error=""):
    query = {"next": _safe_next_url(next_url)}
    if error:
        query["error"] = error
    return redirect(f"/app/login?{urlencode(query)}")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if get_current_user():
        return redirect(_safe_next_url(request.args.get("next")))

    next_url = _safe_next_url(request.args.get("next") or request.form.get("next"))
    if request.method == "POST":
        try:
            user = SecurityService.authenticate(
                username=request.form.get("username"),
                password=request.form.get("password"),
            )
            login_user(user)
            SecurityService.record_audit("login", resource_type="auth")
            return redirect(next_url)
        except ServiceError:
            return _spa_login_redirect(next_url, "invalid_credentials")

    return _spa_login_redirect(next_url)


@auth_bp.route("/forbidden", methods=["GET"])
def forbidden():
    if not get_current_user():
        return redirect(url_for("auth.login", next=request.url))
    return redirect("/app/forbidden")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    user = get_current_user()
    if user:
        try:
            SecurityService.record_audit("logout", resource_type="auth")
        except Exception:
            pass
    logout_user()
    return _spa_login_redirect()
