import os


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_AAPT_PATH = os.path.join(BASE_DIR, "tools", "android", "aapt.exe")


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
    AUTO_DB_BOOTSTRAP = os.environ.get("AUTO_DB_BOOTSTRAP", "false").lower() == "true"
    AUTO_DB_COMPAT_PATCH = os.environ.get("AUTO_DB_COMPAT_PATCH", "false").lower() == "true"
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
    JSON_AS_ASCII = False
    DEFAULT_TIMEOUT = int(os.environ.get("DEFAULT_TIMEOUT", 10))
    UI_AUTOMATION_RUN_TIMEOUT = int(
        os.environ.get("UI_AUTOMATION_RUN_TIMEOUT", 300)
    )
    UI_AUTOMATION_WORKER_HEARTBEAT_INTERVAL = float(
        os.environ.get("UI_AUTOMATION_WORKER_HEARTBEAT_INTERVAL", 5)
    )
    UI_AUTOMATION_WORKER_STALE_SECONDS = int(
        os.environ.get("UI_AUTOMATION_WORKER_STALE_SECONDS", 30)
    )
    UI_AUTOMATION_RUN_STALE_SECONDS = int(
        os.environ.get("UI_AUTOMATION_RUN_STALE_SECONDS", 90)
    )
    UI_AUTOMATION_ARTIFACT_KEEP_LATEST_RUNS = int(
        os.environ.get("UI_AUTOMATION_ARTIFACT_KEEP_LATEST_RUNS", 30)
    )
    ANDROID_UI_WORKER_HEARTBEAT_INTERVAL = float(
        os.environ.get("ANDROID_UI_WORKER_HEARTBEAT_INTERVAL", 5)
    )
    ANDROID_UI_WORKER_STALE_SECONDS = int(
        os.environ.get("ANDROID_UI_WORKER_STALE_SECONDS", 30)
    )
    ANDROID_UI_RUN_STALE_SECONDS = int(
        os.environ.get("ANDROID_UI_RUN_STALE_SECONDS", 1800)
    )
    ANDROID_UI_WORKSPACE_KEEP_LATEST_RUNS = int(
        os.environ.get("ANDROID_UI_WORKSPACE_KEEP_LATEST_RUNS", 30)
    )
    ANDROID_UI_AUTO_START_DEVICE = (
        os.environ.get("ANDROID_UI_AUTO_START_DEVICE", "true").lower() == "true"
    )
    ANDROID_UI_DEVICE_START_WAIT_SECONDS = int(
        os.environ.get("ANDROID_UI_DEVICE_START_WAIT_SECONDS", 90)
    )
    ANDROID_UI_ADB_PATH = os.environ.get(
        "ANDROID_UI_ADB_PATH",
        r"C:\Program Files\Netease\MuMu\nx_main\adb.exe",
    )
    ANDROID_UI_AAPT_PATH = os.environ.get(
        "ANDROID_UI_AAPT_PATH",
        PROJECT_AAPT_PATH,
    )
    ANDROID_UI_DOWNLOAD_CONNECT_TIMEOUT_SECONDS = float(
        os.environ.get("ANDROID_UI_DOWNLOAD_CONNECT_TIMEOUT_SECONDS", 20)
    )
    ANDROID_UI_DOWNLOAD_READ_TIMEOUT_SECONDS = float(
        os.environ.get("ANDROID_UI_DOWNLOAD_READ_TIMEOUT_SECONDS", 60)
    )
    ANDROID_UI_DOWNLOAD_MAX_SECONDS = float(
        os.environ.get("ANDROID_UI_DOWNLOAD_MAX_SECONDS", 1800)
    )
    ANDROID_UI_DOWNLOAD_CHUNK_BYTES = int(
        os.environ.get("ANDROID_UI_DOWNLOAD_CHUNK_BYTES", 524288)
    )
