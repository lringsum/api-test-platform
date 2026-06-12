from __future__ import annotations

import os

import pytest
from playwright.sync_api import expect

from pages.login_page import LoginPage


def pytest_addoption(parser):
    parser.addoption("--base-url", action="store", default=os.getenv("APP_BASE_URL", "http://127.0.0.1:5000"))
    parser.addoption("--username", action="store", default=os.getenv("APP_USERNAME", "admin"))
    parser.addoption("--password", action="store", default=os.getenv("APP_PASSWORD", "admin123"))


@pytest.fixture(scope="session")
def base_url(pytestconfig):
    return pytestconfig.getoption("--base-url").rstrip("/")


@pytest.fixture(scope="session")
def credentials(pytestconfig):
    return {
        "username": pytestconfig.getoption("--username"),
        "password": pytestconfig.getoption("--password"),
    }


@pytest.fixture
def login_page(page, base_url):
    page.goto(f"{base_url}/login", wait_until="domcontentloaded")
    return LoginPage(page)


@pytest.fixture
def authenticated_page(login_page, credentials):
    login_page.login(credentials["username"], credentials["password"])
    login_page.assert_login_success()
    return login_page.page


@pytest.fixture
def soft_assert():
    """一个很轻的断言入口，后面你可以替换成自己的报告记录器。"""

    def _assert(condition, message="断言失败"):
        assert condition, message

    return _assert

