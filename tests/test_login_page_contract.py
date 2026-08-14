from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_authentication_is_rendered_by_the_vue_application():
    page = (ROOT / "frontend" / "src" / "views" / "AuthPage.vue").read_text(encoding="utf-8")
    route = (ROOT / "app" / "routes" / "auth.py").read_text(encoding="utf-8")

    assert "platformApi.login" in page
    assert "username" in page
    assert "password" in page
    assert "/app/login" in route
    assert "render_template" not in route


def test_legacy_auth_urls_remain_compatibility_redirects():
    route = (ROOT / "app" / "routes" / "auth.py").read_text(encoding="utf-8")
    assert 'route("/forbidden", methods=["GET"])' in route
    assert 'route("/logout", methods=["POST"])' in route
    assert '"/app/forbidden"' in route
