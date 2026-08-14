"""add ui automation project settings

Revision ID: 8c9b0d1e2f3a
Revises: 5a3d6b4f9c21
Create Date: 2026-07-22 11:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "8c9b0d1e2f3a"
down_revision = "5a3d6b4f9c21"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if inspect(bind).has_table("ui_automation_project_settings"):
        return
    op.create_table(
        "ui_automation_project_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_ui_project_setting_project"),
    )
    with op.batch_alter_table("ui_automation_project_settings", schema=None) as batch_op:
        batch_op.alter_column("settings_json", server_default=None)


def downgrade():
    bind = op.get_bind()
    if inspect(bind).has_table("ui_automation_project_settings"):
        op.drop_table("ui_automation_project_settings")
