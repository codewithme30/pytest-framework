"""
Module  : tests/ui/conftest.py
Author  : Anil Kalisetti
Purpose : Browser fixtures. One fresh browser per test = full isolation (no shared cookies/cart).

Multi-browser: ``pytest --ui-browsers chrome,firefox`` (or ``all``) runs every UI test once per
browser. Test ids gain a ``[chrome]`` / ``[firefox]`` suffix. Without the option, the single
configured browser is used and ids stay unchanged.

Failure screenshots are taken by framework.plugins.evidence_plugin when a test using the
``driver`` fixture fails; cloud sessions are marked passed/failed here on teardown.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from selenium.webdriver.remote.webdriver import WebDriver

from framework.config.settings import Settings
from framework.core.data_loader import load_data
from framework.plugins.stash import ensure_settings
from framework.ui.browsers import resolve_browsers
from framework.ui.driver_factory import create_driver
from framework.ui.healing import FingerprintStore, LocatorHealer
from framework.ui.healing.transport import export_properties
from framework.ui.targets import ExecutionTarget
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


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Fan a test out over every browser requested with --ui-browsers (only when more than one)."""
    if "browser_name" not in metafunc.fixturenames:
        return
    browsers = resolve_browsers(metafunc.config.getoption("ui_browsers"), ensure_settings(metafunc.config).browser)
    if len(browsers) > 1:
        metafunc.parametrize("browser_name", browsers, indirect=True, scope="function")


@pytest.fixture
def browser_name(request: pytest.FixtureRequest, settings: Settings) -> str:
    """Browser for this test: the parametrized one, else the configured default."""
    return getattr(request, "param", None) or settings.browser


@pytest.fixture
def driver(request: pytest.FixtureRequest, settings: Settings, browser_name: str) -> Iterator[WebDriver]:
    run_settings = dataclasses.replace(settings, browser=browser_name)
    browser = create_driver(run_settings, test_name=request.node.name)
    yield browser
    try:
        call_report = getattr(request.node, "rep_call", None)
        passed = bool(call_report and call_report.passed)  # no call report => setup failed
        # Local/remote targets ignore this; cloud targets mark the vendor dashboard.
        ExecutionTarget.for_settings(run_settings).report_status(browser, passed)
    finally:
        browser.quit()


@pytest.fixture(scope="session")
def fingerprint_store(settings: Settings) -> FingerprintStore:
    """The committed locator baseline. Read-only during normal runs."""
    return FingerprintStore.load(settings.locator_baseline_path)


@pytest.fixture
def healer(
    request: pytest.FixtureRequest, driver: WebDriver, settings: Settings, fingerprint_store: FingerprintStore
) -> Iterator[LocatorHealer]:
    """Self-healing for this browser session; what it did is reported through user_properties."""
    instance = LocatorHealer.from_settings(driver, settings, fingerprint_store)
    yield instance
    request.node.user_properties.extend(export_properties(instance))


@pytest.fixture
def login_page(driver: WebDriver, settings: Settings, healer: LocatorHealer) -> LoginPage:
    """Login screen, opened and ready (not logged in)."""
    return LoginPage(driver, settings.explicit_wait, healer).load(settings.base_ui_url)


@pytest.fixture
def inventory_page(
    driver: WebDriver, settings: Settings, healer: LocatorHealer, login_page: LoginPage, users: dict[str, Any]
) -> InventoryPage:
    """Product page after a successful login as the standard user."""
    login_page.login_as(**users["standard_user"])
    page = InventoryPage(driver, settings.explicit_wait, healer)
    assert page.is_loaded(), "precondition failed: standard_user could not log in"
    return page


@pytest.fixture
def cart_page(driver: WebDriver, settings: Settings, healer: LocatorHealer) -> CartPage:
    return CartPage(driver, settings.explicit_wait, healer)


@pytest.fixture
def checkout_page(driver: WebDriver, settings: Settings, healer: LocatorHealer) -> CheckoutPage:
    return CheckoutPage(driver, settings.explicit_wait, healer)
