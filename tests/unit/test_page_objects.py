"""
Module  : tests/unit/test_page_objects.py
Author  : Anil Kalisetti
Purpose : Page objects follow the abstract-base contract (every page can say if it is loaded).
"""

from __future__ import annotations

import importlib
import sys

import pytest

_PAGE_MODULES = (
    "framework.ui.base_page",
    "framework.ui.pages",
    "framework.ui.pages.login_page",
    "framework.ui.pages.inventory_page",
    "framework.ui.pages.cart_page",
    "framework.ui.pages.checkout_page",
)


@pytest.fixture
def pages(fake_selenium, monkeypatch):
    """Import the page modules against the fake Selenium (and forget them again afterwards)."""
    for name in _PAGE_MODULES:
        monkeypatch.delitem(sys.modules, name, raising=False)
    base = importlib.import_module("framework.ui.base_page")
    package = importlib.import_module("framework.ui.pages")
    return base, package


def test_base_page_is_abstract(pages):
    base, _ = pages
    with pytest.raises(TypeError):
        base.BasePage(object())


def test_every_concrete_page_implements_is_loaded(pages):
    _, package = pages
    for name in ("LoginPage", "InventoryPage", "CartPage", "CheckoutPage"):
        page_class = getattr(package, name)
        assert not getattr(page_class, "__abstractmethods__", None), f"{name} is still abstract"
        assert callable(page_class(object()).is_loaded)


def test_checkout_is_loaded_on_every_checkout_step(pages):
    _, package = pages
    driver = type("D", (), {"current_url": ""})()
    page = package.CheckoutPage(driver)
    for url, expected in [("https://x/checkout-step-one.html", True), ("https://x/checkout-complete.html", True),
                          ("https://x/cart.html", False)]:  # fmt: skip
        driver.current_url = url
        assert page.is_loaded() is expected
