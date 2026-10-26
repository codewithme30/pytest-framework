"""
Module  : framework.ui.cloud_status
Author  : Anil Kalisetti
Purpose : Mark the cloud session PASSED/FAILED so the vendor dashboard matches pytest.

Without this, Sauce Labs / BrowserStack / LambdaTest show every session as "completed"
because they cannot know whether your assertions held.
"""

from __future__ import annotations

import json

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver

from framework.core.logger import get_logger

log = get_logger("ui.cloud_status")


def report_session_status(driver: WebDriver, mode: str, passed: bool, reason: str = "") -> None:
    """Send the verdict using each vendor's documented JavaScript hook; never raises."""
    verdict = "passed" if passed else "failed"
    try:
        if mode == "saucelabs":
            driver.execute_script(f"sauce:job-result={verdict}")
        elif mode == "browserstack":
            payload = {
                "action": "setSessionStatus",
                "arguments": {"status": verdict, "reason": reason[:250]},
            }
            driver.execute_script(f"browserstack_executor: {json.dumps(payload)}")
        elif mode == "lambdatest":
            driver.execute_script(f"lambda-status={verdict}")
    except WebDriverException as exc:
        # A dashboard label must never fail the test run itself.
        log.warning("Could not report %s status to %s: %s", verdict, mode, exc)
