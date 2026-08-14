import json
import os
import re
from datetime import datetime, timedelta, timezone

from flask import Flask
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text

from flask import flash, redirect, request, url_for

from config import Config


db = SQLAlchemy()
migrate = Migrate(compare_type=True)
BJT_TZ = timezone(timedelta(hours=8))

from app.project_context import get_active_project_id, sync_active_project_id
from app.models import Project
from app.security import accessible_projects, get_current_user, has_permission, load_current_user
from app.services.security_service import SecurityService


def register_blueprints(app):
    from app.routes.api_v1 import api_v1_bp
    from app.routes.auth import auth_bp
    from app.routes.legacy_spa import legacy_spa_bp
    from app.routes.spa import spa_bp

    app.register_blueprint(api_v1_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(spa_bp)
    app.register_blueprint(legacy_spa_bp)


def create_app():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    instance_path = os.path.join(project_root, "instance")
    # Runtime static assets are served from project_root/public.
    # app/static is reserved for non-runtime fixtures and deprecated placeholders.
    app = Flask(
        __name__,
        instance_path=instance_path,
        static_folder=os.path.join(project_root, "public"),
        static_url_path="/static",
    )
    app.config.from_object(Config)
    _apply_runtime_config_overrides(app)

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)

    if app.config.get("AUTO_DB_BOOTSTRAP", False):
        _bootstrap_database(app)

    with app.app_context():
        SecurityService.ensure_default_data()

    register_blueprints(app)
    return app


def _bootstrap_database(app):
    """Temporary compatibility bootstrap for local SQLite and legacy environments.

    Long-term schema evolution should use Alembic migrations.
    """
    with app.app_context():
        from app import models  # noqa: F401

        db.create_all()

        if not app.config.get("AUTO_DB_COMPAT_PATCH", False):
            return

        inspector = inspect(db.engine)
        ui_environment_columns = {
            column["name"]
            for column in inspector.get_columns("ui_automation_environments")
        }
        if "runtime_variables_json" not in ui_environment_columns:
            db.session.execute(
                text(
                    "ALTER TABLE ui_automation_environments "
                    "ADD COLUMN runtime_variables_json TEXT NOT NULL DEFAULT '{}'"
                )
            )
            db.session.commit()

        execution_columns = {
            column["name"] for column in inspector.get_columns("executions")
        }
        if "trigger_type" not in execution_columns:
            db.session.execute(
                text(
                    "ALTER TABLE executions "
                    "ADD COLUMN trigger_type TEXT NOT NULL DEFAULT 'manual'"
                )
            )
        if "trigger_user_id" not in execution_columns:
            db.session.execute(
                text("ALTER TABLE executions ADD COLUMN trigger_user_id INTEGER")
            )

        scenario_execution_columns = {
            column["name"] for column in inspector.get_columns("scenario_executions")
        }
        if "trigger_type" not in scenario_execution_columns:
            db.session.execute(
                text(
                    "ALTER TABLE scenario_executions "
                    "ADD COLUMN trigger_type TEXT NOT NULL DEFAULT 'manual'"
                )
            )
            db.session.execute(
                text(
                    "UPDATE scenario_executions SET trigger_type = "
                    "CASE WHEN lower(trigger_mode) = 'manual' "
                    "THEN 'manual' ELSE 'automatic' END"
                )
            )
        if "trigger_user_id" not in scenario_execution_columns:
            db.session.execute(
                text(
                    "ALTER TABLE scenario_executions "
                    "ADD COLUMN trigger_user_id INTEGER"
                )
            )

        ui_run_columns = {
            column["name"] for column in inspector.get_columns("ui_automation_runs")
        }
        if "trigger_type" not in ui_run_columns:
            db.session.execute(
                text(
                    "ALTER TABLE ui_automation_runs "
                    "ADD COLUMN trigger_type TEXT NOT NULL DEFAULT 'manual'"
                )
            )
            db.session.execute(
                text(
                    "UPDATE ui_automation_runs SET trigger_type = "
                    "CASE WHEN lower(run_mode) = 'manual' "
                    "THEN 'manual' ELSE 'automatic' END"
                )
            )
        db.session.commit()


def _apply_runtime_config_overrides(app):
    # Keep these flags dynamic so local scripts/tests can switch behavior per-process.
    auto_bootstrap = os.environ.get("AUTO_DB_BOOTSTRAP")
    if auto_bootstrap is not None:
        app.config["AUTO_DB_BOOTSTRAP"] = auto_bootstrap.lower() == "true"

    auto_compat_patch = os.environ.get("AUTO_DB_COMPAT_PATCH")
    if auto_compat_patch is not None:
        app.config["AUTO_DB_COMPAT_PATCH"] = auto_compat_patch.lower() == "true"

    @app.template_filter("bjt")
    def beijing_time(value, fmt="%Y-%m-%d %H:%M:%S"):
        if not value:
            return "-"
        if not isinstance(value, datetime):
            return value
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(BJT_TZ).strftime(fmt)

    @app.template_filter("clean_text")
    def clean_text(value, fallback=""):
        text = str(value or "").strip()
        if not text:
            return fallback
        if "锟?" in text or re.search(r"\?{2,}", text):
            if "showdoc" in text.lower():
                return "ShowDoc 自动生成用例"
            return fallback or "文本异常"
        return text

    @app.template_filter("pretty_json")
    def pretty_json(value):
        return json.dumps(value or {}, ensure_ascii=False, indent=2)

    @app.template_filter("browser_label")
    def browser_label(value):
        mapping = {
            "chromium": "Chromium 内核",
            "chrome": "Chrome 浏览器",
            "firefox": "Firefox 浏览器",
            "webkit": "WebKit 内核",
        }
        text = str(value or "").strip()
        return mapping.get(text.lower(), text or "-")

    @app.template_filter("result_status_label")
    def result_status_label(value):
        mapping = {
            "passed": "成功",
            "failed": "失败",
            "timeout": "超时",
            "queued": "排队中",
            "running": "执行中",
            "recovered": "已恢复",
        }
        text = str(value or "").strip()
        return mapping.get(text.lower(), text or "-")

    @app.before_request
    def _load_current_user():
        load_current_user()

    @app.before_request
    def _protect_authenticated_routes():
        endpoint = request.endpoint or ""
        if endpoint.startswith("static") or endpoint.startswith("auth.") or request.path.startswith("/app/assets/") or request.path in {"/app/login", "/app/forbidden", "/api/v1/session/login"}:
            return None

        user = get_current_user()
        if not user:
            if endpoint.startswith("api_v1."):
                from flask import jsonify
                return jsonify({"success": False, "message": "Authentication required.", "data": {}}), 401
            flash("请先登录后再访问系统。", "warning")
            return redirect(url_for("auth.login", next=request.url))

        sync_active_project_id()

    @app.context_processor
    def inject_project_context():
        current_project_id = get_active_project_id()
        user = get_current_user()
        projects = accessible_projects(user)
        current_project = db.session.get(Project, current_project_id) if current_project_id else None
        return {
            "global_projects": projects,
            "current_project_id": current_project_id,
            "current_project": current_project,
            "current_user": user,
            "has_permission": has_permission,
        }
