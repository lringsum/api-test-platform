import json

from app import db
from app.models import Environment, Project, Variable
from app.services.base_service import (
    ServiceError,
    commit_session,
    ensure_choice,
    ensure_not_blank,
)


class VariableService:
    AUTO_EXTRACT_DESC_PREFIX = "[AUTO_EXTRACT]"

    @staticmethod
    def list_all(project_id=None, environment_id=None):
        query = Variable.query
        if project_id:
            query = query.filter_by(project_id=project_id)
        if environment_id is not None:
            query = query.filter_by(environment_id=environment_id)
        return query.order_by(Variable.created_at.desc()).all()

    @staticmethod
    def get_by_id(variable_id):
        variable = Variable.query.get(variable_id)
        if not variable:
            raise ServiceError("变量不存在。")
        return variable

    @staticmethod
    def create(project_id, name, value, scope="project", environment_id=None, description=""):
        project = Project.query.get(project_id)
        if not project:
            raise ServiceError("所属项目不存在。")

        scope = ensure_choice(scope, "变量作用域", ["project", "environment"])
        name = ensure_not_blank(name, "变量名称")
        value = "" if value is None else str(value)
        description = str(description or "").strip()

        if scope == "environment":
            if not environment_id:
                raise ServiceError("环境级变量必须指定环境。")
            environment = Environment.query.get(environment_id)
            if not environment or environment.project_id != project_id:
                raise ServiceError("所属环境不存在或与项目不匹配。")
        else:
            environment_id = None

        exists = Variable.query.filter_by(
            project_id=project_id,
            environment_id=environment_id,
            name=name,
        ).first()
        if exists:
            raise ServiceError("当前作用域下变量名称已存在。")

        variable = Variable(
            project_id=project_id,
            environment_id=environment_id,
            name=name,
            value=value,
            scope=scope,
            description=description,
        )
        db.session.add(variable)
        commit_session()
        return variable

    @staticmethod
    def update(variable_id, name, value, scope="project", environment_id=None, description=""):
        variable = VariableService.get_by_id(variable_id)

        scope = ensure_choice(scope, "变量作用域", ["project", "environment"])
        name = ensure_not_blank(name, "变量名称")
        value = "" if value is None else str(value)
        description = str(description or "").strip()

        if scope == "environment":
            if not environment_id:
                raise ServiceError("环境级变量必须指定环境。")
            environment = Environment.query.get(environment_id)
            if not environment or environment.project_id != variable.project_id:
                raise ServiceError("所属环境不存在或与项目不匹配。")
        else:
            environment_id = None

        exists = Variable.query.filter(
            Variable.project_id == variable.project_id,
            Variable.environment_id == environment_id,
            Variable.name == name,
            Variable.id != variable_id,
        ).first()
        if exists:
            raise ServiceError("当前作用域下变量名称已存在。")

        variable.name = name
        variable.value = value
        variable.scope = scope
        variable.environment_id = environment_id
        variable.description = description
        commit_session()
        return variable

    @staticmethod
    def delete(variable_id):
        variable = VariableService.get_by_id(variable_id)
        db.session.delete(variable)
        commit_session()
        return True

    @staticmethod
    def build_runtime_variables(project_id, environment_id=None):
        variables = VariableService.build_project_variables(project_id)

        if environment_id:
            variables.update(
                VariableService.build_environment_variables(project_id, environment_id)
            )

        return variables

    @staticmethod
    def build_project_variables(project_id):
        project = Project.query.get(project_id)
        if not project:
            raise ServiceError("所属项目不存在。")

        project_variables = Variable.query.filter_by(
            project_id=project_id,
            environment_id=None,
        ).all()
        return {item.name: item.value for item in project_variables}

    @staticmethod
    def build_environment_variables(project_id, environment_id):
        if not environment_id:
            return {}

        environment = Environment.query.get(environment_id)
        if not environment or environment.project_id != project_id:
            raise ServiceError("环境不存在或与项目不匹配。")

        variables = {}
        variables.update(environment.variables_data)

        environment_variables = Variable.query.filter_by(
            project_id=project_id,
            environment_id=environment_id,
        ).all()
        variables.update({item.name: item.value for item in environment_variables})
        return variables

    @staticmethod
    def upsert_environment_variables(project_id, environment_id, extracted_values):
        if not extracted_values:
            return

        environment = Environment.query.get(environment_id)
        if not environment or environment.project_id != project_id:
            raise ServiceError("环境不存在或与项目不匹配。")

        for name, value in extracted_values.items():
            clean_name = str(name or "").strip()
            if not clean_name:
                continue

            stored_value = VariableService._to_storage_text(value)
            variable = Variable.query.filter_by(
                project_id=project_id,
                environment_id=environment_id,
                name=clean_name,
            ).first()

            if variable:
                variable.value = stored_value
                if not variable.scope:
                    variable.scope = "environment"
                if not variable.description:
                    variable.description = f"{VariableService.AUTO_EXTRACT_DESC_PREFIX} 执行自动提取写入"
            else:
                db.session.add(
                    Variable(
                        project_id=project_id,
                        environment_id=environment_id,
                        name=clean_name,
                        value=stored_value,
                        scope="environment",
                        description=f"{VariableService.AUTO_EXTRACT_DESC_PREFIX} 执行自动提取写入",
                    )
                )

        commit_session()

    @staticmethod
    def _to_storage_text(value):
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)
