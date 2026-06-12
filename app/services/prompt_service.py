from app import db
from app.models import PromptTemplate
from app.services.base_service import ServiceError, commit_session, ensure_not_blank


class PromptService:
    @staticmethod
    def list_all():
        return PromptTemplate.query.order_by(PromptTemplate.created_at.desc()).all()

    @staticmethod
    def list_active():
        return PromptTemplate.query.filter_by(is_active=True).order_by(
            PromptTemplate.created_at.desc()
        ).all()

    @staticmethod
    def get_by_id(template_id):
        template = db.session.get(PromptTemplate, template_id)
        if not template:
            raise ServiceError("Prompt 模板不存在。")
        return template

    @staticmethod
    def get_active_template():
        template = PromptTemplate.query.filter_by(is_active=True).order_by(
            PromptTemplate.updated_at.desc()
        ).first()
        if not template:
            raise ServiceError("当前没有可用的 Prompt 模板。")
        return template

    @staticmethod
    def create(name, content, description="", is_active=True):
        name = ensure_not_blank(name, "模板名称")
        content = ensure_not_blank(content, "模板内容")
        description = str(description or "").strip()

        exists = PromptTemplate.query.filter_by(name=name).first()
        if exists:
            raise ServiceError("模板名称已存在。")

        template = PromptTemplate(
            name=name,
            content=content,
            description=description,
            is_active=bool(is_active),
        )
        db.session.add(template)
        commit_session()
        return template

    @staticmethod
    def update(template_id, name, content, description="", is_active=True):
        template = PromptService.get_by_id(template_id)
        name = ensure_not_blank(name, "模板名称")
        content = ensure_not_blank(content, "模板内容")
        description = str(description or "").strip()

        exists = PromptTemplate.query.filter(
            PromptTemplate.name == name,
            PromptTemplate.id != template_id,
        ).first()
        if exists:
            raise ServiceError("模板名称已存在。")

        template.name = name
        template.content = content
        template.description = description
        template.is_active = bool(is_active)
        commit_session()
        return template

    @staticmethod
    def delete(template_id):
        template = PromptService.get_by_id(template_id)
        db.session.delete(template)
        commit_session()
        return True
