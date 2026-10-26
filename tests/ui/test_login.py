"""
Module  : tests/ui/test_login.py
Author  : Anil Kalisetti
Purpose : Authentication: valid users, every invalid-input class, locked accounts, input hygiene.

Application under test: SauceDemo (https://www.saucedemo.com), a public retail demo from
Sauce Labs. Its credentials are published on the login page itself, so they are safe to commit.
"""

from __future__ import annotations

import pytest

from framework.ui.pages import InventoryPage

pytestmark = pytest.mark.network


@pytest.mark.smoke
@pytest.mark.critical
@pytest.mark.parametrize("user_key", ["standard_user", "problem_user", "performance_glitch_user"])
def test_valid_user_reaches_the_product_page(driver, settings, login_page, users, user_key):
    login_page.login_as(**users[user_key])
    assert InventoryPage(driver, settings.explicit_wait).is_loaded()


INVALID_LOGINS = [
    pytest.param("standard_user", "wrong_password", "do not match", id="wrong-password"),
    pytest.param("unknown_user", "secret_sauce", "do not match", id="unknown-user"),
    pytest.param("STANDARD_USER", "secret_sauce", "do not match", id="username-is-case-sensitive"),
    pytest.param("standard_user", "SECRET_SAUCE", "do not match", id="password-is-case-sensitive"),
    pytest.param("", "secret_sauce", "Username is required", id="empty-username"),
    pytest.param("standard_user", "", "Password is required", id="empty-password"),
    pytest.param("", "", "Username is required", id="both-empty"),
    pytest.param("standard_user' OR '1'='1", "x", "do not match", id="sql-injection-in-username"),
    pytest.param("<script>alert(1)</script>", "x", "do not match", id="script-tag-in-username"),
    pytest.param("a" * 500, "x", "do not match", id="500-character-username"),
    pytest.param("标准用户", "密码", "do not match", id="non-latin-characters"),
]


@pytest.mark.regression
@pytest.mark.parametrize(("username", "password", "expected_error"), INVALID_LOGINS)
def test_invalid_credentials_show_a_clear_error_and_stay_on_login(login_page, username, password, expected_error):
    login_page.login_as(username, password)
    assert login_page.has_error()
    assert expected_error in login_page.error_message
    assert "inventory" not in login_page.current_url


@pytest.mark.regression
def test_locked_out_user_is_refused_with_explanation(login_page, users):
    login_page.login_as(**users["locked_out_user"])
    assert "locked out" in login_page.error_message


@pytest.mark.regression
def test_password_field_masks_typed_characters(login_page):
    assert login_page.attribute_of(login_page.PASSWORD, "type") == "password"


@pytest.mark.regression
def test_successful_login_after_a_failed_attempt(driver, settings, login_page, users):
    login_page.login_as("standard_user", "wrong")
    assert login_page.has_error()
    login_page.login_as(**users["standard_user"])
    assert InventoryPage(driver, settings.explicit_wait).is_loaded()
