from __future__ import annotations

from playwright.sync_api import Page, expect


class BasePage:
    def __init__(self, page: Page):
        self.page = page

    def open(self, url: str):
        self.page.goto(url, wait_until="domcontentloaded")
        return self

    def wait_for_ready(self):
        expect(self.page.locator("body")).to_be_visible()
        return self

