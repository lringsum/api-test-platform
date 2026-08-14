from app import create_app
from app.routes.legacy_spa import _PREFIX_MAP


RETIRED_API_PATHS = (
    "/api/v1/ai/options",
    "/api/v1/ai/parse",
    "/api/v1/ai/validate",
    "/api/v1/ai/save-testcase",
    "/api/v1/prompt-templates",
    "/api/v1/ui-automation/scripts/ai-generate",
    "/api/v1/ui-automation/scripts/1/ai-repair",
)


def test_retired_ai_api_routes_are_not_registered():
    app = create_app()
    rules = {rule.rule for rule in app.url_map.iter_rules()}

    for path in RETIRED_API_PATHS:
        normalized = path.replace("/1/", "/<int:script_id>/")
        assert normalized not in rules


def test_retired_ai_legacy_paths_are_not_mapped_to_spa_features():
    prefixes = {prefix for prefix, _ in _PREFIX_MAP}

    assert "ai" not in prefixes
    assert "prompts" not in prefixes
