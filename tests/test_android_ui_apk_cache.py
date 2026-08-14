from pathlib import Path

from flask import Flask

import app.services.android_ui_automation_worker as worker_module
from app.services.android_ui_automation_worker import AndroidUiAutomationWorker


def _build_app(tmp_path):
    instance_path = tmp_path / "instance"
    instance_path.mkdir(parents=True, exist_ok=True)
    return Flask(__name__, instance_path=str(instance_path))


class _FakeResponse:
    def __init__(self, chunks, headers=None):
        self._chunks = list(chunks)
        self.headers = headers or {}

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size=0):
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_download_apk_reuses_shared_cache_by_source_manifest(tmp_path, monkeypatch):
    app = _build_app(tmp_path)
    url = "https://example.com/files/demo.apk"

    with app.app_context():
        source_cache = AndroidUiAutomationWorker._source_cache_path(url)
        source_cache.parent.mkdir(parents=True, exist_ok=True)
        source_cache.write_bytes(b"apk-binary")

        final_path = AndroidUiAutomationWorker._finalize_cached_apk(
            url,
            source_cache,
            "com.demo.game",
            [],
        )

        assert final_path.is_file()
        assert final_path.name.startswith("pkg__com.demo.game")
        assert not source_cache.exists()

        def _should_not_download(*args, **kwargs):
            raise AssertionError("network download should not happen when source manifest exists")

        monkeypatch.setattr(worker_module.requests, "get", _should_not_download)

        reused_path, size = AndroidUiAutomationWorker._download_apk(
            url,
            tmp_path / "workspace",
            [],
        )

        assert reused_path == final_path
        assert size == len(b"apk-binary")


def test_download_apk_overwrites_shared_package_cache_for_new_source(tmp_path, monkeypatch):
    app = _build_app(tmp_path)
    url = "https://example.com/files/demo-v2.apk"

    with app.app_context():
        package_cache = AndroidUiAutomationWorker._package_cache_path("com.demo.game")
        package_cache.parent.mkdir(parents=True, exist_ok=True)
        package_cache.write_bytes(b"old-apk")

        calls = []

        def _fake_get(*args, **kwargs):
            calls.append(args[0])
            return _FakeResponse([b"new", b"-apk"], headers={"Content-Length": "7"})

        monkeypatch.setattr(worker_module.requests, "get", _fake_get)

        apk_path, size = AndroidUiAutomationWorker._download_apk(
            url,
            tmp_path / "workspace",
            [],
            package_name_hint="com.demo.game",
        )

        assert calls == [url]
        assert apk_path == package_cache
        assert size == 7
        assert package_cache.read_bytes() == b"new-apk"
