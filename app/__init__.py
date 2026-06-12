import os
import re
from datetime import datetime, timedelta, timezone

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text

from flask import flash, redirect, request, url_for

from config import Config


db = SQLAlchemy()
BJT_TZ = timezone(timedelta(hours=8))

from app.project_context import get_active_project_id, sync_active_project_id
from app.models import Project
from app.security import accessible_projects, get_current_user, has_permission, load_current_user
from app.services.security_service import SecurityService


def register_blueprints(app):
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.ai_parser import ai_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.environment import environment_bp
    from app.routes.execution import execution_bp
    from app.routes.module import module_bp
    from app.routes.project import project_bp
    from app.routes.prompt_template import prompt_bp
    from app.routes.ui_automation import ui_automation_bp
    from app.routes.report import report_bp
    from app.routes.scenario import scenario_bp
    from app.routes.testcase import testcase_bp
    from app.routes.variable import variable_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(project_bp)
    app.register_blueprint(module_bp)
    app.register_blueprint(environment_bp)
    app.register_blueprint(variable_bp)
    app.register_blueprint(testcase_bp)
    app.register_blueprint(scenario_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(ui_automation_bp)
    app.register_blueprint(execution_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(prompt_bp)


def create_app():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    instance_path = os.path.join(project_root, "instance")
    app = Flask(
        __name__,
        instance_path=instance_path,
        static_folder=os.path.join(project_root, "public"),
        static_url_path="",
    )
    app.config.from_object(Config)

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)

    with app.app_context():
        from app import models  # noqa: F401

        db.create_all()
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
        SecurityService.ensure_default_data()

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

    @app.before_request
    def _load_current_user():
        load_current_user()

    @app.before_request
    def _protect_authenticated_routes():
        endpoint = request.endpoint or ""
        if endpoint.startswith("static") or endpoint.startswith("auth."):
            return None

        user = get_current_user()
        if not user:
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

    register_blueprints(app)
    return app
