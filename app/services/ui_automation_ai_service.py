from __future__ import annotations

import json
import os
import re
from textwrap import dedent

import requests
from flask import current_app

from app import db
from app.models import UiAutomationAIRecord, UiAutomationRun
from app.services.base_service import ServiceError, commit_session
from app.services.ui_automation_service import UiAutomationService


SYSTEM_PROMPT = dedent(
    """
    你是一名资深 UI 自动化工程师，擅长 Python + Playwright + pytest。
    你的任务是根据业务目标、页面信息、已有码好的定位器和登录信息，生成可直接运行的 UI 自动化脚本。

    规则：
    1. 只输出 Python 代码，不要输出 Markdown、JSON 或解释。
    2. 优先使用稳定的 locator 和现有定位器库中的信息。
    3. 使用 pytest 风格。
    4. 尽量只覆盖一条主流程，脚本保持短而稳。
    5. 如果需要登录，优先封装成函数或局部 helper。
    6. 不要引入额外依赖。
    7. 若信息不足，生成可继续补全的骨架代码，并保留清晰注释。
    """
).strip()


class UiAutomationAIService:
    @staticmethod
    def _normalize_code(value):
        text = str(value or "").strip().lower()
        text = re.sub(r"[^a-z0-9_]+", "_", text)
        text = re.sub(r"_+", "_", text).strip("_")
        return text or "ai_generated_script"

    @staticmethod
    def _split_locator_codes(locator_codes):
        if not locator_codes:
            return []
        if isinstance(locator_codes, (list, tuple, set)):
            raw_items = locator_codes
        else:
            raw_items = (
                str(locator_codes)
                .replace("，", ",")
                .replace("、", ",")
                .split(",")
            )
        return [str(item).strip() for item in raw_items if str(item).strip()]

    @staticmethod
    def _load_locators(project_id, locator_codes=None):
        locators = UiAutomationService.build_locator_ai_context(project_id=project_id)
        selected = UiAutomationAIService._split_locator_codes(locator_codes)
        if selected:
            locators = [item for item in locators if item["code"] in selected]
        return locators

    @staticmethod
    def _build_prompt(context, locators):
        prompt_lines = [
            SYSTEM_PROMPT,
            "",
            "【项目上下文】",
            json.dumps(context, ensure_ascii=False, indent=2),
            "",
            "【可复用定位器】",
            json.dumps(locators, ensure_ascii=False, indent=2),
            "",
            "【输出要求】",
            "请生成一个可直接运行的 Python 测试文件，只输出代码。",
            "优先使用现有定位器和稳定的定位方式。",
            "如果存在登录流程，请先完成登录，再进入目标页面。",
            "如果定位器不足，请保留清晰的 TODO 注释，但仍然输出可执行的骨架代码。",
            "输出内容不要包含 Markdown、JSON 或解释文字。",
        ]
        prompt_lines.append(
            "New locator policy: use XPath only for any newly saved UI locator, and make sure the XPath is unique before storing it in the platform."
        )
        return "\n".join(prompt_lines).strip()

    @staticmethod
    def _locator_expression(locator):
        locator_type = locator["type"]
        locator_value = str(locator["value"] or "").strip()
        if locator_type == "role":
            try:
                payload = json.loads(locator_value)
            except json.JSONDecodeError:
                payload = {}
            role = payload.get("role") or "button"
            name = payload.get("name") or locator["name"]
            exact = payload.get("exact")
            if exact is False:
                return f"page.get_by_role({role!r}, name={name!r})"
            if exact is True:
                return f"page.get_by_role({role!r}, name={name!r}, exact=True)"
            return f"page.get_by_role({role!r}, name={name!r})"
        if locator_type == "label":
            return f"page.get_by_label({locator_value!r})"
        if locator_type == "placeholder":
            return f"page.get_by_placeholder({locator_value!r})"
        if locator_type == "text":
            return f"page.get_by_text({locator_value!r})"
        if locator_type == "testid":
            return f"page.get_by_test_id({locator_value!r})"
        if locator_type == "xpath":
            return f"page.locator({('xpath=' + locator_value)!r})"
        return f"page.locator({locator_value!r})"

    @staticmethod
    def _render_script(context, locators):
        script_code = UiAutomationAIService._normalize_code(context.get("script_code"))
        function_name = f"test_{script_code}"
        script_name = str(context.get("script_name") or "AI 自动化脚本").strip()
        test_goal = str(context.get("test_goal") or "").strip()
        page_url = str(context.get("page_url") or "").strip()
        page_name = str(context.get("page_name") or "").strip()
        need_login = bool(context.get("need_login"))
        login_url = str(context.get("login_url") or "/login").strip() or "/login"
        login_username = str(context.get("login_username") or "admin").strip() or "admin"
        login_password = str(context.get("login_password") or "admin123").strip() or "admin123"
        assert_text = str(context.get("assert_text") or "").strip()

        lines = [
            "from playwright.sync_api import expect",
            "",
            "",
            f"def {function_name}(page, base_url):",
            f"    \"\"\"{script_name}\"\"\"",
        ]

        if page_name:
            lines.append(f"    # 目标页面: {page_name}")
        if test_goal:
            lines.append(f"    # 目标: {test_goal}")

        if need_login:
            lines.extend(
                [
                    f"    page.goto(f\"{{base_url}}{login_url}\", wait_until=\"domcontentloaded\")",
                    f"    page.get_by_label(\"用户名\").fill({login_username!r})",
                    f"    page.get_by_label(\"密码\").fill({login_password!r})",
                    "    page.get_by_role('button', name='登录').click()",
                    "    page.wait_for_load_state('networkidle')",
                ]
            )

        lines.append(f"    target_url = {page_url!r} if {bool(page_url)!r} else base_url")
        lines.append(
            "    page.goto(target_url if target_url.startswith(('http://', 'https://')) else f'{base_url}{target_url}', wait_until='domcontentloaded')"
        )

        if assert_text:
            lines.append(f"    expect(page.get_by_text({assert_text!r})).to_be_visible()")
        elif page_name:
            lines.append(f"    expect(page.get_by_text({page_name!r})).to_be_visible()")
        else:
            lines.append("    expect(page.locator('body')).to_be_visible()")

        if locators:
            lines.append("")
            lines.append("    # 可复用定位器检查")
            for locator in locators[:5]:
                expr = UiAutomationAIService._locator_expression(locator)
                var_name = f"{UiAutomationAIService._normalize_code(locator['code'])}_locator"
                lines.append(f"    {var_name} = {expr}")
                lines.append(f"    expect({var_name}).to_be_visible()")
                if locator.get("usage_scene"):
                    lines.append(f"    # {locator['usage_scene']}")

        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def _build_openai_payload(prompt_text):
        model = str(
            current_app.config.get("OPENAI_MODEL")
            or os.environ.get("OPENAI_MODEL")
            or "gpt-4.1-mini"
        ).strip()
        timeout = int(
            current_app.config.get("OPENAI_TIMEOUT")
            or os.environ.get("OPENAI_TIMEOUT")
            or 60
        )
        max_tokens = int(
            current_app.config.get("OPENAI_MAX_TOKENS")
            or os.environ.get("OPENAI_MAX_TOKENS")
            or 4096
        )
        temperature = float(
            current_app.config.get("OPENAI_TEMPERATURE")
            or os.environ.get("OPENAI_TEMPERATURE")
            or 0.2
        )
        base_url = str(
            current_app.config.get("OPENAI_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        ).strip().rstrip("/")
        api_key = str(
            current_app.config.get("OPENAI_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        ).strip()

        if not api_key:
            raise ServiceError("AI_MODE=real 时需要配置 OPENAI_API_KEY。")

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt_text},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        return {
            "api_key": api_key,
            "base_url": base_url,
            "timeout": timeout,
            "model": model,
            "payload": payload,
        }

    @staticmethod
    def _extract_script_content(raw_content):
        content = str(raw_content or "").strip()
        if not content:
            raise ServiceError("AI 没有返回脚本内容。")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = None

        if isinstance(parsed, dict):
            for key in ("script_content", "content", "code", "output", "result"):
                candidate = str(parsed.get(key) or "").strip()
                if candidate:
                    content = candidate
                    break

        fence_match = re.search(r"```(?:python)?\s*(.*?)```", content, flags=re.IGNORECASE | re.DOTALL)
        if fence_match:
            content = fence_match.group(1).strip()

        return content.strip()

    @staticmethod
    def _call_real_model(prompt_text):
        config = UiAutomationAIService._build_openai_payload(prompt_text)
        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                f"{config['base_url']}/chat/completions",
                headers=headers,
                json=config["payload"],
                timeout=config["timeout"],
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ServiceError(f"AI 调用失败：{exc}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise ServiceError("AI 返回内容不是合法 JSON。") from exc

        try:
            raw_content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ServiceError("AI 返回格式不正确，缺少脚本内容。") from exc

        script_content = UiAutomationAIService._extract_script_content(raw_content)
        return script_content, config["model"]

    @staticmethod
    def _call_model(prompt_text):
        ai_mode = current_app.config.get("AI_MODE", "mock")
        if ai_mode == "mock":
            return UiAutomationAIService._render_script({}, []), "mock-ui-playwright"
        if ai_mode == "real":
            return UiAutomationAIService._call_real_model(prompt_text)
        raise ServiceError(f"不支持的 AI_MODE：{ai_mode}")

    @staticmethod
    def _build_repair_prompt(context, locators, current_script_content, failure_analysis):
        prompt_lines = [
            SYSTEM_PROMPT,
            "",
            "【当前脚本】",
            current_script_content.strip(),
            "",
            "【执行失败分析】",
            json.dumps(failure_analysis, ensure_ascii=False, indent=2),
            "",
            "【项目上下文】",
            json.dumps(context, ensure_ascii=False, indent=2),
            "",
            "【可复用定位器】",
            json.dumps(locators, ensure_ascii=False, indent=2),
            "",
            "【修复要求】",
            "请基于失败分析直接输出修复后的 Python + Playwright 脚本，只输出代码。",
            "优先复用定位器库中的稳定定位器。",
            "尽量只改动失败相关步骤，不要重写整个脚本。",
            "如果仍然存在不确定点，请保留清晰的 TODO 注释。",
            "输出内容不要包含 Markdown、JSON 或解释文本。",
        ]
        return "\n".join(prompt_lines).strip()

    @staticmethod
    def _render_repair_script(context, current_script_content, failure_analysis, locators):
        script_name = str(context.get("script_name") or "AI 修复脚本").strip()
        failure_label = str(failure_analysis.get("category_label") or "执行异常").strip()
        step_title = str(failure_analysis.get("step_title") or "").strip()
        root_cause = str(failure_analysis.get("root_cause") or "").strip()
        suggestion = str(failure_analysis.get("suggestion") or "").strip()

        lines = [
            current_script_content.strip(),
            "",
            "# AI repair summary",
            f"# script: {script_name}",
            f"# failure: {failure_label}",
        ]
        if step_title:
            lines.append(f"# step: {step_title}")
        if root_cause:
            lines.append(f"# root cause: {root_cause}")
        if suggestion:
            lines.append(f"# suggestion: {suggestion}")
        if locators:
            lines.append("# reusable locators")
            for locator in locators[:5]:
                lines.append(f"# - {locator['code']}: {locator['name']}")
        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def generate_script(
        project_id,
        script_name,
        script_code,
        test_goal,
        page_url="",
        page_name="",
        need_login=False,
        login_url="/login",
        login_username="admin",
        login_password="admin123",
        assert_text="",
        locator_codes=None,
        description="",
        entry_file="tests/test_ai_generated.py",
        created_by=None,
    ):
        project_id = int(project_id)
        locators = UiAutomationAIService._load_locators(project_id, locator_codes=locator_codes)
        context = {
            "project_id": project_id,
            "script_name": str(script_name or "").strip(),
            "script_code": str(script_code or "").strip(),
            "test_goal": str(test_goal or "").strip(),
            "page_url": str(page_url or "").strip(),
            "page_name": str(page_name or "").strip(),
            "need_login": bool(need_login),
            "login_url": str(login_url or "/login").strip(),
            "login_username": str(login_username or "admin").strip(),
            "login_password": str(login_password or "admin123").strip(),
            "assert_text": str(assert_text or "").strip(),
            "locator_codes": UiAutomationAIService._split_locator_codes(locator_codes),
            "entry_file": str(entry_file or "tests/test_ai_generated.py").strip(),
        }

        prompt_text = UiAutomationAIService._build_prompt(context, locators)
        ai_mode = current_app.config.get("AI_MODE", "mock")

        if ai_mode == "mock":
            script_content = UiAutomationAIService._render_script(context, locators)
            model_name = "mock-ui-playwright"
        elif ai_mode == "real":
            script_content, model_name = UiAutomationAIService._call_real_model(prompt_text)
        else:
            raise ServiceError(f"不支持的 AI_MODE：{ai_mode}")

        script = UiAutomationService.create_script(
            project_id=project_id,
            name=script_name,
            code=script_code,
            description=description or test_goal,
            language="python",
            framework="playwright",
            status="draft",
            entry_file=entry_file,
            script_content=script_content,
            created_by=created_by,
            ai_generated=True,
            ai_prompt=prompt_text,
        )

        record = UiAutomationAIRecord(
            project_id=project_id,
            script_id=script.id,
            record_type="script_generate",
            prompt_text=prompt_text,
            input_context=context,
            output_text=script_content,
            model_name=model_name,
            status="success",
            created_by=created_by,
        )
        db.session.add(record)
        commit_session()
        return {
            "script": script,
            "record": record,
            "prompt_text": prompt_text,
            "script_content": script_content,
            "locator_context": locators,
        }

    @staticmethod
    def repair_script_from_run(
        script_id,
        run_id,
        instruction="",
        created_by=None,
        locator_codes=None,
    ):
        script = UiAutomationService.get_script_by_id(script_id)
        run = db.session.get(UiAutomationRun, run_id)
        if not run:
            raise ServiceError("执行记录不存在。")
        if run.script_id != script.id:
            raise ServiceError("该执行记录不属于当前脚本。")

        version = UiAutomationService._get_latest_script_version(script)
        current_script_content = version.script_content if version else ""
        locators = UiAutomationAIService._load_locators(script.project_id, locator_codes=locator_codes)
        failure_analysis = UiAutomationService.analyze_run_failure(run)
        context = {
            "project_id": script.project_id,
            "script_id": script.id,
            "script_name": script.name,
            "script_code": script.code,
            "instruction": str(instruction or "").strip(),
            "run_id": run.id,
            "run_status": run.status,
            "environment_name": run.summary.get("environment_name", ""),
            "browser_type": run.browser_type,
            "entry_file": script.entry_file,
        }
        prompt_text = UiAutomationAIService._build_repair_prompt(
            context,
            locators,
            current_script_content,
            failure_analysis,
        )

        ai_mode = current_app.config.get("AI_MODE", "mock")
        if ai_mode == "mock":
            model_name = "mock-ui-playwright"
            script_content = UiAutomationAIService._render_repair_script(
                context,
                current_script_content,
                failure_analysis,
                locators,
            )
        elif ai_mode == "real":
            script_content, model_name = UiAutomationAIService._call_real_model(prompt_text)
        else:
            raise ServiceError(f"不支持的 AI_MODE：{ai_mode}")

        repaired_script = UiAutomationService.update_script(
            script_id=script.id,
            name=script.name,
            code=script.code,
            description=script.description,
            language=script.language,
            framework=script.framework,
            status=script.status,
            tags_text=", ".join(script.tags),
            entry_file=script.entry_file,
            script_content=script_content,
            owner_id=script.owner_id,
            created_by=created_by,
            ai_generated=True,
            ai_prompt=prompt_text,
            change_summary=f"AI 修复：{failure_analysis.get('category_label') or '执行异常'}",
        )

        record = UiAutomationAIRecord(
            project_id=script.project_id,
            script_id=script.id,
            run_id=run.id,
            record_type="script_repair",
            prompt_text=prompt_text,
            input_context={
                **context,
                "failure_analysis": failure_analysis,
                "locator_context": locators,
            },
            output_text=script_content,
            model_name=model_name,
            status="success",
            created_by=created_by,
        )
        db.session.add(record)
        commit_session()
        return {
            "script": repaired_script,
            "record": record,
            "prompt_text": prompt_text,
            "script_content": script_content,
            "failure_analysis": failure_analysis,
            "locator_context": locators,
        }
