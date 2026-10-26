"""
Module  : framework.ui.targets
Author  : Anil Kalisetti
Purpose : WHERE a browser runs: this laptop, a Selenium Grid, or a cloud provider.

Class hierarchy
    ExecutionTarget (abstract)
        LocalTarget             browser on this machine
        GridTarget              any Selenium Grid / Selenoid at GRID_URL
            CloudTarget (abstract)    shared cloud rules: credentials, build label, status
                SauceLabsTarget
                BrowserStackTarget
                LambdaTestTarget

Design patterns
    Strategy         the target is chosen from configuration; tests never know which one runs.
    Template method  ``create_driver`` fixes the order of steps; subclasses fill in the steps.
    Polymorphism     ``report_status`` means a different JavaScript hook for each vendor.

Real-life example: the same login test runs on a laptop while debugging, on a Grid in CI at
night, and on Sauce Labs before a release. Only ``EXECUTION_MODE`` changes.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

from framework.core.exceptions import ConfigurationError
from framework.core.logger import get_logger

if TYPE_CHECKING:
    from framework.config.settings import Settings
    from framework.ui.browsers import Browser

log = get_logger("ui.targets")


class ExecutionTarget(ABC):
    mode: ClassVar[str]
    _registry: ClassVar[dict[str, type[ExecutionTarget]]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "mode" in cls.__dict__:
            ExecutionTarget._registry[cls.mode] = cls

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @classmethod
    def for_settings(cls, settings: Settings) -> ExecutionTarget:
        try:
            return cls._registry[settings.execution_mode](settings)
        except KeyError:
            raise ConfigurationError(
                f"Unsupported EXECUTION_MODE {settings.execution_mode!r}. "
                f"Choose one of: {', '.join(cls._registry)}"
            ) from None

    @classmethod
    def modes(cls) -> tuple[str, ...]:
        return tuple(cls._registry)

    # --- template method: the fixed recipe ---------------------------------------
    def create_driver(self, browser: Browser, test_name: str = "") -> Any:
        options = browser.build_options()
        self.apply_capabilities(options, test_name)
        return self._start(browser, options, test_name)

    # --- steps subclasses may customise ---------------------------------------------
    def apply_capabilities(self, options: Any, test_name: str) -> None:
        """Attach target specific capabilities. Default: none."""

    def report_status(self, driver: Any, passed: bool, reason: str = "") -> None:
        """Tell the platform whether the test passed. Default: platform has no dashboard."""

    @abstractmethod
    def _start(self, browser: Browser, options: Any, test_name: str) -> Any:
        """Start and return the WebDriver."""


class LocalTarget(ExecutionTarget):
    mode = "local"

    def _start(self, browser: Browser, options: Any, test_name: str) -> Any:
        return browser.start_local(options)


class GridTarget(ExecutionTarget):
    mode = "remote"

    def hub_url(self) -> str:
        if not self._settings.grid_url:
            raise ConfigurationError("EXECUTION_MODE=remote requires GRID_URL (e.g. http://host:4444/wd/hub)")
        return self._settings.grid_url

    def _start(self, browser: Browser, options: Any, test_name: str) -> Any:
        from selenium import webdriver

        hub = self.hub_url()
        log.info("Starting remote session mode=%s hub=%s test=%s", self.mode, hub, test_name)
        return webdriver.Remote(command_executor=hub, options=options)


class CloudTarget(GridTarget):
    """Rules shared by every cloud vendor; subclasses supply only what differs."""

    #: Capability key holding the vendor options, e.g. "sauce:options".
    vendor_key: ClassVar[str]
    #: Default hub; override with GRID_URL for another region or a private tunnel.
    default_hub: ClassVar[str]

    def hub_url(self) -> str:
        return self._settings.grid_url or self.default_hub

    @abstractmethod
    def _vendor_options(self, test_name: str) -> dict[str, Any]:
        """The vendor-specific capability block (credentials, build, test name)."""

    @abstractmethod
    def _status_script(self, passed: bool, reason: str) -> str:
        """JavaScript the vendor documents for marking a session passed/failed."""

    # --- shared behaviour -------------------------------------------------------------------
    @property
    def _build(self) -> str:
        return self._settings.build_name or "local-run"

    def apply_capabilities(self, options: Any, test_name: str) -> None:
        s = self._settings
        if not (s.grid_username and s.grid_access_key):
            raise ConfigurationError(
                f"EXECUTION_MODE={self.mode} requires credentials; set the provider's username/access-key "
                "environment variables (see .env.example)"
            )
        options.set_capability("browserVersion", s.browser_version)
        options.set_capability("platformName", s.platform_name)
        options.set_capability(self.vendor_key, self._vendor_options(test_name))
        # TODO(future): device/OS matrix. Load config/cloud_matrix.yaml and parametrize the
        # `driver` fixture over it, e.g. [("Windows 11","chrome"),("macOS 14","safari")].
        # BrowserStack expects "os"/"osVersion" inside bstack:options instead of platformName;
        # Sauce Labs real devices use "appium:deviceName". Keep that mapping in these subclasses.

    def report_status(self, driver: Any, passed: bool, reason: str = "") -> None:
        try:
            driver.execute_script(self._status_script(passed, reason))
        except Exception as exc:  # noqa: BLE001 - a dashboard label must never fail the run
            log.warning("Could not report status to %s: %s", self.mode, exc)


def _verdict(passed: bool) -> str:
    return "passed" if passed else "failed"


class SauceLabsTarget(CloudTarget):
    mode = "saucelabs"
    vendor_key = "sauce:options"
    default_hub = "https://ondemand.us-west-1.saucelabs.com:443/wd/hub"  # confirm region on your dashboard

    def _vendor_options(self, test_name: str) -> dict[str, Any]:
        s = self._settings
        return {"username": s.grid_username, "accessKey": s.grid_access_key, "build": self._build, "name": test_name}

    def _status_script(self, passed: bool, reason: str) -> str:
        return f"sauce:job-result={_verdict(passed)}"


class BrowserStackTarget(CloudTarget):
    mode = "browserstack"
    vendor_key = "bstack:options"
    default_hub = "https://hub-cloud.browserstack.com/wd/hub"

    def _vendor_options(self, test_name: str) -> dict[str, Any]:
        s = self._settings
        return {
            "userName": s.grid_username,
            "accessKey": s.grid_access_key,
            "buildName": self._build,
            "sessionName": test_name,
        }

    def _status_script(self, passed: bool, reason: str) -> str:
        payload = {"action": "setSessionStatus", "arguments": {"status": _verdict(passed), "reason": reason[:250]}}
        return f"browserstack_executor: {json.dumps(payload)}"


class LambdaTestTarget(CloudTarget):
    mode = "lambdatest"
    vendor_key = "LT:Options"
    default_hub = "https://hub.lambdatest.com/wd/hub"

    def _vendor_options(self, test_name: str) -> dict[str, Any]:
        s = self._settings
        return {
            "username": s.grid_username,
            "accessKey": s.grid_access_key,
            "build": self._build,
            "name": test_name,
            "w3c": True,
        }

    def _status_script(self, passed: bool, reason: str) -> str:
        return f"lambda-status={_verdict(passed)}"
