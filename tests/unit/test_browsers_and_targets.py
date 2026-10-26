"""
Module  : tests/unit/test_browsers_and_targets.py
Author  : Anil Kalisetti
Purpose : Browser classes, execution targets and the driver factory, verified with a fake
          Selenium so no browser, cloud account or network is needed.
"""

from __future__ import annotations

import pytest

from framework.config.settings import BROWSERS, EXECUTION_MODES, load_settings
from framework.core.exceptions import ConfigurationError
from framework.ui.browsers import Browser, ChromiumBrowser, resolve_browsers
from framework.ui.driver_factory import create_driver
from framework.ui.targets import ExecutionTarget

CREDS = {"GRID_USERNAME": "qa-user", "GRID_ACCESS_KEY": "key-123"}


def _settings(**env: str):
    return load_settings(environ=env)


# --- registries stay in step with configuration -------------------------------------------------
def test_every_configurable_browser_has_a_class_and_vice_versa():
    assert set(Browser.names()) == set(BROWSERS)


def test_every_configurable_execution_mode_has_a_target_class_and_vice_versa():
    assert set(ExecutionTarget.modes()) == set(EXECUTION_MODES)


def test_abstract_classes_cannot_be_instantiated():
    for abstract in (Browser, ChromiumBrowser, ExecutionTarget):
        with pytest.raises(TypeError):
            abstract(_settings())


def test_new_browser_is_one_subclass_with_no_other_change(monkeypatch, fake_selenium):
    """Open/closed principle: adding Brave means writing Brave, nothing else."""
    monkeypatch.setitem(Browser._registry, "brave", None)  # restored on teardown

    class Brave(ChromiumBrowser):
        name = "brave"

        def _new_options(self):
            from selenium.webdriver.chrome.options import Options

            return Options()

        def start_local(self, options):
            return options

    assert "brave" in Browser.names()
    assert Browser.create("brave", _settings()).build_options().arguments  # shared Chromium flags reused


def test_unknown_browser_is_rejected_with_the_valid_choices():
    with pytest.raises(ConfigurationError, match="chrome"):
        Browser.create("netscape", _settings())


# --- resolve_browsers (--ui-browsers) ---------------------------------------------------------------
@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        (None, ["chrome"]),
        ("", ["chrome"]),
        ("firefox", ["firefox"]),
        ("chrome,firefox", ["chrome", "firefox"]),
        (" Chrome , FIREFOX ,chrome", ["chrome", "firefox"]),  # trims, lower-cases, de-duplicates
        ("all", ["chrome", "edge", "firefox"]),  # safari needs macOS or a cloud grid
    ],
)
def test_resolve_browsers(requested, expected):
    assert sorted(resolve_browsers(requested, "chrome")) == sorted(expected)


def test_resolve_browsers_keeps_the_order_given():
    assert resolve_browsers("firefox,chrome", "chrome") == ["firefox", "chrome"]


def test_resolve_browsers_rejects_typos():
    with pytest.raises(ConfigurationError, match="chrom"):
        resolve_browsers("chrom", "chrome")


# --- browser options --------------------------------------------------------------------------------------
def test_chrome_options_for_ci_container(fake_selenium):
    s = _settings(BROWSER="chrome", HEADLESS="true", CHROME_BINARY="/usr/bin/chromium")
    options = Browser.create("chrome", s).build_options()
    assert "--headless=new" in options.arguments
    assert "--no-sandbox" in options.arguments  # required for root inside Docker
    assert "--window-size=1920,1080" in options.arguments
    assert options.binary_location == "/usr/bin/chromium"


def test_headed_run_has_no_headless_flag(fake_selenium):
    options = Browser.create("chrome", _settings(HEADLESS="false")).build_options()
    assert "--headless=new" not in options.arguments


def test_edge_shares_chromium_flags_but_ignores_chrome_binary(fake_selenium):
    options = Browser.create("edge", _settings(BROWSER="edge", CHROME_BINARY="/usr/bin/chromium")).build_options()
    assert "--headless=new" in options.arguments
    assert options.binary_location is None


def test_firefox_uses_its_own_flags(fake_selenium):
    options = Browser.create("firefox", _settings(BROWSER="firefox")).build_options()
    assert "-headless" in options.arguments
    assert "--width=1920" in options.arguments and "--height=1080" in options.arguments


def test_safari_builds_options_without_headless_support(fake_selenium):
    options = Browser.create("safari", _settings(BROWSER="safari", HEADLESS="true")).build_options()
    assert options.arguments == []


# --- targets: capabilities ---------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("mode", "key", "user_field", "name_field"),
    [
        ("saucelabs", "sauce:options", "username", "name"),
        ("browserstack", "bstack:options", "userName", "sessionName"),
        ("lambdatest", "LT:Options", "username", "name"),
    ],
)
def test_cloud_credentials_and_names_land_in_vendor_capabilities(fake_selenium, mode, key, user_field, name_field):
    s = _settings(EXECUTION_MODE=mode, BUILD_NAME="build-9", **CREDS)
    options = Browser.create("chrome", s).build_options()
    ExecutionTarget.for_settings(s).apply_capabilities(options, "test_login")
    vendor = options.capabilities[key]
    assert vendor[user_field] == "qa-user"
    assert vendor["accessKey"] == "key-123"
    assert vendor[name_field] == "test_login"
    assert "build-9" in vendor.values()
    assert options.capabilities["platformName"] == s.platform_name


@pytest.mark.parametrize("mode", ["saucelabs", "browserstack", "lambdatest"])
def test_cloud_mode_without_credentials_fails_before_any_network_call(fake_selenium, mode):
    s = _settings(EXECUTION_MODE=mode)
    with pytest.raises(ConfigurationError, match="credentials"):
        ExecutionTarget.for_settings(s).create_driver(Browser.create("chrome", s), "t")
    assert fake_selenium.drivers == []  # nothing was started


def test_remote_mode_requires_grid_url(fake_selenium):
    s = _settings(EXECUTION_MODE="remote")
    with pytest.raises(ConfigurationError, match="GRID_URL"):
        create_driver(s)


def test_grid_url_override_beats_vendor_default(fake_selenium):
    s = _settings(EXECUTION_MODE="saucelabs", GRID_URL="https://eu.example/wd/hub", **CREDS)
    create_driver(s)
    assert fake_selenium.drivers[0].kwargs["command_executor"] == "https://eu.example/wd/hub"


@pytest.mark.parametrize(
    ("mode", "host"),
    [("saucelabs", "saucelabs.com"), ("browserstack", "browserstack.com"), ("lambdatest", "lambdatest.com")],
)
def test_each_cloud_has_a_default_hub(fake_selenium, mode, host):
    create_driver(_settings(EXECUTION_MODE=mode, **CREDS))
    assert host in fake_selenium.drivers[0].kwargs["command_executor"]


# --- create_driver end to end (fake Selenium) ---------------------------------------------------------------
@pytest.mark.parametrize("browser", ["chrome", "firefox", "edge", "safari"])
def test_local_mode_starts_the_requested_browser(fake_selenium, browser):
    driver = create_driver(_settings(BROWSER=browser, PAGE_LOAD_TIMEOUT="45"))
    assert driver.kind == browser
    assert driver.page_load_timeout == 45


def test_remote_mode_starts_a_remote_session_with_options(fake_selenium):
    driver = create_driver(_settings(EXECUTION_MODE="remote", GRID_URL="http://grid:4444/wd/hub"))
    assert driver.kind == "remote"
    assert driver.kwargs["command_executor"] == "http://grid:4444/wd/hub"
    assert "--headless=new" in driver.kwargs["options"].arguments


def test_headed_firefox_gets_its_window_size_after_start(fake_selenium):
    driver = create_driver(_settings(BROWSER="firefox", HEADLESS="false"))
    assert driver.window_size == (1920, 1080)


def test_headless_firefox_needs_no_window_resize(fake_selenium):
    assert create_driver(_settings(BROWSER="firefox", HEADLESS="true")).window_size is None


# --- pass/fail reporting to the vendor dashboard -----------------------------------------------------------------
@pytest.mark.parametrize(
    ("mode", "passed", "needle"),
    [
        ("saucelabs", True, "sauce:job-result=passed"),
        ("saucelabs", False, "sauce:job-result=failed"),
        ("browserstack", False, '"status": "failed"'),
        ("lambdatest", True, "lambda-status=passed"),
    ],
)
def test_session_status_uses_the_vendor_script_hook(fake_selenium, mode, passed, needle):
    driver = create_driver(_settings(EXECUTION_MODE=mode, **CREDS))
    ExecutionTarget.for_settings(_settings(EXECUTION_MODE=mode, **CREDS)).report_status(driver, passed, "assertion failed")
    assert needle in driver.scripts[0]


@pytest.mark.parametrize("mode", ["local", "remote"])
def test_targets_without_a_dashboard_ignore_status(fake_selenium, mode):
    driver = create_driver(_settings(EXECUTION_MODE=mode, GRID_URL="http://grid/wd/hub"))
    ExecutionTarget.for_settings(_settings(EXECUTION_MODE=mode, GRID_URL="http://grid/wd/hub")).report_status(driver, False)
    assert driver.scripts == []


def test_status_reporting_failure_never_raises(fake_selenium):
    class DeadDriver:
        def execute_script(self, script):
            raise RuntimeError("session gone")

    ExecutionTarget.for_settings(_settings(EXECUTION_MODE="saucelabs", **CREDS)).report_status(DeadDriver(), True)


def test_lambdatest_requests_w3c_protocol(fake_selenium):
    s = _settings(EXECUTION_MODE="lambdatest", **CREDS)
    options = Browser.create("chrome", s).build_options()
    ExecutionTarget.for_settings(s).apply_capabilities(options, "t")
    assert options.capabilities["LT:Options"]["w3c"] is True
