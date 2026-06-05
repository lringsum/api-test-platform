import os
import re
from datetime import datetime, timedelta, timezone

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from app.project_context import get_active_project_id, sync_active_project_id
from config import Config


db = SQLAlchemy()
BJT_TZ = timezone(timedelta(hours=8))


def register_blueprints(app):
    from app.routes.ai_parser import ai_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.environment import environment_bp
    from app.routes.execution import execution_bp
    from app.routes.module import module_bp
    from app.routes.project import project_bp
    from app.routes.prompt_template import prompt_bp
    from app.routes.report import report_bp
    from app.routes.scenario import scenario_bp
    from app.routes.testcase import testcase_bp
    from app.routes.variable import variable_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(project_bp)
    app.register_blueprint(module_bp)
    app.register_blueprint(environment_bp)
    app.register_blueprint(variable_bp)
    app.register_blueprint(testcase_bp)
    app.register_blueprint(scenario_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(execution_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(prompt_bp)


def create_app():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    app = Flask(
        __name__,
        instance_relative_config=True,
        static_folder=os.path.join(project_root, "public"),
        static_url_path="",
    )
    app.config.from_object(Config)

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)

    with app.app_context():
        from app import models  # noqa: F401

        db.create_all()

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
    def _sync_project_context():
        sync_active_project_id()

    @app.context_processor
    def inject_project_context():
        from app.models import Project

        current_project_id = get_active_project_id()
        projects = Project.query.order_by(Project.created_at.desc()).all()
        current_project = Project.query.get(current_project_id) if current_project_id else None
        return {
            "global_projects": projects,
            "current_project_id": current_project_id,
            "current_project": current_project,
        }

    register_blueprints(app)
    return app
