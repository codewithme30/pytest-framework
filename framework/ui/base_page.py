"""
Module  : framework.ui.base_page
Author  : Anil Kalisetti
Purpose : Page Object base class: every interaction goes through explicit, bounded waits.

Page objects expose *business actions* (``login_as``); tests never touch locators directly.
"""

from __future__ import annotations

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import Select, WebDriverWait

Locator = tuple[str, str]


def css(selector: str) -> Locator:
    """Readable shorthand: ``css('[data-test="login-button"]')``."""
    return (By.CSS_SELECTOR, selector)


class BasePage:
    def __init__(self, driver: WebDriver, timeout: int = 10) -> None:
        self.driver = driver
        self.timeout = timeout
        self._wait = WebDriverWait(driver, timeout)

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
    def find(self, locator: Locator) -> WebElement:
        return self._wait.until(ec.visibility_of_element_located(locator))

    def find_all(self, locator: Locator) -> list[WebElement]:
        """Return all matches; an empty list (not an exception) when none exist."""
        return self.driver.find_elements(*locator)

    # --- actions -----------------------------------------------------------------
    def click(self, locator: Locator) -> None:
        self._wait.until(ec.element_to_be_clickable(locator)).click()

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
