from app import db
from app.models import Environment, Project
from app.services.base_service import (
    ServiceError,
    commit_session,
    ensure_not_blank,
    parse_json_text,
)


class EnvironmentService:
    @staticmethod
    def list_all(project_id=None):
        query = Environment.query
        if project_id:
            query = query.filter_by(project_id=project_id)
        return query.order_by(Environment.created_at.desc()).all()

    @staticmethod
    def get_by_id(environment_id):
        environment = db.session.get(Environment, environment_id)
        if not environment:
            raise ServiceError("环境不存在。")
        return environment

    @staticmethod
    def create(project_id, name, base_url, headers_json="{}", variables_json="{}", description=""):
        project = db.session.get(Project, project_id)
        if not project:
            raise ServiceError("所属项目不存在。")

        name = ensure_not_blank(name, "环境名称")
        base_url = ensure_not_blank(base_url, "Base URL")
        description = str(description or "").strip()
        headers = parse_json_text(headers_json, "环境请求头 JSON")
        variables = parse_json_text(variables_json, "环境变量 JSON")

        if not isinstance(headers, dict):
            raise ServiceError("环境请求头 JSON 必须是对象。")
        if not isinstance(variables, dict):
            raise ServiceError("环境变量 JSON 必须是对象。")

        exists = Environment.query.filter_by(project_id=project_id, name=name).first()
        if exists:
            raise ServiceError("同一项目下环境名称已存在。")

        environment = Environment(
            project_id=project_id,
            name=name,
            base_url=base_url,
            description=description,
            is_active=True,
        )
        environment.headers = headers
        environment.variables_data = variables

        db.session.add(environment)
        commit_session()
        return environment

    @staticmethod
    def update(environment_id, name, base_url, headers_json="{}", variables_json="{}", description="", is_active=True):
        environment = EnvironmentService.get_by_id(environment_id)

        name = ensure_not_blank(name, "环境名称")
        base_url = ensure_not_blank(base_url, "Base URL")
        description = str(description or "").strip()
        headers = parse_json_text(headers_json, "环境请求头 JSON")
        variables = parse_json_text(variables_json, "环境变量 JSON")

        if not isinstance(headers, dict):
            raise ServiceError("环境请求头 JSON 必须是对象。")
        if not isinstance(variables, dict):
            raise ServiceError("环境变量 JSON 必须是对象。")

        exists = Environment.query.filter(
            Environment.project_id == environment.project_id,
            Environment.name == name,
            Environment.id != environment_id,
        ).first()
        if exists:
            raise ServiceError("同一项目下环境名称已存在。")

        environment.name = name
        environment.base_url = base_url
        environment.description = description
        environment.is_active = bool(is_active)
        environment.headers = headers
        environment.variables_data = variables
        commit_session()
        return environment

    @staticmethod
    def delete(environment_id):
        environment = EnvironmentService.get_by_id(environment_id)
        db.session.delete(environment)
        commit_session()
        return True
