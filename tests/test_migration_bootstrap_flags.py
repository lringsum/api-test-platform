from app import create_app


def test_app_bootstrap_flags_are_loaded(monkeypatch):
    monkeypatch.setenv("AUTO_DB_BOOTSTRAP", "false")
    monkeypatch.setenv("AUTO_DB_COMPAT_PATCH", "true")

    app = create_app()

    assert app.config["AUTO_DB_BOOTSTRAP"] is False
    assert app.config["AUTO_DB_COMPAT_PATCH"] is True

