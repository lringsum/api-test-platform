from app import db
from app.models import Report
from app.services.base_service import ServiceError, commit_session
from app.services.execution_service import ExecutionService


class ReportService:
    @staticmethod
    def get_by_id(report_id):
        report = Report.query.get(report_id)
        if not report:
            raise ServiceError("报告不存在。")
        return report

    @staticmethod
    def get_by_execution_id(execution_id):
        return Report.query.filter_by(execution_id=execution_id).first()

    @staticmethod
    def build_report_data(execution):
        details = execution.details
        failed_cases = []
        failure_details = []
        detail_summary = []

        for item in details:
            detail_summary.append(
                {
                    "testcase_name": item.testcase_name,
                    "status": item.status,
                    "duration_ms": item.duration_ms,
                }
            )

            if item.status != "passed":
                failed_cases.append(item.testcase_name)

                failed_assertions = []
                for assertion in item.assertion_data:
                    if not assertion.get("passed"):
                        failed_assertions.append(
                            {
                                "type": assertion.get("type"),
                                "expected": assertion.get("expected"),
                                "actual": assertion.get("actual"),
                                "passed": assertion.get("passed"),
                                "message": assertion.get("message"),
                            }
                        )

                failure_details.append(
                    {
                        "testcase_name": item.testcase_name,
                        "error_message": item.error_message,
                        "failed_assertions": failed_assertions,
                    }
                )

        return {
            "execution_id": execution.id,
            "project_id": execution.project_id,
            "environment_id": execution.environment_id,
            "status": execution.status,
            "total_count": execution.total_count,
            "passed_count": execution.passed_count,
            "failed_count": execution.failed_count,
            "pass_rate": execution.pass_rate,
            "total_duration_ms": execution.total_duration_ms,
            "failed_cases": failed_cases,
            "failure_details": failure_details,
            "details": detail_summary,
        }

    @staticmethod
    def generate(execution_id):
        execution = ExecutionService.get_by_id(execution_id)
        exists = ReportService.get_by_execution_id(execution_id)
        if exists:
            return exists

        report = Report(
            execution_id=execution.id,
            title=f"执行报告 #{execution.id}",
        )
        report.data = ReportService.build_report_data(execution)

        db.session.add(report)
        commit_session()
        return report

    @staticmethod
    def regenerate(execution_id):
        execution = ExecutionService.get_by_id(execution_id)
        exists = ReportService.get_by_execution_id(execution_id)

        if exists:
            exists.title = f"执行报告 #{execution.id}"
            exists.data = ReportService.build_report_data(execution)
            commit_session()
            return exists

        return ReportService.generate(execution_id)
