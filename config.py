import os


BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _default_database_url():
    db_path = os.path.join(BASE_DIR, "instance", "app.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return "sqlite:///" + db_path


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = int(os.environ.get("PORT", 5000))
    DEBUG = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    SQLALCHEMY_DATABASE_URI = _default_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
    JSON_AS_ASCII = False
    AI_MODE = os.environ.get("AI_MODE", "mock")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
    OPENAI_TIMEOUT = int(os.environ.get("OPENAI_TIMEOUT", 60))
    OPENAI_MAX_TOKENS = int(os.environ.get("OPENAI_MAX_TOKENS", 4096))
    OPENAI_TEMPERATURE = float(os.environ.get("OPENAI_TEMPERATURE", 0.2))
    DEFAULT_TIMEOUT = int(os.environ.get("DEFAULT_TIMEOUT", 10))
    UI_AUTOMATION_RUN_TIMEOUT = int(
        os.environ.get("UI_AUTOMATION_RUN_TIMEOUT", 300)
    )
