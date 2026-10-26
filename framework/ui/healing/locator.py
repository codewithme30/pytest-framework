"""
Module  : framework.ui.healing.locator
Author  : Anil Kalisetti
Purpose : A locator that still behaves like Selenium's ``(by, value)`` tuple, but also carries
          a name, optional fallback selectors and a per-locator opt-out from healing.

Why a tuple subclass? Every Selenium API (``find_element(*locator)``, expected conditions)
keeps working unchanged, so adopting healing needs no change in how pages are written.

    LOGIN_BUTTON = css("#login-button", fallbacks=['[data-test="login-button"]'])
    PAY_NOW      = css("#pay", heal=False)       # money moves here: never guess
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

CSS_SELECTOR = "css selector"  # value of selenium.webdriver.common.by.By.CSS_SELECTOR (kept here to stay Selenium-free)

Pair = tuple[str, str]


def _as_pair(fallback: Any) -> Pair:
    if isinstance(fallback, str):
        return (CSS_SELECTOR, fallback)  # a bare string means a CSS selector
    by, value = fallback
    return (str(by), str(value))


class Locator(tuple):  # type: ignore[type-arg]
    """``(by, value)`` plus ``name``, ``fallbacks`` and ``heal``."""

    name: str
    fallbacks: tuple[Pair, ...]
    heal: bool

    def __new__(
        cls,
        by: str,
        value: str,
        *,
        fallbacks: Iterable[Any] = (),
        heal: bool = True,
        name: str = "",
    ) -> Locator:
        obj = super().__new__(cls, (by, value))
        obj.fallbacks = tuple(_as_pair(f) for f in fallbacks)
        obj.heal = heal
        obj.name = name
        return obj

    def __set_name__(self, owner: type, attribute: str) -> None:
        """Python calls this when the class body finishes: ``LoginPage.LOGIN_BUTTON`` names itself."""
        if not self.name:
            self.name = f"{owner.__name__}.{attribute}"

    def derive(self, by: str, value: str) -> Locator:
        """A copy pointing at a healed selector; it never heals again (no healing loops)."""
        return Locator(by, value, heal=False, name=self.name)

    def __repr__(self) -> str:
        label = self.name or "locator"
        return f"<{label}: {self[0]}={self[1]}>"
