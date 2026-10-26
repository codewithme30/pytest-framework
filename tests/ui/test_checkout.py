"""
Module  : tests/ui/test_checkout.py
Author  : Anil Kalisetti
Purpose : The revenue path: customer details, order overview maths, confirmation, validation.

The tax rate on the demo site is 8%. The arithmetic checks compare the page against values
computed independently from the catalogue prices, so a rounding bug on the site is caught.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import pytest

from framework.core.data_factory import build_checkout_info

pytestmark = pytest.mark.network

EXPECTED_TAX_RATE = Decimal("0.08")
_CENT = Decimal("0.01")


def _go_to_checkout(inventory_page, cart_page, products_to_buy):
    for product in products_to_buy:
        inventory_page.add_to_cart(product)
    inventory_page.open_cart()
    cart_page.checkout()


def _fill_valid_customer(checkout_page):
    info = build_checkout_info()
    checkout_page.fill_customer_info(info.first_name, info.last_name, info.postal_code)
    checkout_page.continue_to_overview()


@pytest.mark.smoke
@pytest.mark.critical
def test_customer_can_complete_a_purchase(inventory_page, cart_page, checkout_page, products):
    _go_to_checkout(inventory_page, cart_page, products[:2])
    _fill_valid_customer(checkout_page)
    checkout_page.finish()
    assert checkout_page.confirmation_header == "Thank you for your order!"


@pytest.mark.critical
@pytest.mark.regression
@pytest.mark.parametrize("count", [1, 2, 6], ids=["one-item", "two-items", "whole-catalogue"])
def test_order_overview_arithmetic_is_correct(inventory_page, cart_page, checkout_page, products, count):
    prices = dict(zip(inventory_page.product_names, inventory_page.product_prices, strict=True))
    chosen = products[:count]
    expected_subtotal = sum((prices[name] for name in chosen), Decimal("0"))
    expected_tax = (expected_subtotal * EXPECTED_TAX_RATE).quantize(_CENT, rounding=ROUND_HALF_UP)

    _go_to_checkout(inventory_page, cart_page, chosen)
    _fill_valid_customer(checkout_page)

    assert checkout_page.subtotal == expected_subtotal
    assert checkout_page.tax == expected_tax
    assert checkout_page.total == expected_subtotal + expected_tax


VALIDATION_CASES = [
    pytest.param("", "Nair", "M5V 2T6", "First Name is required", id="missing-first-name"),
    pytest.param("Priya", "", "M5V 2T6", "Last Name is required", id="missing-last-name"),
    pytest.param("Priya", "Nair", "", "Postal Code is required", id="missing-postal-code"),
    pytest.param("", "", "", "First Name is required", id="everything-missing"),
]


@pytest.mark.regression
@pytest.mark.parametrize(("first", "last", "postal", "expected_error"), VALIDATION_CASES)
def test_missing_customer_details_are_rejected(
    inventory_page, cart_page, checkout_page, products, first, last, postal, expected_error
):
    _go_to_checkout(inventory_page, cart_page, products[:1])
    checkout_page.fill_customer_info(first, last, postal)
    checkout_page.continue_to_overview()
    assert expected_error in checkout_page.error_message
    assert "checkout-step-one" in checkout_page.current_url


UNUSUAL_BUT_VALID_DETAILS = [
    pytest.param("José", "Müller", "K1A 0B1", id="accented-name"),
    pytest.param("Mary-Jane", "O'Neil-Smith", "90210", id="hyphen-and-apostrophe"),
    pytest.param("张", "伟", "100000", id="non-latin-name"),
    pytest.param("A", "B", "1", id="single-character-fields"),
    pytest.param("X" * 100, "Y" * 100, "Z" * 20, id="very-long-values"),
]


@pytest.mark.regression
@pytest.mark.parametrize(("first", "last", "postal"), UNUSUAL_BUT_VALID_DETAILS)
def test_unusual_but_legitimate_customer_details_are_accepted(
    inventory_page, cart_page, checkout_page, products, first, last, postal
):
    _go_to_checkout(inventory_page, cart_page, products[:1])
    checkout_page.fill_customer_info(first, last, postal)
    checkout_page.continue_to_overview()
    assert "checkout-step-two" in checkout_page.current_url


@pytest.mark.regression
def test_cancel_on_customer_details_returns_to_the_cart(inventory_page, cart_page, checkout_page, products):
    _go_to_checkout(inventory_page, cart_page, products[:1])
    checkout_page.cancel()
    assert "cart" in checkout_page.current_url
    assert cart_page.item_names == [products[0]]


@pytest.mark.regression
def test_cart_is_empty_after_a_completed_order(inventory_page, cart_page, checkout_page, products):
    _go_to_checkout(inventory_page, cart_page, products[:3])
    _fill_valid_customer(checkout_page)
    checkout_page.finish()
    checkout_page.back_to_products()
    assert inventory_page.cart_count == 0
