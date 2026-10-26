"""
Module  : tests/unit/test_driver_factory.py
Author  : Anil Kalisetti
Purpose : Verify browser options and cloud capabilities WITHOUT starting a browser.

Cloud sessions cost money and need credentials, so the wiring (which capability goes where)
is verified offline; one real smoke run per provider belongs in the nightly pipeline.
"""

from __future__ import annotations

import pytest

pytest.importorskip("selenium")

from framework.config.settings import load_settings  # noqa: E402
from framework.core.exceptions import ConfigurationError  # noqa: E402
from framework.ui import driver_factory as df  # noqa: E402
from framework.ui.cloud_status import report_session_status  # noqa: E402

CREDS = {"GRID_USERNAME": "qa-user", "GRID_ACCESS_KEY": "key-123"}


def _caps(mode: str, **extra: str) -> dict:
    s = load_settings(environ={"EXECUTION_MODE": mode, "BUILD_NAME": "build-9", **CREDS, **extra})
    options = df._build_options(s)
    df._apply_cloud_capabilities(options, s, "test_login")
    return options.to_capabilities()


def test_chrome_options_for_ci_container():
    s = load_settings(environ={"BROWSER": "chrome", "HEADLESS": "true", "CHROME_BINARY": "/usr/bin/chromium"})
    args = df._build_options(s).arguments
    assert "--headless=new" in args
    assert "--no-sandbox" in args  # required for root inside Docker
    assert "--window-size=1920,1080" in args


def test_headed_run_has_no_headless_flag():
    s = load_settings(environ={"HEADLESS": "false"})
    assert "--headless=new" not in df._build_options(s).arguments


def test_firefox_uses_its_own_headless_flag():
    s = load_settings(environ={"BROWSER": "firefox"})
    assert "-headless" in df._build_options(s).arguments


@pytest.mark.parametrize(
    ("mode", "key", "user_field", "name_field"),
    [
        ("saucelabs", "sauce:options", "username", "name"),
        ("browserstack", "bstack:options", "userName", "sessionName"),
        ("lambdatest", "LT:Options", "username", "name"),
    ],
)
def test_cloud_credentials_and_names_land_in_vendor_capabilities(mode, key, user_field, name_field):
    vendor = _caps(mode)[key]
    assert vendor[user_field] == "qa-user"
    assert vendor["accessKey"] == "key-123"
    assert vendor[name_field] == "test_login"


@pytest.mark.parametrize("mode", ["saucelabs", "browserstack", "lambdatest"])
def test_cloud_mode_without_credentials_fails_before_any_network_call(mode):
    s = load_settings(environ={"EXECUTION_MODE": mode})
    with pytest.raises(ConfigurationError, match="credentials"):
        df._apply_cloud_capabilities(df._build_options(s), s, "t")


def test_remote_mode_requires_grid_url():
    with pytest.raises(ConfigurationError, match="GRID_URL"):
        df._resolve_hub_url(load_settings(environ={"EXECUTION_MODE": "remote"}))


def test_grid_url_override_beats_vendor_default():
    s = load_settings(environ={"EXECUTION_MODE": "saucelabs", "GRID_URL": "https://eu.example/wd/hub"})
    assert df._resolve_hub_url(s) == "https://eu.example/wd/hub"


@pytest.mark.parametrize(
    ("mode", "passed", "needle"),
    [
        ("saucelabs", True, "sauce:job-result=passed"),
        ("saucelabs", False, "sauce:job-result=failed"),
        ("browserstack", False, '"status": "failed"'),
        ("lambdatest", True, "lambda-status=passed"),
    ],
)
def test_session_status_uses_vendor_script_hook(mode, passed, needle):
    class FakeDriver:
        scripts: list[str] = []

        def execute_script(self, script: str) -> None:
            self.scripts.append(script)

    driver = FakeDriver()
    report_session_status(driver, mode, passed, reason="assertion failed")
    assert needle in driver.scripts[0]


def test_session_status_failure_never_raises():
    from selenium.common.exceptions import WebDriverException

    class DeadDriver:
        def execute_script(self, script: str) -> None:
            raise WebDriverException("session gone")

    report_session_status(DeadDriver(), "saucelabs", True)  # must not raise
