"""
Module  : framework.ui.browsers
Author  : Anil Kalisetti
Purpose : One class per browser, hidden behind a common interface (Strategy + Factory).

OOP concepts used here, and why
    Abstraction    ``Browser`` states WHAT every browser must do; subclasses decide HOW.
    Inheritance    ``Chrome`` and ``Edge`` share Chromium behaviour via ``ChromiumBrowser``.
    Polymorphism   callers use ``browser.build_options()`` and never ask "which browser is this?".
    Encapsulation  settings are held privately; callers get behaviour, not raw fields.
    Open/closed    a new browser is a new subclass. Nothing else in the framework changes.

Real-life example: your product must work on Chrome and Firefox (most users) plus Safari
(every iPhone). Adding Safari later means adding ``class Safari(Browser)``, nothing more.

Selenium is imported lazily inside methods, so this module (and the pure helpers such as
``resolve_browsers``) works and is unit-testable on machines without Selenium installed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

from framework.core.exceptions import ConfigurationError
from framework.core.logger import get_logger

if TYPE_CHECKING:  # typing only: keeps Selenium optional at import time
    from framework.config.settings import Settings

log = get_logger("ui.browsers")


class Browser(ABC):
    """Contract every browser implements, plus the registry used by ``Browser.create``."""

    name: ClassVar[str]
    #: True when the browser belongs in the default "all browsers" matrix (``--ui-browsers all``).
    in_default_matrix: ClassVar[bool] = True
    _registry: ClassVar[dict[str, type[Browser]]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Only concrete browsers declare ``name``; abstract helpers (ChromiumBrowser) do not.
        if "name" in cls.__dict__:
            Browser._registry[cls.name] = cls

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # --- factory --------------------------------------------------------------
    @classmethod
    def create(cls, name: str, settings: Settings) -> Browser:
        try:
            return cls._registry[name](settings)
        except KeyError:
            raise ConfigurationError(
                f"Unsupported browser {name!r}. Choose one of: {', '.join(sorted(cls._registry))}"
            ) from None

    @classmethod
    def names(cls) -> tuple[str, ...]:
        return tuple(cls._registry)

    @classmethod
    def default_matrix(cls) -> tuple[str, ...]:
        return tuple(n for n, klass in cls._registry.items() if klass.in_default_matrix)

    # --- behaviour subclasses must provide -------------------------------------------
    @abstractmethod
    def build_options(self) -> Any:
        """Return a Selenium options object configured from the settings."""

    @abstractmethod
    def start_local(self, options: Any) -> Any:
        """Start the browser on this machine and return the WebDriver."""

    # --- shared behaviour ----------------------------------------------------------------
    @property
    def _size(self) -> tuple[int, int]:
        width, height = self._settings.window_size.split(",")
        return int(width), int(height)

    def after_start(self, driver: Any) -> None:
        """Hook run once the session exists. Default: nothing to do."""


class ChromiumBrowser(Browser):
    """Behaviour shared by Chrome and Edge (both are Chromium based)."""

    @abstractmethod
    def _new_options(self) -> Any:
        """Instantiate the vendor-specific options class."""

    def build_options(self) -> Any:
        options = self._new_options()
        if self._settings.headless:
            options.add_argument("--headless=new")
        width, height = self._size
        options.add_argument(f"--window-size={width},{height}")
        # Required when running as root inside Docker / CI containers.
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        return options


class Chrome(ChromiumBrowser):
    name = "chrome"

    def _new_options(self) -> Any:
        from selenium.webdriver.chrome.options import Options

        return Options()

    def build_options(self) -> Any:
        options = super().build_options()
        if self._settings.chrome_binary:  # e.g. /usr/bin/chromium in the Docker image
            options.binary_location = self._settings.chrome_binary
        return options

    def start_local(self, options: Any) -> Any:
        from selenium import webdriver

        return webdriver.Chrome(options=options)


class Edge(ChromiumBrowser):
    name = "edge"

    def _new_options(self) -> Any:
        from selenium.webdriver.edge.options import Options

        return Options()

    def start_local(self, options: Any) -> Any:
        from selenium import webdriver

        return webdriver.Edge(options=options)


class Firefox(Browser):
    name = "firefox"

    def build_options(self) -> Any:
        from selenium.webdriver.firefox.options import Options

        options = Options()
        if self._settings.headless:
            options.add_argument("-headless")
        width, height = self._size
        options.add_argument(f"--width={width}")
        options.add_argument(f"--height={height}")
        return options

    def start_local(self, options: Any) -> Any:
        from selenium import webdriver

        return webdriver.Firefox(options=options)

    def after_start(self, driver: Any) -> None:
        if not self._settings.headless:
            driver.set_window_size(*self._size)


class Safari(Browser):
    """Safari runs on macOS or in a cloud grid only, so it is not in the default matrix.

    Cloud usage: set PLATFORM_NAME to a macOS version (for example "macOS Sonoma").
    """

    name = "safari"
    in_default_matrix = False

    def build_options(self) -> Any:
        from selenium.webdriver.safari.options import Options

        if self._settings.headless:
            log.warning("Safari has no headless mode; running with a visible window.")
        return Options()

    def start_local(self, options: Any) -> Any:
        from selenium import webdriver

        return webdriver.Safari(options=options)

    def after_start(self, driver: Any) -> None:
        driver.set_window_size(*self._size)


def resolve_browsers(requested: str | None, default: str) -> list[str]:
    """Turn ``--ui-browsers`` into an ordered, de-duplicated, validated list.

    ``None`` or empty -> ``[default]``;  ``"all"`` -> every browser in the default matrix;
    ``"chrome, firefox"`` -> ``["chrome", "firefox"]``.
    """
    if not requested or not requested.strip():
        return [default]
    if requested.strip().lower() == "all":
        return list(Browser.default_matrix())

    chosen: list[str] = []
    for raw in requested.split(","):
        name = raw.strip().lower()
        if not name or name in chosen:
            continue
        if name not in Browser.names():
            raise ConfigurationError(
                f"Unknown browser {name!r} in --ui-browsers. Choose from: {', '.join(Browser.names())}, all"
            )
        chosen.append(name)
    return chosen or [default]
