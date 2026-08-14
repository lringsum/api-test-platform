from __future__ import annotations

import os
import re

from playwright.sync_api import expect

from pages.base_page import BasePage


class LoginPage(BasePage):
    username_input = 'input[name="username"]'
    password_input = 'input[name="password"]'
    account_entry_selectors = (
        '[data-testid="account-login-entry"]',
        '[data-testid="password-login-entry"]',
        '[aria-label*="账号"]',
        '[aria-label*="密码"]',
        'img[alt*="天机"]',
        'img[alt*="logo"]',
        '.logo',
        '.brand',
        '.brand-logo',
        '.site-logo',
        '.header-logo',
    )

    def _account_entry_candidates(self):
        custom_selector = os.getenv("APP_LOGIN_ACCOUNT_ENTRY_SELECTOR", "").strip()
        if custom_selector:
            yield self.page.locator(custom_selector).first

        for selector in self.account_entry_selectors:
            yield self.page.locator(selector).first

        for text in ("账号密码登录", "账号登录", "密码登录", "INSIGHTADS", "天机", "投放平台"):
            yield self.page.get_by_text(text, exact=False).first

    def reveal_account_login_if_needed(self):
        username_field = self.page.locator(self.username_input).first
        if username_field.is_visible():
            return self

        for candidate in self._account_entry_candidates():
            try:
                if candidate.is_visible():
                    candidate.click()
                    username_field.wait_for(state="visible", timeout=5000)
                    return self
            except Exception:
                continue

        raise AssertionError("未找到账号密码登录入口，无法展开登录表单。")

    def login(self, username: str, password: str):
        self.reveal_account_login_if_needed()
        self.page.locator(self.username_input).fill(username)
        self.page.locator(self.password_input).fill(password)
        self.page.get_by_role("button", name="登录").click()
        return self

    def assert_login_success(self):
        # 登录后应回到仪表盘
        expect(self.page.get_by_role("heading", name=re.compile(r"Dashboard|仪表盘"))).to_be_visible()
        return self
