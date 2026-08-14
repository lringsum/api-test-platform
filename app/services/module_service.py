from app import db
from app.models import Module, Project
from app.services.base_service import ServiceError, commit_session, ensure_not_blank


class ModuleService:
    @staticmethod
    def list_all(project_id=None, keyword="", kind=""):
        query = Module.query
        if project_id:
            query = query.filter_by(project_id=project_id)
        modules = query.order_by(Module.created_at.desc()).all()

        normalized_keyword = str(keyword or "").strip().lower()
        if normalized_keyword:
            modules = [
                module
                for module in modules
                if normalized_keyword in (module.name or "").lower()
                or normalized_keyword in (module.description or "").lower()
            ]

        normalized_kind = str(kind or "").strip().lower()
        if normalized_kind in {"api", "scenario", "mixed"}:
            modules = [module for module in modules if ModuleService.kind_for(module) == normalized_kind]
        return modules

    @staticmethod
    def kind_for(module):
        has_api_cases = bool(module.testcases)
        has_scenarios = bool(module.scenarios)
        if has_api_cases and has_scenarios:
            return "mixed"
        if has_scenarios:
            return "scenario"
        return "api"

    @staticmethod
    def get_by_id(module_id):
        module = db.session.get(Module, module_id)
        if not module:
            raise ServiceError("模块不存在。")
        return module

    @staticmethod
    def create(project_id, name, description=""):
        project = db.session.get(Project, project_id)
        if not project:
            raise ServiceError("所属项目不存在。")

        name = ensure_not_blank(name, "模块名称")
        description = str(description or "").strip()

        exists = Module.query.filter_by(project_id=project_id, name=name).first()
        if exists:
            raise ServiceError("同一项目下模块名称已存在。")

        module = Module(project_id=project_id, name=name, description=description)
        db.session.add(module)
        commit_session()
        return module

    @staticmethod
    def update(module_id, name, description=""):
        module = ModuleService.get_by_id(module_id)
        name = ensure_not_blank(name, "模块名称")
        description = str(description or "").strip()

        exists = Module.query.filter(
            Module.project_id == module.project_id,
            Module.name == name,
            Module.id != module_id,
        ).first()
        if exists:
            raise ServiceError("同一项目下模块名称已存在。")

        module.name = name
        module.description = description
        commit_session()
        return module

    @staticmethod
    def delete(module_id):
        module = ModuleService.get_by_id(module_id)
        db.session.delete(module)
        commit_session()
        return True
