from __future__ import annotations

import re

from playwright.sync_api import expect

from pages.base_page import BasePage


class LoginPage(BasePage):
    username_input = 'input[name="username"]'
    password_input = 'input[name="password"]'

    def login(self, username: str, password: str):
        self.page.locator(self.username_input).fill(username)
        self.page.locator(self.password_input).fill(password)
        self.page.get_by_role("button", name="登录").click()
        return self

    def assert_login_success(self):
        # 登录后应回到仪表盘
        expect(self.page.get_by_role("heading", name=re.compile(r"Dashboard|仪表盘"))).to_be_visible()
        return self
