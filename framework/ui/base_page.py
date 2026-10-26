"""
Module  : framework.ui.base_page
Author  : Anil Kalisetti
Purpose : Page Object base class: every interaction goes through explicit, bounded waits.

Page objects expose *business actions* (``login_as``); tests never touch locators directly.

OOP concepts: ``BasePage`` is abstract (every page MUST say how to recognise itself via
``is_loaded``), concrete pages inherit all interaction helpers (inheritance), keep their
locators as class attributes (encapsulation: tests never see a selector), and tests treat any
page through the same ``is_loaded()`` call (polymorphism).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import Select, WebDriverWait

from framework.ui.healing import Locator, LocatorHealer


def css(selector: str, *, fallbacks: tuple[Any, ...] | list[Any] = (), heal: bool = True) -> Locator:
    """Readable shorthand: ``css('[data-test="login-button"]')``.

    ``fallbacks``: alternate selectors tried if this one stops matching (self-healing).
    ``heal=False``: never repair this locator automatically (use for actions that move money).
    """
    return Locator(By.CSS_SELECTOR, selector, fallbacks=fallbacks, heal=heal)


class BasePage(ABC):
    def __init__(self, driver: WebDriver, timeout: int = 10, healer: LocatorHealer | None = None) -> None:
        self.driver = driver
        self.timeout = timeout
        self._wait = WebDriverWait(driver, timeout)
        self._healer = healer or LocatorHealer.disabled()  # no healer => plain Selenium behaviour

    @abstractmethod
    def is_loaded(self) -> bool:
        """True when this page (and not another) is currently displayed."""

    # --- navigation ---------------------------------------------------------
    def open(self, url: str) -> None:
        self.driver.get(url)

    @property
    def current_url(self) -> str:
        return self.driver.current_url

    @property
    def title(self) -> str:
        return self.driver.title

    def refresh(self) -> None:
        self.driver.refresh()

    def back(self) -> None:
        self.driver.back()

    def wait_for_url_contains(self, fragment: str) -> None:
        self._wait.until(ec.url_contains(fragment))

    # --- element lookup -------------------------------------------------------
    def _resolve(self, locator: Locator, condition: Callable[[Locator], Any]) -> Any:
        """Wait for ``condition(locator)``; if the element never appears, try to heal the locator.

        Only interactions that REQUIRE the element (find, click, type, read) go through here.
        Probing helpers (``is_visible``, ``is_absent``, ``find_all``) never heal: "is the error
        banner absent?" must not be answered by a look-alike element.
        """
        healer = self._healer
        locator = healer.preferred(locator)  # healed earlier in this test? use that directly
        if not healer.can_heal(locator):
            return healer.record(locator, self._wait.until(condition(locator)))

        patience = min(healer.heal_after, self.timeout)
        try:
            return WebDriverWait(self.driver, patience).until(condition(locator))
        except TimeoutException:
            healed = healer.heal(locator, self.driver.current_url)
            if healed is None:  # nothing trustworthy found: keep waiting normally, then fail as before
                return WebDriverWait(self.driver, max(self.timeout - patience, 1)).until(condition(locator))
            return self._wait.until(condition(healed))

    def find(self, locator: Locator) -> WebElement:
        return self._resolve(locator, ec.visibility_of_element_located)

    def find_all(self, locator: Locator) -> list[WebElement]:
        """Return all matches; an empty list (not an exception) when none exist."""
        return self.driver.find_elements(*locator)

    # --- actions -----------------------------------------------------------------
    def click(self, locator: Locator) -> None:
        self._resolve(locator, ec.element_to_be_clickable).click()

    def type_text(self, locator: Locator, text: str, clear: bool = True) -> None:
        element = self.find(locator)
        if clear:
            element.clear()
        element.send_keys(text)

    def select_by_value(self, locator: Locator, value: str) -> None:
        Select(self.find(locator)).select_by_value(value)

    def hover(self, locator: Locator) -> None:
        ActionChains(self.driver).move_to_element(self.find(locator)).perform()

    def scroll_into_view(self, locator: Locator) -> None:
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", self.find(locator))

    # --- reading state ----------------------------------------------------------------
    def text_of(self, locator: Locator) -> str:
        return self.find(locator).text.strip()

    def texts_of(self, locator: Locator) -> list[str]:
        return [el.text.strip() for el in self.find_all(locator)]

    def attribute_of(self, locator: Locator, name: str) -> str | None:
        return self.find(locator).get_attribute(name)

    def is_visible(self, locator: Locator, timeout: float = 2) -> bool:
        """True if the element becomes visible within ``timeout``; never raises."""
        try:
            WebDriverWait(self.driver, timeout).until(ec.visibility_of_element_located(locator))
            return True
        except TimeoutException:
            return False

    def is_absent(self, locator: Locator, timeout: float = 2) -> bool:
        try:
            WebDriverWait(self.driver, timeout).until(ec.invisibility_of_element_located(locator))
            return True
        except TimeoutException:
            return False
