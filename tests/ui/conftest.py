"""
Module  : tests/ui/conftest.py
Author  : Anil Kalisetti
Purpose : Browser fixtures. One fresh browser per test = full isolation (no shared cookies/cart).

Failure screenshots are taken by framework.plugins.evidence_plugin when a test using the
``driver`` fixture fails; cloud sessions are marked passed/failed here on teardown.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from selenium.webdriver.remote.webdriver import WebDriver

from framework.config.settings import Settings
from framework.core.data_loader import load_data
from framework.ui.cloud_status import report_session_status
from framework.ui.driver_factory import CLOUD_MODES, create_driver
from framework.ui.pages import CartPage, CheckoutPage, InventoryPage, LoginPage

USERS_FILE = Path(__file__).parent / "test_data" / "users.json"

PRODUCTS = [
    "Sauce Labs Backpack",
    "Sauce Labs Bike Light",
    "Sauce Labs Bolt T-Shirt",
    "Sauce Labs Fleece Jacket",
    "Sauce Labs Onesie",
    "Test.allTheThings() T-Shirt (Red)",
]


@pytest.fixture(scope="session")
def users() -> dict[str, Any]:
    return load_data(USERS_FILE)


@pytest.fixture(scope="session")
def products() -> list[str]:
    return list(PRODUCTS)


@pytest.fixture
def driver(request: pytest.FixtureRequest, settings: Settings) -> Iterator[WebDriver]:
    browser = create_driver(settings, test_name=request.node.name)
    yield browser
    try:
        if settings.execution_mode in CLOUD_MODES:
            call_report = getattr(request.node, "rep_call", None)
            passed = bool(call_report and call_report.passed)  # no call report => setup failed
            report_session_status(browser, settings.execution_mode, passed)
    finally:
        browser.quit()


@pytest.fixture
def login_page(driver: WebDriver, settings: Settings) -> LoginPage:
    """Login screen, opened and ready (not logged in)."""
    return LoginPage(driver, settings.explicit_wait).load(settings.base_ui_url)


@pytest.fixture
def inventory_page(driver: WebDriver, settings: Settings, login_page: LoginPage, users: dict[str, Any]) -> InventoryPage:
    """Product page after a successful login as the standard user."""
    login_page.login_as(**users["standard_user"])
    page = InventoryPage(driver, settings.explicit_wait)
    assert page.is_loaded(), "precondition failed: standard_user could not log in"
    return page


@pytest.fixture
def cart_page(driver: WebDriver, settings: Settings) -> CartPage:
    return CartPage(driver, settings.explicit_wait)


@pytest.fixture
def checkout_page(driver: WebDriver, settings: Settings) -> CheckoutPage:
    return CheckoutPage(driver, settings.explicit_wait)
