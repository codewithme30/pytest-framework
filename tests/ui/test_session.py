"""
Module  : tests/ui/test_session.py
Author  : Anil Kalisetti
Purpose : Session handling: logout, protected pages without a session, session surviving refresh.
"""

from __future__ import annotations

import pytest

from framework.ui.pages import LoginPage

pytestmark = pytest.mark.network


@pytest.mark.smoke
def test_logout_returns_to_the_login_screen(driver, settings, inventory_page):
    inventory_page.logout()
    assert LoginPage(driver, settings.explicit_wait).is_visible(LoginPage.LOGIN_BUTTON)


@pytest.mark.regression
@pytest.mark.parametrize("protected_path", ["inventory.html", "cart.html", "checkout-step-one.html"])
def test_protected_pages_redirect_anonymous_visitors_to_login(driver, settings, protected_path):
    page = LoginPage(driver, settings.explicit_wait)
    page.open(f"{settings.base_ui_url.rstrip('/')}/{protected_path}")
    assert page.has_error()
    assert "logged in" in page.error_message


@pytest.mark.regression
def test_session_survives_a_page_refresh(inventory_page):
    inventory_page.refresh()
    assert inventory_page.is_loaded()


@pytest.mark.regression
def test_protected_page_is_unreachable_after_logout(driver, settings, inventory_page):
    inventory_page.logout()
    page = LoginPage(driver, settings.explicit_wait)
    page.open(f"{settings.base_ui_url.rstrip('/')}/inventory.html")
    assert page.has_error()
