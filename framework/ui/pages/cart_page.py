"""
Module  : framework.ui.pages.cart_page
Author  : Anil Kalisetti
Purpose : Shopping cart page.
"""

from __future__ import annotations

from framework.ui.base_page import BasePage, css


class CartPage(BasePage):
    ITEMS = css('[data-test="inventory-item"]')
    NAMES = css('[data-test="inventory-item-name"]')
    CHECKOUT = css('[data-test="checkout"]')
    CONTINUE_SHOPPING = css('[data-test="continue-shopping"]')

    @property
    def item_names(self) -> list[str]:
        """Names of items in the cart (empty list for an empty cart)."""
        return self.texts_of(self.NAMES)

    def remove(self, product: str) -> None:
        self.click(css(f'[data-test="remove-{product.lower().replace(" ", "-")}"]'))

    def checkout(self) -> None:
        self.click(self.CHECKOUT)
        self.wait_for_url_contains("checkout-step-one")

    def continue_shopping(self) -> None:
        self.click(self.CONTINUE_SHOPPING)
        self.wait_for_url_contains("inventory")
