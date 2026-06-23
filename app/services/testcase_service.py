import math
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import joinedload

from app import db
from app.models import Module, Project, TestCase
from app.services.base_service import (
    ServiceError,
    commit_session,
    ensure_choice,
    ensure_not_blank,
    parse_json_text,
    validate_case_schema,
)


@dataclass
class InterfaceGroup:
    module: Module
    project: Project
    method: str
    url: str
    feature_name: str = ""
    testcases: list[TestCase] = field(default_factory=list)
    active_count: int = 0
    inactive_count: int = 0
    ai_count: int = 0
    manual_count: int = 0
    latest_created_at: object = None


@dataclass
class ModuleGroup:
    module: Module
    project: Project
    endpoint_groups: list[InterfaceGroup] = field(default_factory=list)
    total_endpoint_count: int = 0
    total_testcase_count: int = 0
    displayed_endpoint_count: int = 0
    displayed_testcase_count: int = 0
    latest_created_at: object = None


class GroupedPagination:
    def __init__(self, items, page, per_page, total):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total

    @property
    def pages(self):
        if not self.total:
            return 0
        return math.ceil(self.total / self.per_page)

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def prev_num(self):
        if not self.has_prev:
            return None
        return self.page - 1

    @property
    def next_num(self):
        if not self.has_next:
            return None
        return self.page + 1

    def iter_pages(self, left_edge=2, left_current=2, right_current=5, right_edge=2):
        last = 0
        for num in range(1, self.pages + 1):
            if (
                num <= left_edge
                or (self.page - left_current - 1 < num < self.page + right_current)
                or num > self.pages - right_edge
            ):
                if last + 1 != num:
                    yield None
                yield num
                last = num


class TestCaseService:
    # 约束：
    # 列表页接口功能名必须由后端统一解析并传给模板，模板里不再维护中文映射表。
    # 这样可以避免因为文件编码或手工误改，把中文展示名写成问号。
    _FEATURE_NAME_RULES = [
        ("/material_folder/get_tree", "素材文件夹目录树查询接口"),
        ("/material_folder/create", "素材文件夹新建文件夹接口"),
        ("/material_folder/update", "素材文件夹编辑文件夹接口"),
        ("/material_folder/get_detail", "素材文件夹文件夹详情接口"),
        ("/material_folder/delete", "素材文件夹删除文件夹接口"),
        ("/material/get_material_list", "素材库列表查询接口"),
        ("/material_tag/get_category_list", "素材标签获取分类列表接口"),
        ("/material_tag/save_category", "素材标签保存分类接口"),
        ("/material_tag/update_category_status", "素材标签更新分类状态接口"),
        ("/material_tag/get_tag_list", "素材标签获取标签列表接口"),
        ("/material_tag/save_tag", "素材标签保存标签接口"),
        ("/material_tag/batch_create_tag", "素材标签批量新增标签接口"),
        ("/material_tag/batch_update_tag_status", "素材标签批量更新标签状态接口"),
        ("/material_tag/delete_category", "素材标签删除标签分类接口"),
        ("/material_tag/delete_tag", "素材标签删除标签接口"),
        ("/material_tag/batch_delete_tag", "素材标签批量删除标签接口"),
        ("/material_tag/get_available_tag_options", "素材标签获取可用标签选项接口"),
        ("/material_work_order/create", "素材工单新建接口"),
        ("/material_work_order/update_pending_fields", "素材工单编辑待接单需求字段接口"),
        ("/material_work_order/get_create_form_meta", "素材工单新建表单元数据接口"),
        ("/material_work_order/get_filter_options", "素材工单筛选项查询接口"),
        ("/material_work_order/detail", "素材工单详情查询接口"),
        ("/material_work_order/list", "素材工单列表查询接口"),
        ("/batch_add_to_folder", "新素材库批量加入文件夹接口"),
        ("/batch_set_favorite", "新素材库批量收藏接口"),
        ("/batch_set_pinned", "新素材库批量置顶接口"),
        ("/batch_update_tags", "新素材库批量改标签接口"),
        ("/upload_cover_image", "新素材库上传封面接口"),
        ("/set_cover", "新素材库设置封面接口"),
        ("/reset_cover", "新素材库恢复默认封面接口"),
        ("/reupload_current_file", "新素材库重传当前文件接口"),
        ("/get_column_config_meta", "新素材库列配置元定义接口"),
        ("/get_gdt_reject_records", "新素材库广点通拒审记录接口"),
        ("/export_gdt_reject_records", "新素材库导出广点通拒审记录接口"),
        ("/list_column_templates", "新素材库列配置模板列表接口"),
        ("/save_column_template", "新素材库保存列配置模板接口"),
        ("/get_column_template", "新素材库查询指定列模板配置接口"),
        ("/delete_column_template", "新素材库删除列配置模板接口"),
        ("/import_material_metadata", "新素材库批量导入素材元数据接口"),
        ("/export_materials", "新素材库批量导出素材接口"),
        ("/export_import_template", "新素材库导出批量编辑模板接口"),
        ("/detail", "素材库详情查询"),
        ("/list", "素材库列表查询"),
        ("/get_filter_options", "素材库筛选项查询"),
        ("/set_favorite", "素材库收藏设置"),
        ("/set_pinned", "素材库置顶设置"),
        ("/update_belonging", "素材库归属修改"),
        ("/update_metadata", "素材库信息编辑"),
    ]
    _HIDDEN_ENDPOINTS = {
        ("GET", "/ad/material_library/export_import_template"),
    }

    @staticmethod
    def _looks_like_garbled_text(text: str) -> bool:
        value = str(text or "")
        if not value:
            return False
        return ("�" in value) or bool(re.search(r"\?{2,}", value))

    @staticmethod
    def _resolve_feature_name(url: str) -> str:
        url_text = str(url or "").lower()

        for fragment, name in TestCaseService._FEATURE_NAME_RULES:
            if fragment in url_text:
                return name

        if "material_work_order" in url_text:
            return "素材工单接口"
        if "material_library" in url_text:
            return "素材库接口"
        if "/login" in url_text:
            return "用户登录"
        if "/init" in url_text:
            return "SDK初始化"
        return "接口功能待命名"

    @staticmethod
    def list_all(project_id=None, module_id=None, page=1, per_page=20):
        query = TestCase.query
        if project_id:
            query = query.filter_by(project_id=project_id)
        if module_id:
            query = query.filter_by(module_id=module_id)
        return query.order_by(TestCase.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

    @staticmethod
    def list_all_records(project_id=None, module_id=None):
        query = TestCase.query.options(
            joinedload(TestCase.project),
            joinedload(TestCase.module),
        )
        if project_id:
            query = query.filter_by(project_id=project_id)
        if module_id:
            query = query.filter_by(module_id=module_id)
        return query.order_by(
            TestCase.module_id.asc(),
            TestCase.created_at.desc(),
            TestCase.id.desc(),
        ).all()

    @staticmethod
    def list_grouped(
        project_id=None,
        module_id=None,
        interface_name=None,
        interface_url=None,
        page=1,
        per_page=10,
    ):
        query = TestCase.query.options(
            joinedload(TestCase.project),
            joinedload(TestCase.module),
        )
        if project_id:
            query = query.filter_by(project_id=project_id)
        if module_id:
            query = query.filter_by(module_id=module_id)

        interface_name_text = str(interface_name or "").strip().lower()
        interface_url_text = str(interface_url or "").strip().lower()

        testcases = query.order_by(
            TestCase.module_id.asc(),
            TestCase.created_at.desc(),
            TestCase.id.desc(),
        ).all()

        interface_groups = []
        interface_group_map = {}
        module_summary_map = {}

        for testcase in testcases:
            data = testcase.data or {}
            method = str(data.get("method") or "GET").upper()
            url = str(data.get("url") or "").strip() or "-"
            feature_name = TestCaseService._resolve_feature_name(url)
            if interface_url_text and interface_url_text not in url.lower():
                continue
            if interface_name_text and interface_name_text not in feature_name.lower():
                continue
            if (method, url) in TestCaseService._HIDDEN_ENDPOINTS:
                continue
            group_key = (testcase.module_id, method, url)

            interface_group = interface_group_map.get(group_key)
            if interface_group is None:
                interface_group = InterfaceGroup(
                    module=testcase.module,
                    project=testcase.project,
                    method=method,
                    url=url,
                    feature_name=feature_name,
                )
                interface_group_map[group_key] = interface_group
                interface_groups.append(interface_group)

            interface_group.testcases.append(testcase)
            if interface_group.latest_created_at is None or testcase.created_at > interface_group.latest_created_at:
                interface_group.latest_created_at = testcase.created_at
            if testcase.is_active:
                interface_group.active_count += 1
            else:
                interface_group.inactive_count += 1

            if testcase.source == "ai":
                interface_group.ai_count += 1
            else:
                interface_group.manual_count += 1

            module_summary = module_summary_map.get(testcase.module_id)
            if module_summary is None:
                module_summary = {
                    "module": testcase.module,
                    "project": testcase.project,
                    "endpoint_count": 0,
                    "testcase_count": 0,
                }
                module_summary_map[testcase.module_id] = module_summary
            module_summary["testcase_count"] += 1

        for interface_group in interface_groups:
            interface_group.testcases.sort(
                key=lambda item: (item.created_at, item.id),
            )
            module_summary_map[interface_group.module.id]["endpoint_count"] += 1

        interface_groups.sort(
            key=lambda group: (
                -(
                    (group.latest_created_at or (group.testcases[0].created_at if group.testcases else group.module.created_at))
                    .timestamp()
                ),
                (group.project.name or "").lower(),
                (group.module.name or "").lower(),
                group.url.lower(),
                group.method,
            ),
        )

        module_groups = []
        module_group_map = {}
        for interface_group in interface_groups:
            module_group = module_group_map.get(interface_group.module.id)
            if module_group is None:
                summary = module_summary_map[interface_group.module.id]
                module_group = ModuleGroup(
                    module=interface_group.module,
                    project=interface_group.project,
                    total_endpoint_count=summary["endpoint_count"],
                    total_testcase_count=summary["testcase_count"],
                    latest_created_at=interface_group.latest_created_at,
                )
                module_group_map[interface_group.module.id] = module_group
                module_groups.append(module_group)
            elif (
                module_group.latest_created_at is None
                or (
                    interface_group.latest_created_at is not None
                    and interface_group.latest_created_at > module_group.latest_created_at
                )
            ):
                module_group.latest_created_at = interface_group.latest_created_at

            module_group.endpoint_groups.append(interface_group)
            module_group.displayed_endpoint_count += 1
            module_group.displayed_testcase_count += len(interface_group.testcases)

        module_groups.sort(
            key=lambda group: (
                -(
                    (group.latest_created_at or group.module.created_at).timestamp()
                ),
                (group.project.name or "").lower(),
                (group.module.name or "").lower(),
            ),
        )

        total = len(module_groups)
        if total == 0:
            return GroupedPagination(items=[], page=1, per_page=per_page, total=0)

        page = max(page, 1)
        start = (page - 1) * per_page
        end = start + per_page
        page_groups = module_groups[start:end]

        if start >= total and total > 0:
            page = math.ceil(total / per_page)
            start = (page - 1) * per_page
            end = start + per_page
            page_groups = module_groups[start:end]

        return GroupedPagination(items=page_groups, page=page, per_page=per_page, total=total)

    @staticmethod
    def get_by_id(testcase_id):
        testcase = db.session.get(TestCase, testcase_id)
        if not testcase:
            raise ServiceError("用例不存在。")
        return testcase

    @staticmethod
    def create(project_id, module_id, name, case_data, description="", source="manual", is_active=True):
        project = db.session.get(Project, project_id)
        if not project:
            raise ServiceError("所属项目不存在。")

        module = db.session.get(Module, module_id)
        if not module or module.project_id != project_id:
            raise ServiceError("所属模块不存在或与项目不匹配。")

        name = ensure_not_blank(name, "用例名称")
        if TestCaseService._looks_like_garbled_text(name):
            raise ServiceError("用例名称疑似乱码，请使用 UTF-8 中文后重试。")
        source = ensure_choice(source, "用例来源", ["manual", "ai"])
        description = str(description or "").strip()

        case_dict = parse_json_text(case_data, "用例 JSON")
        case_dict = validate_case_schema(case_dict)
        case_dict["name"] = name

        exists = TestCase.query.filter_by(module_id=module_id, name=name).first()
        if exists:
            raise ServiceError("同一模块下用例名称已存在。")

        testcase = TestCase(
            project_id=project_id,
            module_id=module_id,
            name=name,
            description=description,
            source=source,
            is_active=bool(is_active),
            case_data="{}",
        )
        testcase.data = case_dict

        db.session.add(testcase)
        commit_session()
        return testcase

    @staticmethod
    def update(testcase_id, module_id, name, case_data, description="", source="manual", is_active=True):
        testcase = TestCaseService.get_by_id(testcase_id)
        module = db.session.get(Module, module_id)
        if not module or module.project_id != testcase.project_id:
            raise ServiceError("所属模块不存在或与项目不匹配。")

        name = ensure_not_blank(name, "用例名称")
        if TestCaseService._looks_like_garbled_text(name):
            raise ServiceError("用例名称疑似乱码，请使用 UTF-8 中文后重试。")
        source = ensure_choice(source, "用例来源", ["manual", "ai"])
        description = str(description or "").strip()

        case_dict = parse_json_text(case_data, "用例 JSON")
        case_dict = validate_case_schema(case_dict)
        case_dict["name"] = name

        exists = TestCase.query.filter(
            TestCase.module_id == module_id,
            TestCase.name == name,
            TestCase.id != testcase_id,
        ).first()
        if exists:
            raise ServiceError("同一模块下用例名称已存在。")

        testcase.module_id = module_id
        testcase.name = name
        testcase.description = description
        testcase.source = source
        testcase.is_active = bool(is_active)
        testcase.data = case_dict
        commit_session()
        return testcase

    @staticmethod
    def delete(testcase_id):
        testcase = TestCaseService.get_by_id(testcase_id)
        db.session.delete(testcase)
        commit_session()
        return True

    @staticmethod
    def validate_case_json(case_data):
        case_dict = parse_json_text(case_data, "用例 JSON")
        return validate_case_schema(case_dict)


