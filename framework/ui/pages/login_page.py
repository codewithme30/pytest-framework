"""
Module  : framework.ui.pages.login_page
Author  : Anil Kalisetti
Purpose : Login screen of the sample retail application.
"""

from __future__ import annotations

from framework.ui.base_page import BasePage, css


class LoginPage(BasePage):
    # Fallbacks are the author's "if the id ever changes, try these" list (self-healing).
    USERNAME = css("#user-name", fallbacks=['[data-test="username"]', 'input[name="user-name"]'])
    PASSWORD = css("#password", fallbacks=['[data-test="password"]', 'input[type="password"]'])
    LOGIN_BUTTON = css("#login-button", fallbacks=['[data-test="login-button"]', 'input[type="submit"]'])
    ERROR = css('[data-test="error"]')

    def is_loaded(self) -> bool:
        return self.is_visible(self.LOGIN_BUTTON)

    def load(self, base_url: str) -> LoginPage:
        self.open(base_url)
        self.find(self.LOGIN_BUTTON)
        return self

    def login_as(self, username: str, password: str) -> None:
        """Fill the form and submit. Empty strings are typed as empty (negative tests)."""
        self.type_text(self.USERNAME, username)
        self.type_text(self.PASSWORD, password)
        self.click(self.LOGIN_BUTTON)

    @property
    def error_message(self) -> str:
        return self.text_of(self.ERROR)

    def has_error(self) -> bool:
        return self.is_visible(self.ERROR)
