"""
Module  : tests/ui/test_inventory.py
Author  : Anil Kalisetti
Purpose : Product catalogue: contents, sorting in all four directions, data sanity, detail view.

Soft assertions (pytest-check) are used where one test inspects many items: every bad item is
reported in a single run instead of stopping at the first.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pytest_check import check

pytestmark = pytest.mark.network


@pytest.mark.smoke
def test_catalogue_lists_every_product(inventory_page, products):
    assert sorted(inventory_page.product_names) == sorted(products)


@pytest.mark.regression
def test_every_product_has_a_name_and_a_positive_price(inventory_page):
    for name, price in zip(inventory_page.product_names, inventory_page.product_prices, strict=True):
        check.is_true(name, "product with empty name")
        check.greater(price, Decimal("0"), f"{name!r} must have a positive price")


@pytest.mark.regression
@pytest.mark.parametrize(("option", "descending"), [("az", False), ("za", True)], ids=["a-to-z", "z-to-a"])
def test_sort_by_name(inventory_page, option, descending):
    inventory_page.sort_by(option)
    names = inventory_page.product_names
    assert names == sorted(names, reverse=descending)


@pytest.mark.regression
@pytest.mark.parametrize(("option", "descending"), [("lohi", False), ("hilo", True)], ids=["low-to-high", "high-to-low"])
def test_sort_by_price(inventory_page, option, descending):
    inventory_page.sort_by(option)
    prices = inventory_page.product_prices
    assert prices == sorted(prices, reverse=descending)


@pytest.mark.regression
def test_sorting_keeps_the_same_set_of_products(inventory_page):
    before = sorted(inventory_page.product_names)
    inventory_page.sort_by("hilo")
    assert sorted(inventory_page.product_names) == before


@pytest.mark.regression
def test_product_detail_page_opens_from_the_catalogue(inventory_page, products):
    inventory_page.open_product(products[0])
    assert "inventory-item" in inventory_page.current_url
    inventory_page.back()
    assert inventory_page.is_loaded()


@pytest.mark.regression
def test_reset_app_state_empties_the_cart(inventory_page, products):
    inventory_page.add_to_cart(products[0])
    assert inventory_page.cart_count == 1
    inventory_page.reset_app_state()
    inventory_page.refresh()
    assert inventory_page.cart_count == 0
