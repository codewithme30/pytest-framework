"""
Module  : tests/unit/test_driver_factory.py
Author  : Anil Kalisetti
Purpose : The same wiring checks as test_browsers_and_targets, but against REAL Selenium option
          classes, to prove the fake used offline still matches the library.

Skipped automatically when Selenium is not installed.
"""

from __future__ import annotations

import pytest

pytest.importorskip("selenium")

from framework.config.settings import load_settings  # noqa: E402
from framework.ui.browsers import Browser  # noqa: E402
from framework.ui.targets import ExecutionTarget  # noqa: E402

CREDS = {"GRID_USERNAME": "qa-user", "GRID_ACCESS_KEY": "key-123"}


def test_real_chrome_options_for_ci_container():
    s = load_settings(environ={"BROWSER": "chrome", "HEADLESS": "true", "CHROME_BINARY": "/usr/bin/chromium"})
    options = Browser.create("chrome", s).build_options()
    assert {"--headless=new", "--no-sandbox", "--window-size=1920,1080"} <= set(options.arguments)
    assert options.binary_location == "/usr/bin/chromium"


@pytest.mark.parametrize("browser", ["chrome", "firefox", "edge", "safari"])
def test_every_browser_produces_real_w3c_capabilities(browser):
    options = Browser.create(browser, load_settings(environ={"BROWSER": browser})).build_options()
    assert options.to_capabilities()["browserName"]


@pytest.mark.parametrize(
    ("mode", "key"),
    [("saucelabs", "sauce:options"), ("browserstack", "bstack:options"), ("lambdatest", "LT:Options")],
)
def test_real_options_carry_vendor_capabilities(mode, key):
    s = load_settings(environ={"EXECUTION_MODE": mode, "BUILD_NAME": "build-9", **CREDS})
    options = Browser.create("chrome", s).build_options()
    ExecutionTarget.for_settings(s).apply_capabilities(options, "test_login")
    assert options.to_capabilities()[key]["accessKey"] == "key-123"
