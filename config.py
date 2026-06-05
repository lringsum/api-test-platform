import os


BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _normalize_database_url(url):
    if not url:
        return url
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://") :]
    return url


def _default_database_url():
    if os.environ.get("VERCEL"):
        return "sqlite:////tmp/api-test-platform.db"
    return "sqlite:///" + os.path.join(BASE_DIR, "instance", "app.db")


def _resolve_database_url():
    for env_name in (
        "DATABASE_URL",
        "POSTGRES_URL_NON_POOLING",
        "POSTGRES_URL",
        "POSTGRES_PRISMA_URL",
    ):
        value = os.environ.get(env_name)
        if value:
            return _normalize_database_url(value)
    return _default_database_url()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = int(os.environ.get("PORT", 5000))
    DEBUG = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    SQLALCHEMY_DATABASE_URI = _resolve_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
    JSON_AS_ASCII = False
    AI_MODE = os.environ.get("AI_MODE", "mock")
    DEFAULT_TIMEOUT = int(os.environ.get("DEFAULT_TIMEOUT", 10))
