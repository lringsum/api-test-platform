import json

from flask import current_app

from app.services.base_service import ServiceError, validate_case_schema
from app.services.prompt_service import PromptService
from app.services.testcase_service import TestCaseService
from app.utils.ai_mock import build_mock_case


class AIService:
    @staticmethod
    def build_prompt(document_text, template_id=None):
        document_text = str(document_text or "").strip()
        if not document_text:
            raise ServiceError("接口文档不能为空。")

        template = (
            PromptService.get_by_id(template_id)
            if template_id
            else PromptService.get_active_template()
        )

        return template.content.replace("{{document}}", document_text), template

    @staticmethod
    def parse_document(document_text, template_id=None):
        prompt_text, template = AIService.build_prompt(document_text, template_id)
        ai_mode = current_app.config.get("AI_MODE", "mock")

        if ai_mode == "mock":
            raw_result = AIService._mock_parse(document_text)
        elif ai_mode == "real":
            raw_result = AIService._real_parse(prompt_text)
        else:
            raise ServiceError(f"不支持的 AI_MODE：{ai_mode}")

        validated_case = AIService.validate_ai_output(raw_result)

        return {
            "mode": ai_mode,
            "template_id": template.id,
            "template_name": template.name,
            "prompt_preview": prompt_text,
            "raw_result": raw_result,
            "case_data": validated_case,
            "validation": {
                "valid": True,
                "message": "AI 解析结果校验通过。"
            },
        }

    @staticmethod
    def validate_ai_output(raw_result):
        if isinstance(raw_result, str):
            try:
                raw_result = json.loads(raw_result)
            except json.JSONDecodeError as exc:
                raise ServiceError(f"AI 返回结果不是合法 JSON：{exc.msg}") from exc

        return validate_case_schema(raw_result)

    @staticmethod
    def save_as_testcase(project_id, module_id, case_data, description="AI 解析生成"):
        validated = AIService.validate_ai_output(case_data)
        testcase = TestCaseService.create(
            project_id=project_id,
            module_id=module_id,
            name=validated["name"],
            description=description,
            case_data=validated,
            source="ai",
            is_active=True,
        )
        return testcase

    @staticmethod
    def _mock_parse(document_text):
        return build_mock_case(document_text)

    @staticmethod
    def _real_parse(prompt_text):
        raise ServiceError("当前版本仅实现 mock 模式，real 模式预留待扩展。")
