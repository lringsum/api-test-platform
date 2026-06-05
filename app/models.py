import json
from datetime import datetime

from sqlalchemy import UniqueConstraint

from app import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class JsonTextMixin:
    @staticmethod
    def dumps_json(data):
        if data is None:
            return "{}"
        return json.dumps(data, ensure_ascii=False, indent=2)

    @staticmethod
    def loads_json(text, default=None):
        if default is None:
            default = {}
        if not text:
            return default
        try:
            return json.loads(text)
        except (TypeError, ValueError):
            return default


class Project(db.Model, TimestampMixin):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("name", name="uq_project_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), default="", nullable=False)
    status = db.Column(db.String(20), default="active", nullable=False)

    modules = db.relationship(
        "Module",
        backref="project",
        cascade="all, delete-orphan",
        lazy=True,
    )
    environments = db.relationship(
        "Environment",
        backref="project",
        cascade="all, delete-orphan",
        lazy=True,
    )
    variables = db.relationship(
        "Variable",
        backref="project",
        cascade="all, delete-orphan",
        lazy=True,
    )
    testcases = db.relationship(
        "TestCase",
        backref="project",
        cascade="all, delete-orphan",
        lazy=True,
    )
    executions = db.relationship(
        "Execution",
        backref="project",
        cascade="all, delete-orphan",
        lazy=True,
    )
    scenarios = db.relationship(
        "Scenario",
        backref="project",
        cascade="all, delete-orphan",
        lazy=True,
    )

    def __repr__(self):
        return f"<Project {self.name}>"


class Module(db.Model, TimestampMixin):
    __tablename__ = "modules"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_module_project_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), default="", nullable=False)

    testcases = db.relationship(
        "TestCase",
        backref="module",
        cascade="all, delete-orphan",
        lazy=True,
    )
    scenarios = db.relationship(
        "Scenario",
        backref="module",
        lazy=True,
    )

    def __repr__(self):
        return f"<Module {self.name}>"


class Environment(db.Model, TimestampMixin, JsonTextMixin):
    __tablename__ = "environments"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_environment_project_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = db.Column(db.String(100), nullable=False)
    base_url = db.Column(db.String(255), nullable=False)
    headers_json = db.Column(db.Text, default="{}", nullable=False)
    variables_json = db.Column(db.Text, default="{}", nullable=False)
    description = db.Column(db.String(255), default="", nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    variables = db.relationship(
        "Variable",
        backref="environment",
        cascade="all, delete-orphan",
        lazy=True,
    )
    executions = db.relationship(
        "Execution",
        backref="environment",
        lazy=True,
    )
    scenario_executions = db.relationship(
        "ScenarioExecution",
        backref="environment",
        lazy=True,
    )

    @property
    def headers(self):
        return self.loads_json(self.headers_json, default={})

    @headers.setter
    def headers(self, value):
        self.headers_json = self.dumps_json(value)

    @property
    def variables_data(self):
        return self.loads_json(self.variables_json, default={})

    @variables_data.setter
    def variables_data(self, value):
        self.variables_json = self.dumps_json(value)

    def __repr__(self):
        return f"<Environment {self.name}>"


class Variable(db.Model, TimestampMixin):
    __tablename__ = "variables"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "environment_id",
            "name",
            name="uq_variable_scope_name",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    environment_id = db.Column(
        db.Integer,
        db.ForeignKey("environments.id", ondelete="CASCADE"),
        nullable=True,
    )
    name = db.Column(db.String(100), nullable=False)
    value = db.Column(db.Text, default="", nullable=False)
    scope = db.Column(db.String(20), default="project", nullable=False)
    description = db.Column(db.String(255), default="", nullable=False)

    def __repr__(self):
        return f"<Variable {self.name}>"


class TestCase(db.Model, TimestampMixin, JsonTextMixin):
    __tablename__ = "testcases"
    __table_args__ = (
        UniqueConstraint("module_id", "name", name="uq_testcase_module_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    module_id = db.Column(
        db.Integer,
        db.ForeignKey("modules.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), default="", nullable=False)
    case_data = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(20), default="manual", nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    execution_details = db.relationship(
        "ExecutionDetail",
        backref="testcase",
        lazy=True,
    )
    scenario_steps = db.relationship(
        "ScenarioStep",
        backref="testcase",
        lazy=True,
    )

    @property
    def data(self):
        return self.loads_json(self.case_data, default={})

    @data.setter
    def data(self, value):
        self.case_data = self.dumps_json(value)

    def __repr__(self):
        return f"<TestCase {self.name}>"


class PromptTemplate(db.Model, TimestampMixin):
    __tablename__ = "prompt_templates"
    __table_args__ = (
        UniqueConstraint("name", name="uq_prompt_template_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    description = db.Column(db.String(255), default="", nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<PromptTemplate {self.name}>"


class Execution(db.Model, TimestampMixin, JsonTextMixin):
    __tablename__ = "executions"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    environment_id = db.Column(
        db.Integer,
        db.ForeignKey("environments.id", ondelete="SET NULL"),
        nullable=True,
    )
    execution_type = db.Column(db.String(20), nullable=False)
    target_type = db.Column(db.String(20), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False)
    total_count = db.Column(db.Integer, default=0, nullable=False)
    passed_count = db.Column(db.Integer, default=0, nullable=False)
    failed_count = db.Column(db.Integer, default=0, nullable=False)
    pass_rate = db.Column(db.Float, default=0.0, nullable=False)
    total_duration_ms = db.Column(db.Integer, default=0, nullable=False)
    summary_json = db.Column(db.Text, default="{}", nullable=False)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)

    details = db.relationship(
        "ExecutionDetail",
        backref="execution",
        cascade="all, delete-orphan",
        lazy=True,
    )
    report = db.relationship(
        "Report",
        backref="execution",
        uselist=False,
        cascade="all, delete-orphan",
        lazy=True,
    )

    @property
    def summary(self):
        return self.loads_json(self.summary_json, default={})

    @summary.setter
    def summary(self, value):
        self.summary_json = self.dumps_json(value)

    def __repr__(self):
        return f"<Execution {self.id}>"


class ExecutionDetail(db.Model, TimestampMixin, JsonTextMixin):
    __tablename__ = "execution_details"

    id = db.Column(db.Integer, primary_key=True)
    execution_id = db.Column(
        db.Integer,
        db.ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    testcase_id = db.Column(
        db.Integer,
        db.ForeignKey("testcases.id", ondelete="SET NULL"),
        nullable=True,
    )
    testcase_name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False)
    request_snapshot = db.Column(db.Text, default="{}", nullable=False)
    response_snapshot = db.Column(db.Text, default="{}", nullable=False)
    assertion_results = db.Column(db.Text, default="[]", nullable=False)
    extract_results = db.Column(db.Text, default="{}", nullable=False)
    error_message = db.Column(db.Text, default="", nullable=False)
    duration_ms = db.Column(db.Integer, default=0, nullable=False)

    @property
    def request_data(self):
        return self.loads_json(self.request_snapshot, default={})

    @request_data.setter
    def request_data(self, value):
        self.request_snapshot = self.dumps_json(value)

    @property
    def response_data(self):
        return self.loads_json(self.response_snapshot, default={})

    @response_data.setter
    def response_data(self, value):
        self.response_snapshot = self.dumps_json(value)

    @property
    def assertion_data(self):
        return self.loads_json(self.assertion_results, default=[])

    @assertion_data.setter
    def assertion_data(self, value):
        self.assertion_results = self.dumps_json(value)

    @property
    def extract_data(self):
        return self.loads_json(self.extract_results, default={})

    @extract_data.setter
    def extract_data(self, value):
        self.extract_results = self.dumps_json(value)

    def __repr__(self):
        return f"<ExecutionDetail {self.testcase_name}>"


class Report(db.Model, TimestampMixin, JsonTextMixin):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    execution_id = db.Column(
        db.Integer,
        db.ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    title = db.Column(db.String(150), nullable=False)
    report_data = db.Column(db.Text, default="{}", nullable=False)

    @property
    def data(self):
        return self.loads_json(self.report_data, default={})

    @data.setter
    def data(self, value):
        self.report_data = self.dumps_json(value)

    def __repr__(self):
        return f"<Report {self.title}>"


class Scenario(db.Model, TimestampMixin, JsonTextMixin):
    __tablename__ = "scenarios"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_scenario_project_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    module_id = db.Column(
        db.Integer,
        db.ForeignKey("modules.id", ondelete="SET NULL"),
        nullable=True,
    )
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), default="", nullable=False)
    status = db.Column(db.String(20), default="active", nullable=False)
    tags_json = db.Column(db.Text, default="[]", nullable=False)

    steps = db.relationship(
        "ScenarioStep",
        backref="scenario",
        cascade="all, delete-orphan",
        order_by="ScenarioStep.order_no",
        lazy=True,
    )
    executions = db.relationship(
        "ScenarioExecution",
        backref="scenario",
        cascade="all, delete-orphan",
        lazy=True,
    )

    @property
    def tags(self):
        return self.loads_json(self.tags_json, default=[])

    @tags.setter
    def tags(self, value):
        self.tags_json = self.dumps_json(value or [])

    def __repr__(self):
        return f"<Scenario {self.name}>"


class ScenarioStep(db.Model, TimestampMixin, JsonTextMixin):
    __tablename__ = "scenario_steps"
    __table_args__ = (
        UniqueConstraint("scenario_id", "order_no", name="uq_scenario_step_order"),
    )

    id = db.Column(db.Integer, primary_key=True)
    scenario_id = db.Column(
        db.Integer,
        db.ForeignKey("scenarios.id", ondelete="CASCADE"),
        nullable=False,
    )
    testcase_id = db.Column(
        db.Integer,
        db.ForeignKey("testcases.id", ondelete="SET NULL"),
        nullable=True,
    )
    order_no = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(100), default="", nullable=False)
    is_enabled = db.Column(db.Boolean, default=True, nullable=False)
    continue_on_failure = db.Column(db.Boolean, default=False, nullable=False)
    setup_variables_json = db.Column(db.Text, default="{}", nullable=False)
    request_overrides_json = db.Column(db.Text, default="{}", nullable=False)
    extract_overrides_json = db.Column(db.Text, default="{}", nullable=False)
    assertion_overrides_json = db.Column(db.Text, default="[]", nullable=False)

    execution_details = db.relationship(
        "ScenarioExecutionDetail",
        backref="scenario_step",
        lazy=True,
    )

    @property
    def setup_variables(self):
        return self.loads_json(self.setup_variables_json, default={})

    @setup_variables.setter
    def setup_variables(self, value):
        self.setup_variables_json = self.dumps_json(value or {})

    @property
    def request_overrides(self):
        return self.loads_json(self.request_overrides_json, default={})

    @request_overrides.setter
    def request_overrides(self, value):
        self.request_overrides_json = self.dumps_json(value or {})

    @property
    def extract_overrides(self):
        return self.loads_json(self.extract_overrides_json, default={})

    @extract_overrides.setter
    def extract_overrides(self, value):
        self.extract_overrides_json = self.dumps_json(value or {})

    @property
    def assertion_overrides(self):
        return self.loads_json(self.assertion_overrides_json, default=[])

    @assertion_overrides.setter
    def assertion_overrides(self, value):
        self.assertion_overrides_json = self.dumps_json(value or [])

    def __repr__(self):
        return f"<ScenarioStep {self.order_no}:{self.name or self.testcase_id}>"


class ScenarioExecution(db.Model, TimestampMixin, JsonTextMixin):
    __tablename__ = "scenario_executions"

    id = db.Column(db.Integer, primary_key=True)
    scenario_id = db.Column(
        db.Integer,
        db.ForeignKey("scenarios.id", ondelete="CASCADE"),
        nullable=False,
    )
    environment_id = db.Column(
        db.Integer,
        db.ForeignKey("environments.id", ondelete="SET NULL"),
        nullable=True,
    )
    trigger_mode = db.Column(db.String(20), default="manual", nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False)
    total_steps = db.Column(db.Integer, default=0, nullable=False)
    passed_steps = db.Column(db.Integer, default=0, nullable=False)
    failed_steps = db.Column(db.Integer, default=0, nullable=False)
    duration_ms = db.Column(db.Integer, default=0, nullable=False)
    runtime_variables_json = db.Column(db.Text, default="{}", nullable=False)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)

    details = db.relationship(
        "ScenarioExecutionDetail",
        backref="scenario_execution",
        cascade="all, delete-orphan",
        lazy=True,
    )

    @property
    def runtime_variables(self):
        return self.loads_json(self.runtime_variables_json, default={})

    @runtime_variables.setter
    def runtime_variables(self, value):
        self.runtime_variables_json = self.dumps_json(value or {})

    def __repr__(self):
        return f"<ScenarioExecution {self.id}>"


class ScenarioExecutionDetail(db.Model, TimestampMixin, JsonTextMixin):
    __tablename__ = "scenario_execution_details"

    id = db.Column(db.Integer, primary_key=True)
    scenario_execution_id = db.Column(
        db.Integer,
        db.ForeignKey("scenario_executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    scenario_step_id = db.Column(
        db.Integer,
        db.ForeignKey("scenario_steps.id", ondelete="SET NULL"),
        nullable=True,
    )
    testcase_id = db.Column(
        db.Integer,
        db.ForeignKey("testcases.id", ondelete="SET NULL"),
        nullable=True,
    )
    step_name = db.Column(db.String(100), nullable=False)
    testcase_name = db.Column(db.String(100), default="", nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False)
    request_snapshot_json = db.Column(db.Text, default="{}", nullable=False)
    response_snapshot_json = db.Column(db.Text, default="{}", nullable=False)
    extract_snapshot_json = db.Column(db.Text, default="{}", nullable=False)
    assertion_results_json = db.Column(db.Text, default="[]", nullable=False)
    error_message = db.Column(db.Text, default="", nullable=False)
    duration_ms = db.Column(db.Integer, default=0, nullable=False)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)

    @property
    def request_data(self):
        return self.loads_json(self.request_snapshot_json, default={})

    @request_data.setter
    def request_data(self, value):
        self.request_snapshot_json = self.dumps_json(value or {})

    @property
    def response_data(self):
        return self.loads_json(self.response_snapshot_json, default={})

    @response_data.setter
    def response_data(self, value):
        self.response_snapshot_json = self.dumps_json(value or {})

    @property
    def extract_data(self):
        return self.loads_json(self.extract_snapshot_json, default={})

    @extract_data.setter
    def extract_data(self, value):
        self.extract_snapshot_json = self.dumps_json(value or {})

    @property
    def assertion_data(self):
        return self.loads_json(self.assertion_results_json, default=[])

    @assertion_data.setter
    def assertion_data(self, value):
        self.assertion_results_json = self.dumps_json(value or [])

    def __repr__(self):
        return f"<ScenarioExecutionDetail {self.step_name}>"
