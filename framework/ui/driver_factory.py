"""
Module  : framework.ui.driver_factory
Author  : Anil Kalisetti
Purpose : Create a Selenium WebDriver for any execution target from configuration alone.

Targets (``EXECUTION_MODE``):
    local         browser on this machine (Selenium Manager downloads the driver)
    remote        any Selenium Grid / Selenoid / Zalenium at ``GRID_URL``
    saucelabs     Sauce Labs cloud   (credentials: SAUCE_USERNAME / SAUCE_ACCESS_KEY)
    browserstack  BrowserStack cloud (credentials: BROWSERSTACK_USERNAME / BROWSERSTACK_ACCESS_KEY)
    lambdatest    LambdaTest cloud   (credentials: LT_USERNAME / LT_ACCESS_KEY)

Test code never changes between targets: switching from laptop to cloud is a config change.
"""

from __future__ import annotations

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.options import ArgOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.remote.webdriver import WebDriver

from framework.config.settings import Settings
from framework.core.exceptions import ConfigurationError
from framework.core.logger import get_logger

log = get_logger("ui.driver")

CLOUD_MODES = ("saucelabs", "browserstack", "lambdatest")

# Default hub endpoints. Override with GRID_URL (e.g. EU data centre or a private tunnel).
# Verify against your provider's dashboard: regions and hostnames differ per account.
_CLOUD_HUBS = {
    "saucelabs": "https://ondemand.us-west-1.saucelabs.com:443/wd/hub",
    "browserstack": "https://hub-cloud.browserstack.com/wd/hub",
    "lambdatest": "https://hub.lambdatest.com/wd/hub",
}


def create_driver(settings: Settings, test_name: str = "") -> WebDriver:
    """Return a ready-to-use driver for ``settings.execution_mode``."""
    options = _build_options(settings)
    mode = settings.execution_mode

    if mode == "local":
        driver = _create_local(settings.browser, options)
    else:
        _apply_cloud_capabilities(options, settings, test_name)
        hub = _resolve_hub_url(settings)
        log.info("Starting remote session mode=%s hub=%s test=%s", mode, hub, test_name)
        driver = webdriver.Remote(command_executor=hub, options=options)

    driver.set_page_load_timeout(settings.page_load_timeout)
    # Implicit waits are deliberately left at 0: mixing them with explicit waits causes
    # unpredictable delays. All waiting lives in BasePage.
    if settings.browser == "firefox" and not settings.headless:
        driver.set_window_size(*_window_size(settings))
    return driver


def _window_size(settings: Settings) -> tuple[int, int]:
    width, height = settings.window_size.split(",")
    return int(width), int(height)


def _build_options(settings: Settings) -> ArgOptions:
    width, height = settings.window_size.split(",")
    if settings.browser == "firefox":
        options: ArgOptions = FirefoxOptions()
        if settings.headless:
            options.add_argument("-headless")
        options.add_argument(f"--width={width}")
        options.add_argument(f"--height={height}")
    else:
        options = ChromeOptions() if settings.browser == "chrome" else EdgeOptions()
        if settings.headless:
            options.add_argument("--headless=new")
        options.add_argument(f"--window-size={width},{height}")
        # Required when running as root inside Docker / CI containers.
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        if settings.chrome_binary:
            options.binary_location = settings.chrome_binary
    return options


def _create_local(browser: str, options: ArgOptions) -> WebDriver:
    factories = {
        "chrome": webdriver.Chrome,
        "firefox": webdriver.Firefox,
        "edge": webdriver.Edge,
    }
    return factories[browser](options=options)


def _resolve_hub_url(settings: Settings) -> str:
    hub = settings.grid_url or _CLOUD_HUBS.get(settings.execution_mode, "")
    if not hub:
        raise ConfigurationError("EXECUTION_MODE=remote requires GRID_URL (e.g. http://host:4444/wd/hub)")
    return hub


def _apply_cloud_capabilities(options: ArgOptions, settings: Settings, test_name: str) -> None:
    """Attach provider specific capabilities. Credentials travel as capabilities, not in the URL."""
    mode = settings.execution_mode
    if mode == "remote":
        return  # plain grid: nothing vendor specific (auth, if any, belongs in GRID_URL)

    if not (settings.grid_username and settings.grid_access_key):
        raise ConfigurationError(
            f"EXECUTION_MODE={mode} requires credentials; set the provider's username/access-key "
            "environment variables (see .env.example)"
        )

    build = settings.build_name or "local-run"
    options.set_capability("browserVersion", settings.browser_version)
    options.set_capability("platformName", settings.platform_name)

    if mode == "saucelabs":
        options.set_capability(
            "sauce:options",
            {
                "username": settings.grid_username,
                "accessKey": settings.grid_access_key,
                "build": build,
                "name": test_name,
            },
        )
    elif mode == "browserstack":
        options.set_capability(
            "bstack:options",
            {
                "userName": settings.grid_username,
                "accessKey": settings.grid_access_key,
                "buildName": build,
                "sessionName": test_name,
            },
        )
    elif mode == "lambdatest":
        options.set_capability(
            "LT:Options",
            {
                "username": settings.grid_username,
                "accessKey": settings.grid_access_key,
                "build": build,
                "name": test_name,
                "w3c": True,
            },
        )
    # TODO(future): device/OS matrix. Load config/cloud_matrix.yaml and parametrize the `driver`
    # fixture over it, e.g. [("Windows 11","chrome"),("macOS 14","safari"),("Pixel 8","chrome")].
    # BrowserStack expects "os"/"osVersion" inside bstack:options instead of platformName;
    # Sauce Labs real devices use "appium:deviceName". Keep that mapping inside this function.
