from datetime import datetime, timedelta
from collections import defaultdict

from flask import Blueprint, render_template, request

from app.models import Environment, Execution, ExecutionDetail, Project, TestCase
from app.project_context import resolve_project_id

dashboard_bp = Blueprint("dashboard", __name__)
BJT_OFFSET = timedelta(hours=8)
DEFAULT_MANUAL_MINUTES_PER_CASE = 3


@dashboard_bp.route("/")
def index():
    selected_project_id = resolve_project_id()

    now_utc = datetime.utcnow()
    today_bjt = (now_utc + BJT_OFFSET).date()

    trend_days = 30
    trend_start_bjt = today_bjt - timedelta(days=trend_days - 1)
    trend_start_utc = datetime.combine(trend_start_bjt, datetime.min.time()) - BJT_OFFSET

    quarter_start_month = ((today_bjt.month - 1) // 3) * 3 + 1
    quarter_start_bjt = today_bjt.replace(month=quarter_start_month, day=1)
    quarter_start_utc = datetime.combine(quarter_start_bjt, datetime.min.time()) - BJT_OFFSET

    query_start_utc = min(trend_start_utc, quarter_start_utc)
    details_query = (
        ExecutionDetail.query.join(Execution, ExecutionDetail.execution_id == Execution.id)
        .filter(ExecutionDetail.created_at >= query_start_utc)
        .order_by(ExecutionDetail.created_at.asc())
    )
    if selected_project_id:
        details_query = details_query.filter(Execution.project_id == selected_project_id)
    details = details_query.all()

    trend_dates = [trend_start_bjt + timedelta(days=i) for i in range(trend_days)]
    trend_bucket = {day: {"total": 0, "passed": 0, "failed": 0} for day in trend_dates}

    quarter_total = 0
    quarter_passed = 0
    quarter_failed = 0
    quarter_active_days = set()
    quarter_case_counter = defaultdict(lambda: {"name": "", "total": 0, "failed": 0})
    quarter_module_counter = defaultdict(lambda: {"name": "未分组模块", "total": 0, "failed": 0})

    testcase_ids = sorted({item.testcase_id for item in details if item.testcase_id})
    testcase_module_map = {}
    testcase_name_map = {}
    if testcase_ids:
        testcases = TestCase.query.filter(TestCase.id.in_(testcase_ids)).all()
        testcase_module_map = {item.id: item.module for item in testcases}
        testcase_name_map = {item.id: item.name for item in testcases}

    for detail in details:
        if not detail.created_at:
            continue
        detail_date_bjt = (detail.created_at + BJT_OFFSET).date()

        if trend_start_bjt <= detail_date_bjt <= today_bjt:
            trend_bucket[detail_date_bjt]["total"] += 1
            if detail.status == "passed":
                trend_bucket[detail_date_bjt]["passed"] += 1
            elif detail.status == "failed":
                trend_bucket[detail_date_bjt]["failed"] += 1

        if quarter_start_bjt <= detail_date_bjt <= today_bjt:
            quarter_total += 1
            case_key = detail.testcase_id or detail.testcase_name
            case_name = testcase_name_map.get(detail.testcase_id, detail.testcase_name or "未知接口")
            quarter_case_counter[case_key]["name"] = case_name
            quarter_case_counter[case_key]["total"] += 1

            module = testcase_module_map.get(detail.testcase_id)
            module_key = module.id if module else f"unknown:{detail.testcase_name}"
            module_name = module.name if module else "未分组模块"
            quarter_module_counter[module_key]["name"] = module_name
            quarter_module_counter[module_key]["total"] += 1

            if detail.status == "passed":
                quarter_passed += 1
            elif detail.status == "failed":
                quarter_failed += 1
                quarter_case_counter[case_key]["failed"] += 1
                quarter_module_counter[module_key]["failed"] += 1
            if detail.status in ("passed", "failed"):
                quarter_active_days.add(detail_date_bjt)

    trend_labels = [day.strftime("%m-%d") for day in trend_dates]
    trend_totals = [trend_bucket[day]["total"] for day in trend_dates]
    trend_passed = [trend_bucket[day]["passed"] for day in trend_dates]
    trend_failed = [trend_bucket[day]["failed"] for day in trend_dates]
    trend_pass_rate = [
        round((trend_bucket[day]["passed"] / trend_bucket[day]["total"]) * 100, 2)
        if trend_bucket[day]["total"] > 0
        else 0
        for day in trend_dates
    ]

    quarter_days = (today_bjt - quarter_start_bjt).days + 1
    quarter_pass_rate = round((quarter_passed / quarter_total) * 100, 2) if quarter_total else 0
    quarter_active_rate = round((len(quarter_active_days) / quarter_days) * 100, 2) if quarter_days else 0
    quarter_saved_hours = round((quarter_total * DEFAULT_MANUAL_MINUTES_PER_CASE) / 60, 1)

    trend_chart = {
        "labels": trend_labels,
        "total": trend_totals,
        "passed": trend_passed,
        "failed": trend_failed,
        "pass_rate": trend_pass_rate,
    }

    quarter_metrics = {
        "label": f"{today_bjt.year} Q{((today_bjt.month - 1) // 3) + 1}",
        "period": f"{quarter_start_bjt.strftime('%Y-%m-%d')} ~ {today_bjt.strftime('%Y-%m-%d')}",
        "total_cases": quarter_total,
        "pass_rate": quarter_pass_rate,
        "active_days": len(quarter_active_days),
        "active_rate": quarter_active_rate,
        "saved_hours": quarter_saved_hours,
    }

    top_failed_cases = sorted(
        [
            {
                "name": item["name"],
                "failed": item["failed"],
                "total": item["total"],
                "fail_rate": round((item["failed"] / item["total"]) * 100, 2) if item["total"] else 0,
            }
            for item in quarter_case_counter.values()
            if item["failed"] > 0
        ],
        key=lambda x: (x["failed"], x["fail_rate"]),
        reverse=True,
    )[:8]

    top_failed_modules = sorted(
        [
            {
                "name": item["name"],
                "failed": item["failed"],
                "total": item["total"],
                "fail_rate": round((item["failed"] / item["total"]) * 100, 2) if item["total"] else 0,
            }
            for item in quarter_module_counter.values()
            if item["failed"] > 0
        ],
        key=lambda x: (x["failed"], x["fail_rate"]),
        reverse=True,
    )[:8]

    stats = {
        "project_count": Project.query.count(),
        "testcase_count": TestCase.query.count(),
        "environment_count": Environment.query.count(),
        "execution_count": Execution.query.count(),
    }
    recent_query = Execution.query
    if selected_project_id:
        recent_query = recent_query.filter(Execution.project_id == selected_project_id)
    recent_executions = recent_query.order_by(Execution.created_at.desc()).limit(10).all()
    projects = Project.query.order_by(Project.created_at.desc()).all()

    return render_template(
        "dashboard.html",
        stats=stats,
        recent_executions=recent_executions,
        trend_chart=trend_chart,
        quarter_metrics=quarter_metrics,
        projects=projects,
        selected_project_id=selected_project_id,
        top_failed_cases=top_failed_cases,
        top_failed_modules=top_failed_modules,
    )
