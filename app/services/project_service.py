from app import db
from app.models import Project
from app.services.base_service import ServiceError, commit_session, ensure_not_blank


class ProjectService:
    @staticmethod
    def list_all():
        return Project.query.order_by(Project.created_at.desc()).all()

    @staticmethod
    def get_by_id(project_id):
        project = db.session.get(Project, project_id)
        if not project:
            raise ServiceError("项目不存在。")
        return project

    @staticmethod
    def create(name, description=""):
        name = ensure_not_blank(name, "项目名称")
        description = str(description or "").strip()

        exists = Project.query.filter_by(name=name).first()
        if exists:
            raise ServiceError("项目名称已存在。")

        project = Project(name=name, description=description, status="active")
        db.session.add(project)
        commit_session()
        return project

    @staticmethod
    def update(project_id, name, description="", status="active"):
        project = ProjectService.get_by_id(project_id)
        name = ensure_not_blank(name, "项目名称")
        description = str(description or "").strip()
        status = str(status or "active").strip()

        exists = Project.query.filter(
            Project.name == name,
            Project.id != project_id,
        ).first()
        if exists:
            raise ServiceError("项目名称已存在。")

        project.name = name
        project.description = description
        project.status = status
        commit_session()
        return project

    @staticmethod
    def delete(project_id):
        project = ProjectService.get_by_id(project_id)
        db.session.delete(project)
        commit_session()
        return True
