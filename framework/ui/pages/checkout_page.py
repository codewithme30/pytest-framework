"""
Module  : framework.ui.pages.checkout_page
Author  : Anil Kalisetti
Purpose : The three checkout screens: customer info, order overview, confirmation.
"""

from __future__ import annotations

import re
from decimal import Decimal

from framework.ui.base_page import BasePage, css

_MONEY = re.compile(r"\$(\d+(?:\.\d{2})?)")


def _money(label: str) -> Decimal:
    """'Item total: $29.99' -> Decimal('29.99')."""
    match = _MONEY.search(label)
    if not match:
        raise ValueError(f"No amount found in label: {label!r}")
    return Decimal(match.group(1))


class CheckoutPage(BasePage):
    FIRST_NAME = css('[data-test="firstName"]')
    LAST_NAME = css('[data-test="lastName"]')
    POSTAL_CODE = css('[data-test="postalCode"]')
    CONTINUE = css('[data-test="continue"]')
    CANCEL = css('[data-test="cancel"]')
    ERROR = css('[data-test="error"]')

    SUBTOTAL = css('[data-test="subtotal-label"]')
    TAX = css('[data-test="tax-label"]')
    TOTAL = css('[data-test="total-label"]')
    FINISH = css('[data-test="finish"]')

    COMPLETE_HEADER = css('[data-test="complete-header"]')
    BACK_HOME = css('[data-test="back-to-products"]')

    # --- step one: customer information ------------------------------------------------
    def fill_customer_info(self, first: str, last: str, postal: str) -> None:
        self.type_text(self.FIRST_NAME, first)
        self.type_text(self.LAST_NAME, last)
        self.type_text(self.POSTAL_CODE, postal)

    def continue_to_overview(self) -> None:
        self.click(self.CONTINUE)

    def cancel(self) -> None:
        self.click(self.CANCEL)
        self.wait_for_url_contains("cart")

    @property
    def error_message(self) -> str:
        return self.text_of(self.ERROR)

    # --- step two: overview -------------------------------------------------------------
    @property
    def subtotal(self) -> Decimal:
        return _money(self.text_of(self.SUBTOTAL))

    @property
    def tax(self) -> Decimal:
        return _money(self.text_of(self.TAX))

    @property
    def total(self) -> Decimal:
        return _money(self.text_of(self.TOTAL))

    def finish(self) -> None:
        self.click(self.FINISH)
        self.wait_for_url_contains("checkout-complete")

    # --- step three: confirmation ----------------------------------------------------------
    @property
    def confirmation_header(self) -> str:
        return self.text_of(self.COMPLETE_HEADER)

    def back_to_products(self) -> None:
        self.click(self.BACK_HOME)
        self.wait_for_url_contains("inventory")
