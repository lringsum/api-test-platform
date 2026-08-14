"""add android project flows

Revision ID: 5a3d6b4f9c21
Revises: e370cba83ac6
Create Date: 2026-07-09 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5a3d6b4f9c21"
down_revision = "e370cba83ac6"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "android_ui_project_flows" not in existing_tables:
        op.create_table(
        "android_ui_project_flows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "code", name="uq_android_ui_flow_project_code"),
        sa.UniqueConstraint("project_id", "name", name="uq_android_ui_flow_project_name"),
        )
    if "android_ui_project_flow_steps" not in existing_tables:
        op.create_table(
        "android_ui_project_flow_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("flow_id", sa.Integer(), nullable=False),
        sa.Column("step_no", sa.Integer(), nullable=False),
        sa.Column("step_name", sa.String(length=120), nullable=False),
        sa.Column("step_type", sa.String(length=40), nullable=False),
        sa.Column("selector_type", sa.String(length=40), nullable=False),
        sa.Column("selector_value", sa.String(length=255), nullable=False),
        sa.Column("input_value", sa.String(length=255), nullable=False),
        sa.Column("wait_timeout_sec", sa.Integer(), nullable=False),
        sa.Column("retry_times", sa.Integer(), nullable=False),
        sa.Column("continue_on_failure", sa.Boolean(), nullable=False),
        sa.Column("capture_on_success", sa.Boolean(), nullable=False),
        sa.Column("capture_on_failure", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("remark", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["flow_id"], ["android_ui_project_flows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("flow_id", "step_no", name="uq_android_ui_flow_step_no"),
        )
    with op.batch_alter_table("android_ui_test_tasks", schema=None) as batch_op:
        existing_columns = {row["name"] for row in inspector.get_columns("android_ui_test_tasks")}
        if "flow_mode" not in existing_columns:
            batch_op.add_column(sa.Column("flow_mode", sa.String(length=20), nullable=False, server_default="basic"))
        if "flow_id" not in existing_columns:
            batch_op.add_column(sa.Column("flow_id", sa.Integer(), nullable=True))
        if "flow_override_enabled" not in existing_columns:
            batch_op.add_column(sa.Column("flow_override_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("android_ui_test_runs", schema=None) as batch_op:
        existing_columns = {row["name"] for row in inspector.get_columns("android_ui_test_runs")}
        if "flow_mode" not in existing_columns:
            batch_op.add_column(sa.Column("flow_mode", sa.String(length=20), nullable=False, server_default="basic"))
        if "flow_id" not in existing_columns:
            batch_op.add_column(sa.Column("flow_id", sa.Integer(), nullable=True))
        if "flow_snapshot_json" not in existing_columns:
            batch_op.add_column(sa.Column("flow_snapshot_json", sa.Text(), nullable=False, server_default="{}"))
    if "android_ui_run_steps" not in existing_tables:
        op.create_table(
        "android_ui_run_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("flow_id", sa.Integer(), nullable=True),
        sa.Column("template_step_id", sa.Integer(), nullable=True),
        sa.Column("step_no", sa.Integer(), nullable=False),
        sa.Column("step_name", sa.String(length=120), nullable=False),
        sa.Column("step_type", sa.String(length=40), nullable=False),
        sa.Column("selector_type", sa.String(length=40), nullable=False),
        sa.Column("selector_value", sa.String(length=255), nullable=False),
        sa.Column("input_value", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("screenshot_path", sa.String(length=500), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("raw_result_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["flow_id"], ["android_ui_project_flows.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["android_ui_test_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_step_id"], ["android_ui_project_flow_steps.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        )
    if "android_ui_run_step_artifacts" not in existing_tables:
        op.create_table(
        "android_ui_run_step_artifacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_step_id", sa.Integer(), nullable=False),
        sa.Column("artifact_type", sa.String(length=40), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_step_id"], ["android_ui_run_steps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        )
    with op.batch_alter_table("android_ui_test_tasks", schema=None) as batch_op:
        batch_op.alter_column("flow_mode", server_default=None)
        batch_op.alter_column("flow_override_enabled", server_default=None)
    with op.batch_alter_table("android_ui_test_runs", schema=None) as batch_op:
        batch_op.alter_column("flow_mode", server_default=None)
        batch_op.alter_column("flow_snapshot_json", server_default=None)


def downgrade():
    op.drop_table("android_ui_run_step_artifacts")
    op.drop_table("android_ui_run_steps")
    with op.batch_alter_table("android_ui_test_runs", schema=None) as batch_op:
        batch_op.drop_constraint("fk_android_ui_test_runs_flow_id", type_="foreignkey")
        batch_op.drop_column("flow_snapshot_json")
        batch_op.drop_column("flow_id")
        batch_op.drop_column("flow_mode")
    with op.batch_alter_table("android_ui_test_tasks", schema=None) as batch_op:
        batch_op.drop_constraint("fk_android_ui_test_tasks_flow_id", type_="foreignkey")
        batch_op.drop_column("flow_override_enabled")
        batch_op.drop_column("flow_id")
        batch_op.drop_column("flow_mode")
    op.drop_table("android_ui_project_flow_steps")
    op.drop_table("android_ui_project_flows")
