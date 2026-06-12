from app import db
from app.models import Module, Project, Scenario, ScenarioStep, TestCase
from app.services.base_service import (
    ServiceError,
    commit_session,
    ensure_choice,
    ensure_not_blank,
    parse_json_text,
)


class ScenarioService:
    @staticmethod
    def list_all(project_id=None, module_id=None, status=None, keyword=None):
        query = Scenario.query
        if project_id:
            query = query.filter_by(project_id=project_id)
        if module_id:
            query = query.filter_by(module_id=module_id)
        if status:
            query = query.filter_by(status=status)
        if keyword:
            query = query.filter(Scenario.name.contains(str(keyword).strip()))
        return query.order_by(Scenario.created_at.desc()).all()

    @staticmethod
    def get_by_id(scenario_id):
        scenario = db.session.get(Scenario, scenario_id)
        if not scenario:
            raise ServiceError("场景不存在。")
        return scenario

    @staticmethod
    def create(project_id, module_id, name, description="", status="active", tags_text=""):
        project = db.session.get(Project, project_id)
        if not project:
            raise ServiceError("所属项目不存在。")

        module_id = module_id or None
        if module_id:
            module = db.session.get(Module, module_id)
            if not module or module.project_id != project_id:
                raise ServiceError("所属模块不存在或与项目不匹配。")

        name = ensure_not_blank(name, "场景名称")
        status = ensure_choice(status or "active", "场景状态", ["active", "inactive"])
        description = str(description or "").strip()
        tags = ScenarioService.parse_tags(tags_text)

        exists = Scenario.query.filter_by(project_id=project_id, name=name).first()
        if exists:
            raise ServiceError("同一项目下场景名称已存在。")

        scenario = Scenario(
            project_id=project_id,
            module_id=module_id,
            name=name,
            description=description,
            status=status,
        )
        scenario.tags = tags
        db.session.add(scenario)
        commit_session()
        return scenario

    @staticmethod
    def update(scenario_id, module_id, name, description="", status="active", tags_text=""):
        scenario = ScenarioService.get_by_id(scenario_id)
        module_id = module_id or None
        if module_id:
            module = db.session.get(Module, module_id)
            if not module or module.project_id != scenario.project_id:
                raise ServiceError("所属模块不存在或与项目不匹配。")

        name = ensure_not_blank(name, "场景名称")
        status = ensure_choice(status or "active", "场景状态", ["active", "inactive"])
        description = str(description or "").strip()
        tags = ScenarioService.parse_tags(tags_text)

        exists = Scenario.query.filter(
            Scenario.project_id == scenario.project_id,
            Scenario.name == name,
            Scenario.id != scenario_id,
        ).first()
        if exists:
            raise ServiceError("同一项目下场景名称已存在。")

        scenario.module_id = module_id
        scenario.name = name
        scenario.description = description
        scenario.status = status
        scenario.tags = tags
        commit_session()
        return scenario

    @staticmethod
    def delete(scenario_id):
        scenario = ScenarioService.get_by_id(scenario_id)
        db.session.delete(scenario)
        commit_session()
        return True

    @staticmethod
    def add_step(
        scenario_id,
        testcase_id,
        name="",
        continue_on_failure=False,
        is_enabled=True,
        setup_variables_text="{}",
        request_overrides_text="{}",
        extract_overrides_text="{}",
        assertion_overrides_text="[]",
    ):
        scenario = ScenarioService.get_by_id(scenario_id)
        testcase = ScenarioService._get_valid_testcase(testcase_id, scenario.project_id)

        step = ScenarioStep(
            scenario_id=scenario.id,
            testcase_id=testcase.id,
            order_no=ScenarioService._next_order_no(scenario.id),
            name=str(name or "").strip(),
            continue_on_failure=bool(continue_on_failure),
            is_enabled=bool(is_enabled),
        )
        ScenarioService._apply_step_payload(
            step=step,
            setup_variables_text=setup_variables_text,
            request_overrides_text=request_overrides_text,
            extract_overrides_text=extract_overrides_text,
            assertion_overrides_text=assertion_overrides_text,
        )
        db.session.add(step)
        commit_session()
        return step

    @staticmethod
    def update_step(
        scenario_step_id,
        testcase_id,
        name="",
        continue_on_failure=False,
        is_enabled=True,
        setup_variables_text="{}",
        request_overrides_text="{}",
        extract_overrides_text="{}",
        assertion_overrides_text="[]",
    ):
        step = ScenarioService.get_step_by_id(scenario_step_id)
        testcase = ScenarioService._get_valid_testcase(testcase_id, step.scenario.project_id)

        step.testcase_id = testcase.id
        step.name = str(name or "").strip()
        step.continue_on_failure = bool(continue_on_failure)
        step.is_enabled = bool(is_enabled)
        ScenarioService._apply_step_payload(
            step=step,
            setup_variables_text=setup_variables_text,
            request_overrides_text=request_overrides_text,
            extract_overrides_text=extract_overrides_text,
            assertion_overrides_text=assertion_overrides_text,
        )
        commit_session()
        return step

    @staticmethod
    def delete_step(scenario_step_id):
        step = ScenarioService.get_step_by_id(scenario_step_id)
        scenario_id = step.scenario_id
        db.session.delete(step)
        commit_session()
        ScenarioService._reorder_steps(scenario_id)
        return True

    @staticmethod
    def move_step_up(scenario_step_id):
        step = ScenarioService.get_step_by_id(scenario_step_id)
        previous_step = (
            ScenarioStep.query.filter(
                ScenarioStep.scenario_id == step.scenario_id,
                ScenarioStep.order_no < step.order_no,
            )
            .order_by(ScenarioStep.order_no.desc())
            .first()
        )
        if not previous_step:
            return step

        step.order_no, previous_step.order_no = previous_step.order_no, step.order_no
        commit_session()
        return step

    @staticmethod
    def move_step_down(scenario_step_id):
        step = ScenarioService.get_step_by_id(scenario_step_id)
        next_step = (
            ScenarioStep.query.filter(
                ScenarioStep.scenario_id == step.scenario_id,
                ScenarioStep.order_no > step.order_no,
            )
            .order_by(ScenarioStep.order_no.asc())
            .first()
        )
        if not next_step:
            return step

        step.order_no, next_step.order_no = next_step.order_no, step.order_no
        commit_session()
        return step

    @staticmethod
    def get_step_by_id(scenario_step_id):
        step = db.session.get(ScenarioStep, scenario_step_id)
        if not step:
            raise ServiceError("场景步骤不存在。")
        return step

    @staticmethod
    def parse_tags(tags_text):
        raw_text = str(tags_text or "").strip()
        if not raw_text:
            return []
        return [item.strip() for item in raw_text.split(",") if item.strip()]

    @staticmethod
    def format_tags(tags):
        return ", ".join(tags or [])

    @staticmethod
    def _next_order_no(scenario_id):
        last_step = (
            ScenarioStep.query.filter_by(scenario_id=scenario_id)
            .order_by(ScenarioStep.order_no.desc())
            .first()
        )
        return 1 if not last_step else last_step.order_no + 1

    @staticmethod
    def _get_valid_testcase(testcase_id, project_id):
        testcase = db.session.get(TestCase, testcase_id)
        if not testcase or testcase.project_id != project_id:
            raise ServiceError("关联用例不存在或与场景项目不匹配。")
        return testcase

    @staticmethod
    def _apply_step_payload(
        step,
        setup_variables_text="{}",
        request_overrides_text="{}",
        extract_overrides_text="{}",
        assertion_overrides_text="[]",
    ):
        step.setup_variables = ScenarioService._parse_dict_json(
            setup_variables_text, "步骤变量注入"
        )
        step.request_overrides = ScenarioService._parse_dict_json(
            request_overrides_text, "请求覆盖"
        )
        step.extract_overrides = ScenarioService._parse_dict_json(
            extract_overrides_text, "提取覆盖"
        )
        step.assertion_overrides = ScenarioService._parse_list_json(
            assertion_overrides_text, "断言覆盖"
        )

    @staticmethod
    def _parse_dict_json(json_text, field_name):
        text = str(json_text or "").strip()
        if not text:
            return {}
        data = parse_json_text(text, field_name)
        if not isinstance(data, dict):
            raise ServiceError(f"{field_name} 必须是对象。")
        return data

    @staticmethod
    def _parse_list_json(json_text, field_name):
        text = str(json_text or "").strip()
        if not text:
            return []
        data = parse_json_text(text, field_name)
        if not isinstance(data, list):
            raise ServiceError(f"{field_name} 必须是数组。")
        return data

    @staticmethod
    def _reorder_steps(scenario_id):
        steps = (
            ScenarioStep.query.filter_by(scenario_id=scenario_id)
            .order_by(ScenarioStep.order_no.asc(), ScenarioStep.id.asc())
            .all()
        )
        for index, step in enumerate(steps, start=1):
            step.order_no = index
        commit_session()
