from flask import Blueprint, render_template, request

from app.models import Execution, Project, Report
from app.project_context import resolve_project_id
from app.security import accessible_projects, require_permission
from app.services.report_service import ReportService

report_bp = Blueprint("report", __name__, url_prefix="/reports")


@report_bp.route("/")
@require_permission("report:view")
def list_reports():
    project_id = resolve_project_id()
    status = (request.args.get("status") or "").strip()
    page = request.args.get("page", 1, type=int)

    query = Report.query.join(Execution, Report.execution_id == Execution.id)
    if project_id:
        query = query.filter(Execution.project_id == project_id)
    if status in ("passed", "failed"):
        query = query.filter(Execution.status == status)

    pagination = query.order_by(Report.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return render_template("reports/_list_content.html", pagination=pagination)

    projects = accessible_projects()
    return render_template(
        "reports/list.html",
        pagination=pagination,
        projects=projects,
        selected_project_id=project_id,
        selected_status=status,
    )


@report_bp.route("/<int:report_id>")
@require_permission("report:view")
def detail_report(report_id):
    report = ReportService.get_by_id(report_id)
    return render_template("reports/detail.html", report=report)
