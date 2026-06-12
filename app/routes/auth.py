from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.security import get_current_user, login_user, logout_user
from app.services.base_service import ServiceError
from app.services.security_service import SecurityService

auth_bp = Blueprint("auth", __name__, url_prefix="")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if get_current_user():
        return redirect(url_for("dashboard.index"))

    next_url = request.args.get("next") or request.form.get("next") or url_for("dashboard.index")
    if request.method == "POST":
        try:
            user = SecurityService.authenticate(
                username=request.form.get("username"),
                password=request.form.get("password"),
            )
            login_user(user)
            SecurityService.record_audit("login", resource_type="auth")
            flash("登录成功。", "success")
            return redirect(next_url or url_for("dashboard.index"))
        except ServiceError as exc:
            flash(str(exc), "danger")

    return render_template("auth/login.html", next_url=next_url)


@auth_bp.route("/logout", methods=["POST"])
def logout():
    user = get_current_user()
    if user:
        try:
            SecurityService.record_audit("logout", resource_type="auth")
        except Exception:
            pass
    logout_user()
    flash("你已退出登录。", "success")
    return redirect(url_for("auth.login"))
