"""
Module  : framework.ui.driver_factory
Author  : Anil Kalisetti
Purpose : Single entry point that turns configuration into a ready WebDriver.

Two independent choices are combined here:
    WHAT browser   framework.ui.browsers   (chrome | firefox | edge | safari)
    WHERE it runs  framework.ui.targets    (local | remote | saucelabs | browserstack | lambdatest)

Test code never changes between combinations: moving from laptop to cloud is a config change.
"""

from __future__ import annotations

from typing import Any

from framework.config.settings import Settings
from framework.core.logger import get_logger
from framework.ui.browsers import Browser
from framework.ui.targets import ExecutionTarget

log = get_logger("ui.driver")

#: Modes that run on a vendor cloud and have a pass/fail dashboard.
CLOUD_MODES = ("saucelabs", "browserstack", "lambdatest")


def create_driver(settings: Settings, test_name: str = "") -> Any:
    """Return a ready-to-use driver for ``settings.browser`` on ``settings.execution_mode``."""
    browser = Browser.create(settings.browser, settings)
    target = ExecutionTarget.for_settings(settings)

    driver = target.create_driver(browser, test_name)
    driver.set_page_load_timeout(settings.page_load_timeout)
    # Implicit waits are deliberately left at 0: mixing them with explicit waits causes
    # unpredictable delays. All waiting lives in BasePage.
    browser.after_start(driver)
    return driver
