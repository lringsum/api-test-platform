from pathlib import Path

from flask import Blueprint, current_app, send_from_directory


spa_bp = Blueprint("spa", __name__, url_prefix="/app")


def _dist_directory():
    return Path(current_app.root_path).parent / "frontend" / "dist"


@spa_bp.route("/", defaults={"asset_path": ""})
@spa_bp.route("/<path:asset_path>")
def index(asset_path):
    """Serve the Vue build and let the client router resolve application paths."""
    dist_dir = _dist_directory()
    requested_asset = dist_dir / asset_path
    if asset_path and requested_asset.is_file():
        return send_from_directory(dist_dir, asset_path)
    return send_from_directory(dist_dir, "index.html")
