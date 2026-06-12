from __future__ import annotations

import re

from playwright.sync_api import expect

from pages.base_page import BasePage


class DashboardPage(BasePage):
    def assert_loaded(self):
        expect(self.page.get_by_role("heading", name=re.compile(r"Dashboard|仪表盘"))).to_be_visible()
        return self

