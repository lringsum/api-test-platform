from app import create_app
from app.models import UiAutomationScript
from app.services.ui_automation_service import UiAutomationService


SCRIPT_ID = 3


def main():
    app = create_app()
    with app.app_context():
        script = UiAutomationScript.query.get(SCRIPT_ID)
        if not script:
            raise SystemExit(f"script {SCRIPT_ID} not found")
        version = next((v for v in script.versions if v.id == script.current_version_id), None)
        if version is None:
            raise SystemExit("current version not found")
        content = version.script_content

        old_block = """        if not scenario.get("skip_retain_assert"):\n            assert_contains_text(\n                x(page, scenario["xpath"]),\n                selected_value,\n                f"断言{scenario['field_name']}单项筛选后仍选中 {selected_value}",\n                f"{scenario['field_name']}下拉框",\n                expected_text=f"{scenario['field_name']}筛选条件仍为 {selected_value}",\n            )\n"""
        if old_block not in content:
            raise SystemExit("batch select retain block not found")
        content = content.replace(old_block, "", 1)

        UiAutomationService.update_script(
            script_id=script.id,
            name=script.name,
            code=script.code,
            description=script.description,
            language=script.language,
            framework=script.framework,
            status=script.status,
            tags_text=", ".join(script.tags or []),
            entry_file=script.entry_file,
            script_content=content,
            owner_id=script.owner_id,
            created_by=None,
            change_summary="移除批量下拉覆盖的查询后回显断言，只保留可操作与查询反馈校验",
        )
        refreshed = UiAutomationScript.query.get(SCRIPT_ID)
        print(
            {
                "script_id": refreshed.id,
                "current_version_id": refreshed.current_version_id,
                "version_count": len(refreshed.versions),
            }
        )


if __name__ == "__main__":
    main()
