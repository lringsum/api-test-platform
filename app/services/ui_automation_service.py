from __future__ import annotations

import re
from collections import Counter, defaultdict

from flask import current_app

from app import db
from app.models import (
    Project,
    UiAutomationArtifact,
    UiAutomationEnvironment,
    UiAutomationLocator,
    UiAutomationProjectSetting,
    UiAutomationRun,
    UiAutomationRunStep,
    UiAutomationScript,
    UiAutomationScriptVersion,
)
from app.services.base_service import ServiceError, commit_session, ensure_not_blank
from app.utils.trigger import normalize_trigger_type
from sqlalchemy.orm import selectinload


DEFAULT_SCRIPT_TEMPLATE = """from playwright.sync_api import expect


def test_example(page, base_url):
    page.goto(f"{base_url}/login", wait_until="domcontentloaded")
    page.get_by_label("???").fill("admin")
    page.get_by_label("??").fill("admin123")
    page.get_by_role("button", name="??").click()
    expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()
"""


class UiAutomationService:
    CHANGE_SUMMARY_FALLBACK = "内容更新"
    CHANGE_SUMMARY_GARBLED_FALLBACK = "说明疑似乱码，已使用默认说明"
    _GARBLED_TEXT_MARKERS = ("�", "锟", "Ã", "鈥", "銆", "鐧", "闂")

    @staticmethod
    def is_suspect_change_summary(value):
        text = str(value or "").strip()
        if not text:
            return False
        if "\ufffd" in text:
            return True
        marker_hits = sum(text.count(marker) for marker in UiAutomationService._GARBLED_TEXT_MARKERS)
        if marker_hits >= 2:
            return True
        question_count = text.count("?")
        if "???" in text:
            return True
        if question_count >= 2 and question_count / max(len(text), 1) >= 0.2:
            return True
        return False

    @staticmethod
    def sanitize_change_summary(value, fallback=None):
        fallback_text = str(fallback or UiAutomationService.CHANGE_SUMMARY_FALLBACK).strip()
        text = str(value or "").strip()
        if not text:
            return fallback_text
        if UiAutomationService.is_suspect_change_summary(text):
            return fallback_text
        return text

    @staticmethod
    def display_change_summary(value, fallback=None):
        fallback_text = str(fallback or UiAutomationService.CHANGE_SUMMARY_FALLBACK).strip()
        text = str(value or "").strip()
        if not text:
            return fallback_text
        if UiAutomationService.is_suspect_change_summary(text):
            return UiAutomationService.CHANGE_SUMMARY_GARBLED_FALLBACK
        return text

    @staticmethod
    def decorate_version_display(version):
        if not version:
            return None
        setattr(
            version,
            "display_change_summary",
            UiAutomationService.display_change_summary(version.change_summary),
        )
        return version

    @staticmethod
    def get_project_settings(project_id, ensure_exists=False):
        if not project_id:
            return None
        normalized_project_id = int(project_id)
        settings = UiAutomationProjectSetting.query.filter_by(project_id=normalized_project_id).first()
        if settings or not ensure_exists:
            return settings
        settings = UiAutomationProjectSetting(project_id=normalized_project_id)
        settings.settings = {}
        db.session.add(settings)
        db.session.flush()
        return settings

    @staticmethod
    def get_artifact_keep_latest_runs(project_id=None):
        default_value = int(
            current_app.config.get("UI_AUTOMATION_ARTIFACT_KEEP_LATEST_RUNS", 30)
        )
        if not project_id:
            return max(default_value, 1)
        settings = UiAutomationService.get_project_settings(project_id)
        if not settings:
            return max(default_value, 1)
        value = settings.get_int("artifact_keep_latest_runs", default_value)
        return max(value, 1)

    @staticmethod
    def update_project_settings(project_id, artifact_keep_latest_runs):
        normalized_project_id = int(ensure_not_blank(project_id, "所属项目"))
        keep_latest_runs = int(ensure_not_blank(artifact_keep_latest_runs, "产物保留次数"))
        if keep_latest_runs < 1 or keep_latest_runs > 500:
            raise ServiceError("产物保留次数仅支持 1 到 500 之间的整数。")

        project = db.session.get(Project, normalized_project_id)
        if not project:
            raise ServiceError("所属项目不存在。")

        settings = UiAutomationService.get_project_settings(
            normalized_project_id,
            ensure_exists=True,
        )
        settings.set_value("artifact_keep_latest_runs", keep_latest_runs)
        commit_session()
        return settings

    @staticmethod
    def _normalize_locator_code(value):
        text = str(value or "").strip().lower()
        text = re.sub(r"[^a-z0-9_]+", "_", text)
        text = re.sub(r"_+", "_", text).strip("_")
        return text or "locator"

    @staticmethod
    def serialize_locator(locator):
        return {
            "id": locator.id,
            "project_id": locator.project_id,
            "page_name": locator.page_name,
            "page_url_pattern": locator.page_url_pattern,
            "locator_name": locator.locator_name,
            "locator_code": locator.locator_code,
            "locator_type": locator.locator_type,
            "locator_value": locator.locator_value,
            "description": locator.description,
            "usage_scene": locator.usage_scene,
            "is_stable": locator.is_stable,
            "status": locator.status,
            "created_by": locator.created_by,
            "updated_by": locator.updated_by,
            "created_at": locator.created_at.isoformat() if locator.created_at else None,
            "updated_at": locator.updated_at.isoformat() if locator.updated_at else None,
        }

    @staticmethod
    def list_scripts(project_id=None, project_ids=None):
        query = UiAutomationScript.query
        if project_id:
            query = query.filter_by(project_id=project_id)
        elif project_ids:
            query = query.filter(UiAutomationScript.project_id.in_(project_ids))
        return query.order_by(UiAutomationScript.updated_at.desc(), UiAutomationScript.id.desc()).all()

    @staticmethod
    def get_script_by_id(script_id):
        script = db.session.get(UiAutomationScript, script_id)
        if not script:
            raise ServiceError("UI 脚本不存在。")
        return script

    @staticmethod
    def _normalize_tags(tags_text):
        if not tags_text:
            return []
        if isinstance(tags_text, list):
            return [str(item).strip() for item in tags_text if str(item).strip()]
        return [item.strip() for item in str(tags_text).replace("，", ",").split(",") if item.strip()]

    @staticmethod
    def _next_version_no(script_id):
        latest = (
            UiAutomationScriptVersion.query.filter_by(script_id=script_id)
            .order_by(UiAutomationScriptVersion.version_no.desc())
            .first()
        )
        return (latest.version_no + 1) if latest else 1

    @staticmethod
    def _is_login_script(name="", code="", tags=None):
        normalized_tags = {
            str(item or "").strip().lower()
            for item in (tags or [])
            if str(item or "").strip()
        }
        normalized_name = str(name or "").strip().lower()
        normalized_code = str(code or "").strip().lower()
        return (
            "login" in normalized_tags
            or "登录" in normalized_tags
            or ("login" in normalized_code and "登录" in normalized_name)
        )

    @staticmethod
    def default_login_dependency(project_id, exclude_script_id=None, required=True):
        query = UiAutomationScript.query.filter_by(
            project_id=int(project_id),
            status="active",
        )
        if exclude_script_id:
            query = query.filter(UiAutomationScript.id != int(exclude_script_id))
        candidates = query.order_by(
            UiAutomationScript.updated_at.desc(),
            UiAutomationScript.id.desc(),
        ).all()
        login_script = next(
            (
                item for item in candidates
                if UiAutomationService._is_login_script(
                    item.name,
                    item.code,
                    item.tags,
                )
            ),
            None,
        )
        if not login_script:
            if required:
                raise ServiceError("当前项目没有启用的用户登录前置脚本，请先录入登录脚本。")
            return None
        return {
            "type": "script",
            "role": "login_precondition",
            "script_id": login_script.id,
            "script_code": login_script.code,
        }

    @staticmethod
    def _normalize_script_dependencies(
        project_id,
        dependencies=None,
        require_login=True,
        exclude_script_id=None,
        is_login_script=False,
    ):
        normalized = []
        for item in dependencies or []:
            if isinstance(item, int) or (isinstance(item, str) and item.isdigit()):
                item = {"type": "script", "script_id": int(item)}
            if not isinstance(item, dict):
                continue
            try:
                dependency_script_id = int(item.get("script_id") or item.get("scriptId"))
            except (TypeError, ValueError):
                continue
            dependency_script = db.session.get(UiAutomationScript, dependency_script_id)
            if (
                not dependency_script
                or dependency_script.project_id != int(project_id)
                or dependency_script.id == exclude_script_id
            ):
                continue
            normalized.append(
                {
                    "type": "script",
                    "role": str(item.get("role") or "precondition").strip(),
                    "script_id": dependency_script.id,
                    "script_code": dependency_script.code,
                }
            )

        if require_login and not is_login_script:
            login_dependency = UiAutomationService.default_login_dependency(
                project_id,
                exclude_script_id=exclude_script_id,
                required=True,
            )
            normalized = [
                item for item in normalized
                if item.get("role") != "login_precondition"
            ]
            normalized.insert(0, login_dependency)
        elif is_login_script:
            normalized = [
                item for item in normalized
                if item.get("role") != "login_precondition"
            ]
        return normalized

    @staticmethod
    def create_script(
        project_id,
        name,
        code,
        description="",
        language="python",
        framework="playwright",
        status="draft",
        tags_text="",
        entry_file="",
        script_content="",
        owner_id=None,
        created_by=None,
        dependencies=None,
        require_login=True,
    ):
        project_id = int(ensure_not_blank(project_id, "所属项目"))
        name = ensure_not_blank(name, "脚本名称")
        code = ensure_not_blank(code, "脚本编码").lower()
        description = str(description or "").strip()
        language = str(language or "python").strip().lower()
        framework = str(framework or "playwright").strip().lower()
        status = str(status or "draft").strip().lower()
        entry_file = str(entry_file or "").strip()
        script_content = ensure_not_blank(script_content, "脚本内容")

        exists = UiAutomationScript.query.filter_by(project_id=project_id, code=code).first()
        if exists:
            raise ServiceError("同一项目下脚本编码已存在。")

        script = UiAutomationScript(
            project_id=project_id,
            name=name,
            code=code,
            description=description,
            language=language,
            framework=framework,
            status=status,
            entry_file=entry_file,
            owner_id=owner_id,
        )
        script.tags = UiAutomationService._normalize_tags(tags_text)
        db.session.add(script)
        db.session.flush()
        initial_change_summary = UiAutomationService.sanitize_change_summary("\u9996\u7248\u521b\u5efa", fallback="\u9996\u7248\u521b\u5efa")

        version = UiAutomationScriptVersion(
            script_id=script.id,
            version_no=1,
            change_summary="首版创建",
            script_content=script_content,
            ai_generated=False,
            ai_prompt="",
            created_by=created_by,
        )
        version.dependencies = UiAutomationService._normalize_script_dependencies(
            project_id,
            dependencies=dependencies,
            require_login=bool(require_login),
            exclude_script_id=script.id,
            is_login_script=(
                not bool(require_login)
                or UiAutomationService._is_login_script(
                script.name,
                script.code,
                script.tags,
                )
            ),
        )
        version.change_summary = initial_change_summary
        db.session.add(version)
        db.session.flush()

        script.current_version_id = version.id
        commit_session()
        return script

    @staticmethod
    def update_script(
        script_id,
        name,
        code,
        description="",
        language="python",
        framework="playwright",
        status="draft",
        tags_text="",
        entry_file="",
        script_content="",
        owner_id=None,
        created_by=None,
        change_summary="内容更新",
        dependencies=None,
        require_login=None,
    ):
        script = UiAutomationService.get_script_by_id(script_id)
        name = ensure_not_blank(name, "脚本名称")
        code = ensure_not_blank(code, "脚本编码").lower()
        description = str(description or "").strip()
        language = str(language or "python").strip().lower()
        framework = str(framework or "playwright").strip().lower()
        status = str(status or "draft").strip().lower()
        entry_file = str(entry_file or "").strip()
        script_content = ensure_not_blank(script_content, "脚本内容")

        exists = UiAutomationScript.query.filter(
            UiAutomationScript.project_id == script.project_id,
            UiAutomationScript.code == code,
            UiAutomationScript.id != script.id,
        ).first()
        if exists:
            raise ServiceError("同一项目下脚本编码已存在。")

        script.name = name
        script.code = code
        script.description = description
        script.language = language
        script.framework = framework
        script.status = status
        script.entry_file = entry_file
        script.owner_id = owner_id
        script.tags = UiAutomationService._normalize_tags(tags_text)
        change_summary = UiAutomationService.sanitize_change_summary(
            change_summary,
            fallback=UiAutomationService.CHANGE_SUMMARY_FALLBACK,
        )

        current_version = UiAutomationService._get_latest_script_version(script)
        current_dependencies = current_version.dependencies if current_version else []
        effective_dependencies = current_dependencies if dependencies is None else dependencies
        is_login_script = UiAutomationService._is_login_script(
            script.name,
            script.code,
            script.tags,
        )
        if require_login is False:
            is_login_script = True
        if require_login is None:
            require_login = bool(
                not is_login_script
                and any(
                    item.get("role") == "login_precondition"
                    for item in current_dependencies
                    if isinstance(item, dict)
                )
            )

        next_version_no = UiAutomationService._next_version_no(script.id)
        version = UiAutomationScriptVersion(
            script_id=script.id,
            version_no=next_version_no,
            change_summary=str(change_summary or "内容更新").strip(),
            script_content=script_content,
            ai_generated=False,
            ai_prompt="",
            created_by=created_by,
        )
        version.dependencies = UiAutomationService._normalize_script_dependencies(
            script.project_id,
            dependencies=effective_dependencies,
            require_login=bool(require_login),
            exclude_script_id=script.id,
            is_login_script=is_login_script,
        )
        db.session.add(version)
        db.session.flush()
        script.current_version_id = version.id
        commit_session()
        return script

    @staticmethod
    def delete_script(script_id):
        script = UiAutomationService.get_script_by_id(script_id)
        db.session.delete(script)
        commit_session()
        return True

    @staticmethod
    def list_script_versions(script_id):
        return (
            UiAutomationScriptVersion.query.filter_by(script_id=script_id)
            .order_by(UiAutomationScriptVersion.version_no.desc())
            .all()
        )

    @staticmethod
    def list_script_runs(script_id, limit=10):
        query = UiAutomationRun.query.filter_by(script_id=script_id).order_by(
            UiAutomationRun.created_at.desc(),
            UiAutomationRun.id.desc(),
        )
        if limit:
            query = query.limit(limit)
        return query.all()

    @staticmethod
    def list_scripts_with_relations(project_id=None, project_ids=None):
        query = UiAutomationScript.query.options(
            selectinload(UiAutomationScript.owner),
            selectinload(UiAutomationScript.versions),
        )
        if project_id:
            query = query.filter_by(project_id=project_id)
        elif project_ids:
            query = query.filter(UiAutomationScript.project_id.in_(project_ids))
        return query.order_by(UiAutomationScript.updated_at.desc(), UiAutomationScript.id.desc()).all()

    @staticmethod
    def list_recent_runs_by_script_ids(script_ids, limit_per_script=5):
        normalized_ids = []
        for script_id in script_ids or []:
            try:
                normalized_id = int(script_id)
            except (TypeError, ValueError):
                continue
            if normalized_id > 0 and normalized_id not in normalized_ids:
                normalized_ids.append(normalized_id)

        if not normalized_ids:
            return {}

        runs = (
            UiAutomationRun.query.options(selectinload(UiAutomationRun.environment))
            .filter(UiAutomationRun.script_id.in_(normalized_ids))
            .order_by(
                UiAutomationRun.script_id.asc(),
                UiAutomationRun.created_at.desc(),
                UiAutomationRun.id.desc(),
            )
            .all()
        )

        run_map = {script_id: [] for script_id in normalized_ids}
        for run in runs:
            script_runs = run_map.setdefault(run.script_id, [])
            if len(script_runs) >= limit_per_script:
                continue
            script_runs.append(run)
        return run_map

    @staticmethod
    def get_script_version_by_id(version_id):
        version = db.session.get(UiAutomationScriptVersion, version_id)
        if not version:
            raise ServiceError("脚本版本不存在。")
        return version

    @staticmethod
    def restore_script_version(script_id, version_id, created_by=None, change_summary="版本回滚"):
        script = UiAutomationService.get_script_by_id(script_id)
        source_version = UiAutomationService.get_script_version_by_id(version_id)
        if source_version.script_id != script.id:
            raise ServiceError("脚本版本不属于当前脚本。")

        next_version_no = UiAutomationService._next_version_no(script.id)
        version = UiAutomationScriptVersion(
            script_id=script.id,
            version_no=next_version_no,
            change_summary=str(change_summary or f"回滚到 v{source_version.version_no}").strip(),
            script_content=source_version.script_content,
            dependencies_json=source_version.dependencies_json,
            locator_snapshot_json=source_version.locator_snapshot_json,
            ai_generated=False,
            ai_prompt="",
            created_by=created_by,
        )
        db.session.add(version)
        db.session.flush()
        script.current_version_id = version.id
        commit_session()
        return version

    @staticmethod
    def list_locators(project_id=None, project_ids=None):
        query = UiAutomationLocator.query
        if project_id:
            query = query.filter_by(project_id=project_id)
        elif project_ids:
            query = query.filter(UiAutomationLocator.project_id.in_(project_ids))
        return query.order_by(UiAutomationLocator.updated_at.desc(), UiAutomationLocator.id.desc()).all()

    @staticmethod
    def _get_latest_script_version(script):
        if not script:
            return None
        if script.current_version_id:
            current_version = (
                UiAutomationScriptVersion.query.filter_by(id=script.current_version_id, script_id=script.id)
                .first()
            )
            if current_version:
                return current_version
        if script.versions:
            return script.versions[0]
        return None

    @staticmethod
    def _collect_script_content(project_id=None, project_ids=None):
        scripts = UiAutomationService.list_scripts(project_id=project_id, project_ids=project_ids)
        payload = []
        for script in scripts:
            version = UiAutomationService._get_latest_script_version(script)
            payload.append(
                {
                    "script": script,
                    "version": version,
                    "content": version.script_content if version else "",
                }
            )
        return payload

    @staticmethod
    def build_locator_usage_map(project_id=None, project_ids=None):
        locators = UiAutomationService.list_locators(project_id=project_id, project_ids=project_ids)
        script_payload = UiAutomationService._collect_script_content(project_id=project_id, project_ids=project_ids)
        usage_map = {
            locator.locator_code: {
                "usage_count": 0,
                "scripts": [],
                "matched_by": [],
            }
            for locator in locators
        }
        duplicate_groups = defaultdict(list)

        for locator in locators:
            duplicate_key = (locator.locator_type or "css", (locator.locator_value or "").strip())
            duplicate_groups[duplicate_key].append(locator)

        for item in script_payload:
            script = item["script"]
            content = item["content"] or ""
            lowered_content = content.lower()
            for locator in locators:
                code = locator.locator_code
                code_hit = code.lower() in lowered_content
                value_hit = False
                locator_value = (locator.locator_value or "").strip()
                if locator_value:
                    locator_value_norm = locator_value.lower()
                    value_hit = locator_value_norm in lowered_content
                if not code_hit and not value_hit:
                    continue
                entry = usage_map[code]
                entry["usage_count"] += 1
                entry["scripts"].append(
                    {
                        "id": script.id,
                        "name": script.name,
                        "code": script.code,
                    }
                )
                entry["matched_by"].append("code" if code_hit else "value")

        duplicate_candidates = []
        for (_, _), items in duplicate_groups.items():
            if len(items) > 1:
                duplicate_candidates.append(items)

        total_used = sum(1 for item in usage_map.values() if item["usage_count"] > 0)
        total_unused = max(len(locators) - total_used, 0)

        top_used = sorted(
            [
                {
                    "locator_code": locator.locator_code,
                    "locator_name": locator.locator_name,
                    "usage_count": usage_map[locator.locator_code]["usage_count"],
                    "scripts": usage_map[locator.locator_code]["scripts"],
                }
                for locator in locators
            ],
            key=lambda item: (-item["usage_count"], item["locator_code"]),
        )[:8]

        duplicate_preview = [
            {
                "locator_type": items[0].locator_type,
                "locator_value": items[0].locator_value,
                "items": [
                    {
                        "id": locator.id,
                        "locator_code": locator.locator_code,
                        "locator_name": locator.locator_name,
                        "page_name": locator.page_name,
                        "status": locator.status,
                    }
                    for locator in items
                ],
            }
            for items in duplicate_candidates[:8]
        ]

        return {
            "usage_map": usage_map,
            "top_used": top_used,
            "duplicate_candidates": duplicate_preview,
            "summary": {
                "used": total_used,
                "unused": total_unused,
                "duplicates": sum(max(len(items) - 1, 0) for items in duplicate_candidates),
                "script_count": len(script_payload),
            },
        }

    @staticmethod
    def export_locators(project_id=None, project_ids=None):
        locators = UiAutomationService.list_locators(project_id=project_id, project_ids=project_ids)
        return [UiAutomationService.serialize_locator(locator) for locator in locators]

    @staticmethod
    def batch_import_locators(project_id, items, created_by=None):
        project_id = int(ensure_not_blank(project_id, "所属项目"))
        if not db.session.get(Project, project_id):
            raise ServiceError("所属项目不存在。")
        if not isinstance(items, list) or not items:
            raise ServiceError("批量导入内容不能为空。")

        created_locators = []
        errors = []
        used_codes = {
            item.locator_code
            for item in UiAutomationLocator.query.filter_by(project_id=project_id).all()
        }

        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                errors.append(f"第 {index} 项不是有效对象。")
                continue

            locator_name = str(item.get("locator_name") or item.get("name") or "").strip()
            locator_code = str(item.get("locator_code") or item.get("code") or "").strip().lower()
            if not locator_name:
                locator_name = f"导入定位器 {index}"
            if not locator_code:
                locator_code = UiAutomationService._normalize_locator_code(locator_name)
            base_code = locator_code
            suffix = 2
            while locator_code in used_codes:
                locator_code = f"{base_code}_{suffix}"
                suffix += 1
            used_codes.add(locator_code)

            locator_type = str(item.get("locator_type") or item.get("type") or "css").strip().lower()
            locator_value = str(item.get("locator_value") or item.get("value") or "").strip()
            if not locator_value:
                errors.append(f"第 {index} 项缺少定位器值。")
                continue

            page_name = str(item.get("page_name") or item.get("pageName") or "").strip()
            page_url_pattern = str(item.get("page_url_pattern") or item.get("url_pattern") or "").strip()
            description = str(item.get("description") or "").strip()
            usage_scene = str(item.get("usage_scene") or item.get("scene") or "").strip()
            is_stable = item.get("is_stable", item.get("stable", True))
            if isinstance(is_stable, str):
                is_stable = is_stable.strip().lower() in {"1", "true", "yes", "y"}
            status = str(item.get("status") or "active").strip().lower()

            try:
                locator = UiAutomationService.create_locator(
                    project_id=project_id,
                    locator_name=locator_name,
                    locator_code=locator_code,
                    locator_type=locator_type,
                    locator_value=locator_value,
                    page_name=page_name,
                    page_url_pattern=page_url_pattern,
                    description=description,
                    usage_scene=usage_scene,
                    is_stable=bool(is_stable),
                    status=status,
                    created_by=created_by,
                )
                created_locators.append(locator)
            except ServiceError as exc:
                errors.append(f"第 {index} 项：{exc}")

        return {
            "created_locators": created_locators,
            "errors": errors,
        }

    @staticmethod
    def bulk_update_locators(locator_ids, action, updated_by=None):
        valid_ids = []
        for item in locator_ids or []:
            try:
                valid_ids.append(int(item))
            except (TypeError, ValueError):
                continue

        if not valid_ids:
            raise ServiceError("请先选择要操作的定位器。")

        locators = UiAutomationLocator.query.filter(UiAutomationLocator.id.in_(valid_ids)).all()
        if not locators:
            raise ServiceError("未找到可操作的定位器。")

        action = str(action or "").strip().lower()
        if action not in {"activate", "deprecate", "stable", "unstable", "delete"}:
            raise ServiceError("不支持的批量操作。")

        if action == "delete":
            for locator in locators:
                db.session.delete(locator)
            commit_session()
            return {"updated_count": len(locators), "deleted_count": len(locators)}

        updated_count = 0
        for locator in locators:
            if action == "activate":
                locator.status = "active"
            elif action == "deprecate":
                locator.status = "deprecated"
            elif action == "stable":
                locator.is_stable = True
            elif action == "unstable":
                locator.is_stable = False
            locator.updated_by = updated_by
            updated_count += 1

        commit_session()
        return {"updated_count": updated_count, "deleted_count": 0}

    @staticmethod
    def get_locator_by_id(locator_id):
        locator = db.session.get(UiAutomationLocator, locator_id)
        if not locator:
            raise ServiceError("定位器不存在。")
        return locator

    @staticmethod
    def create_locator(
        project_id,
        locator_name,
        locator_code,
        locator_type,
        locator_value,
        page_name="",
        page_url_pattern="",
        description="",
        usage_scene="",
        is_stable=True,
        status="active",
        created_by=None,
    ):
        project_id = int(ensure_not_blank(project_id, "所属项目"))
        if not db.session.get(Project, project_id):
            raise ServiceError("所属项目不存在。")

        locator_name = ensure_not_blank(locator_name, "定位器名称")
        locator_code = ensure_not_blank(locator_code, "定位器编码").lower()
        locator_type = str(locator_type or "css").strip().lower()
        locator_value = ensure_not_blank(locator_value, "定位器值")
        status = str(status or "active").strip().lower()

        if locator_type not in {"role", "label", "placeholder", "text", "testid", "css", "xpath", "custom"}:
            raise ServiceError("不支持的定位器类型。")
        if status not in {"active", "deprecated"}:
            raise ServiceError("不支持的定位器状态。")
        if UiAutomationLocator.query.filter_by(project_id=project_id, locator_code=locator_code).first():
            raise ServiceError("同一项目下定位器编码已存在。")

        locator = UiAutomationLocator(
            project_id=project_id,
            page_name=str(page_name or "").strip(),
            page_url_pattern=str(page_url_pattern or "").strip(),
            locator_name=locator_name,
            locator_code=locator_code,
            locator_type=locator_type,
            locator_value=locator_value,
            description=str(description or "").strip(),
            usage_scene=str(usage_scene or "").strip(),
            is_stable=bool(is_stable),
            status=status,
            created_by=created_by,
            updated_by=created_by,
        )
        db.session.add(locator)
        commit_session()
        return locator

    @staticmethod
    def update_locator(
        locator_id,
        locator_name,
        locator_code,
        locator_type,
        locator_value,
        page_name="",
        page_url_pattern="",
        description="",
        usage_scene="",
        is_stable=True,
        status="active",
        updated_by=None,
    ):
        locator = UiAutomationService.get_locator_by_id(locator_id)
        locator_name = ensure_not_blank(locator_name, "定位器名称")
        locator_code = ensure_not_blank(locator_code, "定位器编码").lower()
        locator_type = str(locator_type or "css").strip().lower()
        locator_value = ensure_not_blank(locator_value, "定位器值")
        status = str(status or "active").strip().lower()

        if locator_type not in {"role", "label", "placeholder", "text", "testid", "css", "xpath", "custom"}:
            raise ServiceError("不支持的定位器类型。")
        if status not in {"active", "deprecated"}:
            raise ServiceError("不支持的定位器状态。")

        exists = UiAutomationLocator.query.filter(
            UiAutomationLocator.project_id == locator.project_id,
            UiAutomationLocator.locator_code == locator_code,
            UiAutomationLocator.id != locator.id,
        ).first()
        if exists:
            raise ServiceError("同一项目下定位器编码已存在。")

        locator.locator_name = locator_name
        locator.locator_code = locator_code
        locator.locator_type = locator_type
        locator.locator_value = locator_value
        locator.page_name = str(page_name or "").strip()
        locator.page_url_pattern = str(page_url_pattern or "").strip()
        locator.description = str(description or "").strip()
        locator.usage_scene = str(usage_scene or "").strip()
        locator.is_stable = bool(is_stable)
        locator.status = status
        locator.updated_by = updated_by
        commit_session()
        return locator

    @staticmethod
    def delete_locator(locator_id):
        locator = UiAutomationService.get_locator_by_id(locator_id)
        db.session.delete(locator)
        commit_session()
        return True

    @staticmethod
    def _build_failure_analysis(status, error_message="", target_step=None):
        normalized_status = str(status or "").strip().lower()
        step_error = str(target_step.error_message or "").strip() if target_step else ""
        error_message = step_error or str(error_message or "").strip()

        if normalized_status in {"queued", "pending", "running"}:
            status_labels = {
                "queued": "排队中",
                "pending": "等待执行",
                "running": "执行中",
            }
            return {
                "has_failure": False,
                "category": normalized_status,
                "category_label": status_labels[normalized_status],
                "summary": "",
                "root_cause": "",
                "suggestion": "",
                "step_index": target_step.step_index if target_step else None,
                "step_title": target_step.step_title if target_step else "",
                "step_type": target_step.step_type if target_step else "",
                "locator": target_step.locator if target_step else "",
                "match_count": None,
                "error_message": error_message,
            }

        if normalized_status == "passed":
            return {
                "has_failure": False,
                "category": "passed",
                "category_label": "已通过",
                "summary": "本次执行已通过。",
                "root_cause": "本次执行成功，没有失败根因。",
                "suggestion": "无需修复。",
                "step_index": target_step.step_index if target_step else None,
                "step_title": target_step.step_title if target_step else "",
                "step_type": target_step.step_type if target_step else "",
                "locator": target_step.locator if target_step else "",
                "match_count": None,
                "error_message": error_message,
            }

        locator_text = str(target_step.locator or "").strip() if target_step else ""
        step_title = target_step.step_title if target_step else ""
        step_type = target_step.step_type if target_step else ""

        analysis_text = " ".join([error_message, locator_text, step_title, step_type])

        def _has(*keywords):
            text = analysis_text.lower()
            return any(keyword.lower() in text for keyword in keywords)

        resolved_match = re.search(r"resolved to\s+(\d+)\s+elements?", analysis_text, re.IGNORECASE)
        match_count = int(resolved_match.group(1)) if resolved_match else None

        if normalized_status == "timeout":
            category = "timeout"
            category_label = "执行超时"
            root_cause = "执行在限定时间内没有完成，通常是页面等待、接口返回或脚本步骤阻塞导致。"
            suggestion = "优先检查超时前最后一个步骤、页面网络状态和等待条件，必要时适当放宽超时配置。"
        elif _has("strict mode violation", "strict mode") or (match_count is not None and match_count > 1):
            category = "locator_not_unique"
            category_label = "元素不唯一"
            root_cause = (
                f"当前 XPath 同时命中了 {match_count} 个元素，Playwright 严格模式无法确定要操作哪一个。"
                if match_count is not None
                else "当前 XPath 命中了多个元素，Playwright 严格模式无法确定要操作哪一个。"
            )
            suggestion = "结合失败截图和页面结构收窄 XPath，增加稳定的父级、文本或属性条件，确保只命中一个目标元素。"
        elif _has(
            "element(s) not found",
            "element not found",
            "no element found",
            "resolved to 0 elements",
            "actual value: none",
        ) or (_has("waiting for locator") and _has("timed out", "timeout")):
            category = "locator_not_found"
            category_label = "元素定位不到"
            match_count = 0
            root_cause = "当前 XPath 在限定时间内没有命中目标元素，可能是页面文案、结构、属性或加载时机发生了变化。"
            suggestion = "结合失败截图确认目标元素当前状态，并按实际页面更新 XPath；如元素延迟出现，再补充明确的等待条件。"
        elif _has("assert", "expect", "to_be_", "to_have_", "not.to_", "visible", "hidden"):
            category = "assertion"
            category_label = "断言失败"
            root_cause = "脚本断言结果与页面实际状态不一致，通常是页面文案、结构或数据状态发生变化。"
            suggestion = "先核对失败步骤截图与日志，再让 AI 按当前页面状态修复断言或等待条件。"
        elif _has("timed out", "timeout", "??"):
            category = "timeout"
            category_label = "执行超时"
            root_cause = "执行在限定时间内没有完成，通常是页面等待、接口返回或脚本步骤阻塞导致。"
            suggestion = "优先检查超时前最后一个步骤、页面网络状态和等待条件，必要时适当放宽超时配置。"
        elif _has("locator", "waiting for", "strict mode", "element", "selector", "???", "???"):
            category = "locator"
            category_label = "定位器异常"
            root_cause = "当前定位器没有稳定命中目标元素，可能是页面结构、属性或可见状态发生了变化。"
            suggestion = "结合失败截图和页面结构检查 XPath，确保定位条件稳定且只命中目标元素。"
        elif _has("navigation", "goto", "load", "network", "??"):
            category = "navigation"
            category_label = "页面跳转异常"
            root_cause = "页面打开、跳转或资源加载过程异常，通常与地址配置、网络波动或页面加载事件有关。"
            suggestion = "检查 base_url、路由跳转、网络请求和 wait_for_load_state 等等待条件是否合理。"
        else:
            category = "script"
            category_label = "脚本执行异常"
            root_cause = error_message or "执行过程中出现了未归类的异常。"
            suggestion = "结合运行日志和步骤明细，优先让 AI 根据失败步骤做一次脚本修复。"

        summary_parts = [category_label]
        if step_title:
            summary_parts.append(f"失败步骤：{step_title}")
        if category == "locator_not_unique" and match_count is not None:
            summary_parts.append(f"命中 {match_count} 个元素")

        return {
            "has_failure": True,
            "category": category,
            "category_label": category_label,
            "summary": "；".join(summary_parts),
            "root_cause": root_cause,
            "suggestion": suggestion,
            "step_index": target_step.step_index if target_step else None,
            "step_title": step_title,
            "step_type": step_type,
            "locator": locator_text,
            "match_count": match_count,
            "error_message": error_message,
        }

    @staticmethod
    def analyze_step_failure(step):
        if not step:
            raise ServiceError("UI 执行步骤不存在。")
        return UiAutomationService._build_failure_analysis(
            step.status,
            error_message=step.error_message,
            target_step=step,
        )

    @staticmethod
    def analyze_run_failure(run):
        if not run:
            raise ServiceError("UI 执行记录不存在。")

        steps = list(run.steps or [])
        failed_step = next((step for step in steps if step.status == "failed"), None)
        last_step = steps[-1] if steps else None
        target_step = failed_step or last_step
        return UiAutomationService._build_failure_analysis(
            run.status,
            error_message=run.error_message,
            target_step=target_step,
        )

    @staticmethod
    def build_locator_context(project_id=None, project_ids=None):
        locators = UiAutomationService.list_locators(project_id=project_id, project_ids=project_ids)
        return [
            {
                "code": locator.locator_code,
                "name": locator.locator_name,
                "page": locator.page_name,
                "url_pattern": locator.page_url_pattern,
                "type": locator.locator_type,
                "value": locator.locator_value,
                "usage_scene": locator.usage_scene,
                "stable": locator.is_stable,
                "status": locator.status,
            }
            for locator in locators
            if locator.status == "active"
        ]

    @staticmethod
    def list_environments(project_id=None, project_ids=None):
        query = UiAutomationEnvironment.query
        if project_id:
            query = query.filter_by(project_id=project_id)
        elif project_ids:
            query = query.filter(UiAutomationEnvironment.project_id.in_(project_ids))
        return query.order_by(UiAutomationEnvironment.updated_at.desc(), UiAutomationEnvironment.id.desc()).all()

    @staticmethod
    def create_environment(project_id, name, base_url, browser_default="chromium", headless_default=True, timeout_ms=30000, retry_times=0, viewport_width=1440, viewport_height=900, storage_state_path="", proxy_config=None, runtime_variables=None, status="active", description=""):
        project_id = int(ensure_not_blank(project_id, "project"))
        if not db.session.get(Project, project_id):
            raise ServiceError("Project not found.")
        name = ensure_not_blank(name, "environment name")
        if UiAutomationEnvironment.query.filter_by(project_id=project_id, name=name).first():
            raise ServiceError("An environment with that name already exists.")
        environment = UiAutomationEnvironment(
            project_id=project_id, name=name, base_url=ensure_not_blank(base_url, "base URL"),
            browser_default=str(browser_default or "chromium").strip().lower(), headless_default=bool(headless_default),
            timeout_ms=int(timeout_ms or 30000), retry_times=int(retry_times or 0), viewport_width=int(viewport_width or 1440), viewport_height=int(viewport_height or 900),
            storage_state_path=str(storage_state_path or "").strip(), status=str(status or "active").strip().lower(), description=str(description or "").strip(),
        )
        environment.proxy_config = proxy_config if isinstance(proxy_config, dict) else {}
        environment.runtime_variables = runtime_variables if isinstance(runtime_variables, dict) else {}
        db.session.add(environment)
        commit_session()
        return environment

    @staticmethod
    def update_environment(environment_id, **payload):
        environment = db.session.get(UiAutomationEnvironment, int(environment_id))
        if not environment:
            raise ServiceError("Environment not found.")
        name = ensure_not_blank(payload.get("name"), "environment name")
        duplicate = UiAutomationEnvironment.query.filter(
            UiAutomationEnvironment.project_id == environment.project_id,
            UiAutomationEnvironment.name == name,
            UiAutomationEnvironment.id != environment.id,
        ).first()
        if duplicate:
            raise ServiceError("An environment with that name already exists.")
        environment.name, environment.base_url = name, ensure_not_blank(payload.get("base_url"), "base URL")
        for field, default in (("browser_default", "chromium"), ("headless_default", True), ("timeout_ms", 30000), ("retry_times", 0), ("viewport_width", 1440), ("viewport_height", 900), ("storage_state_path", ""), ("status", "active"), ("description", "")):
            value = payload.get(field, getattr(environment, field, default))
            if field in {"timeout_ms", "retry_times", "viewport_width", "viewport_height"}:
                value = int(value or default)
            elif field == "headless_default":
                value = bool(value)
            elif field in {"browser_default", "status", "storage_state_path", "description"}:
                value = str(value or default).strip()
            setattr(environment, field, value)
        environment.proxy_config = payload.get("proxy_config") if isinstance(payload.get("proxy_config"), dict) else environment.proxy_config
        environment.runtime_variables = payload.get("runtime_variables") if isinstance(payload.get("runtime_variables"), dict) else environment.runtime_variables
        commit_session()
        return environment

    @staticmethod
    def delete_environment(environment_id):
        environment = db.session.get(UiAutomationEnvironment, int(environment_id))
        if not environment:
            raise ServiceError("Environment not found.")
        db.session.delete(environment)
        commit_session()
        return True

    @staticmethod
    def list_runs(project_id=None, project_ids=None):
        query = UiAutomationRun.query
        if project_id:
            query = query.filter_by(project_id=project_id)
        elif project_ids:
            query = query.filter(UiAutomationRun.project_id.in_(project_ids))
        return query.order_by(UiAutomationRun.created_at.desc(), UiAutomationRun.id.desc()).all()

    @staticmethod
    def list_artifacts(run_id):
        return UiAutomationArtifact.query.filter_by(run_id=run_id).order_by(UiAutomationArtifact.created_at.asc()).all()

    @staticmethod
    def list_artifacts_by_run_ids(run_ids):
        normalized_ids = []
        for run_id in run_ids or []:
            try:
                normalized_id = int(run_id)
            except (TypeError, ValueError):
                continue
            if normalized_id > 0 and normalized_id not in normalized_ids:
                normalized_ids.append(normalized_id)

        if not normalized_ids:
            return {}

        artifacts = (
            UiAutomationArtifact.query
            .filter(UiAutomationArtifact.run_id.in_(normalized_ids))
            .order_by(UiAutomationArtifact.run_id.asc(), UiAutomationArtifact.created_at.asc())
            .all()
        )

        artifact_map = {run_id: [] for run_id in normalized_ids}
        for artifact in artifacts:
            artifact_map.setdefault(artifact.run_id, []).append(artifact)
        return artifact_map

    @staticmethod
    def list_run_steps(run_id):
        return UiAutomationRunStep.query.filter_by(run_id=run_id).order_by(UiAutomationRunStep.step_index.asc()).all()

    @staticmethod
    def get_execution_context(project_id=None, project_ids=None):
        scripts = UiAutomationService.list_scripts(project_id=project_id, project_ids=project_ids)
        environments = UiAutomationService.list_environments(project_id=project_id, project_ids=project_ids)
        runs = UiAutomationService.list_runs(project_id=project_id, project_ids=project_ids)[:20]
        projects = []
        if project_id:
            project = db.session.get(Project, project_id)
            projects = [project] if project else []
        elif project_ids:
            projects = Project.query.filter(Project.id.in_(project_ids)).order_by(Project.created_at.desc()).all()
        return {
            "scripts": scripts,
            "environments": environments,
            "runs": runs,
            "projects": projects,
        }

    @staticmethod
    def create_run(
        project_id,
        script_id,
        environment_id=None,
        browser_type="chromium",
        run_mode="manual",
        trigger_type="automatic",
        max_retry=0,
        run_timeout_seconds=None,
        trigger_source="ui",
        trigger_user_id=None,
    ):
        project_id = int(ensure_not_blank(project_id, "所属项目"))
        try:
            script_id = int(ensure_not_blank(script_id, "脚本").strip())
        except (TypeError, ValueError):
            raise ServiceError("脚本ID不合法。")
        if environment_id not in (None, ""):
            try:
                environment_id = int(environment_id)
            except (TypeError, ValueError):
                raise ServiceError("环境ID不合法。")
        project = db.session.get(Project, project_id)
        if not project:
            raise ServiceError("所属项目不存在。")

        script = db.session.get(UiAutomationScript, script_id)
        if not script or script.project_id != project.id:
            raise ServiceError("脚本不存在或不属于当前项目。")

        environment = None
        if environment_id:
            environment = db.session.get(UiAutomationEnvironment, environment_id)
            if not environment or environment.project_id != project.id:
                raise ServiceError("环境不存在或不属于当前项目。")

        version = None
        if script.current_version_id:
            version = db.session.get(UiAutomationScriptVersion, script.current_version_id)
        if not version:
            version = (
                UiAutomationScriptVersion.query.filter_by(script_id=script.id)
                .order_by(UiAutomationScriptVersion.version_no.desc())
                .first()
            )
        if not version:
            raise ServiceError("脚本缺少可执行版本。")

        run = UiAutomationRun(
            project_id=project.id,
            script_id=script.id,
            script_version_id=version.id,
            environment_id=environment.id if environment else None,
            browser_type=str(browser_type or "chromium").strip().lower(),
            run_mode=str(run_mode or "manual").strip().lower(),
            trigger_type=normalize_trigger_type(trigger_type),
            status="queued",
            max_retry=int(max_retry or 0),
            trigger_user_id=trigger_user_id,
            trigger_source=str(trigger_source or "ui").strip().lower(),
        )
        db.session.add(run)
        db.session.flush()
        run.summary = {
            "script_name": script.name,
            "script_code": script.code,
            "script_version": version.version_no,
            "environment_name": environment.name if environment else "",
            "environment_base_url": environment.base_url if environment else "",
            "browser_type": run.browser_type,
            "run_mode": run.run_mode,
            "trigger_type": run.trigger_type,
            "trigger_person": run.trigger_person_name,
            "preconditions": version.dependencies,
        }
        if run_timeout_seconds not in (None, ""):
            try:
                timeout_value = int(run_timeout_seconds)
            except (TypeError, ValueError):
                raise ServiceError("执行超时时长不合法。")
            if timeout_value < 30 or timeout_value > 3600:
                raise ServiceError("执行超时时长需在 30 到 3600 秒之间。")
            summary = dict(run.summary or {})
            summary["configured_timeout_seconds"] = timeout_value
            summary["timeout_source"] = "run"
            run.summary = summary
        commit_session()
        return run
