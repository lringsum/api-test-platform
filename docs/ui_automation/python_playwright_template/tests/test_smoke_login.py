import re

from playwright.sync_api import expect

from pages.dashboard_page import DashboardPage


def test_admin_can_login_and_open_dashboard(authenticated_page):
    dashboard = DashboardPage(authenticated_page)
    dashboard.assert_loaded()
    expect(authenticated_page.locator("body")).to_contain_text(re.compile(r"API 测试平台|Dashboard"))

