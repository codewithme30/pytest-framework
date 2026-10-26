"""
Module  : framework.ui.pages.inventory_page
Author  : Anil Kalisetti
Purpose : Product listing, sorting, cart badge and the burger menu.
"""

from __future__ import annotations

from decimal import Decimal

from framework.ui.base_page import BasePage, Locator, css


def _slug(product_name: str) -> str:
    """'Sauce Labs Backpack' -> 'sauce-labs-backpack' (used in the data-test attributes)."""
    return product_name.lower().replace(" ", "-")


class InventoryPage(BasePage):
    TITLE = css('[data-test="title"]')
    ITEMS = css('[data-test="inventory-item"]')
    NAMES = css('[data-test="inventory-item-name"]')
    PRICES = css('[data-test="inventory-item-price"]')
    SORT = css('[data-test="product-sort-container"]')
    CART_LINK = css('[data-test="shopping-cart-link"]')
    CART_BADGE = css('[data-test="shopping-cart-badge"]')
    MENU_BUTTON = css("#react-burger-menu-btn")
    LOGOUT_LINK = css("#logout_sidebar_link")
    RESET_LINK = css("#reset_sidebar_link")

    @staticmethod
    def _add_button(product: str) -> Locator:
        return css(f'[data-test="add-to-cart-{_slug(product)}"]')

    @staticmethod
    def _remove_button(product: str) -> Locator:
        return css(f'[data-test="remove-{_slug(product)}"]')

    # --- state ------------------------------------------------------------------
    def is_loaded(self) -> bool:
        return self.is_visible(self.TITLE) and "inventory" in self.current_url

    @property
    def product_names(self) -> list[str]:
        self.find(self.ITEMS)
        return self.texts_of(self.NAMES)

    @property
    def product_prices(self) -> list[Decimal]:
        self.find(self.ITEMS)
        return [Decimal(text.lstrip("$")) for text in self.texts_of(self.PRICES)]

    @property
    def cart_count(self) -> int:
        """Badge number; the badge disappears entirely when the cart is empty."""
        return int(self.text_of(self.CART_BADGE)) if self.is_visible(self.CART_BADGE, 1) else 0

    # --- actions ------------------------------------------------------------------
    def sort_by(self, option_value: str) -> None:
        """option_value: az | za | lohi | hilo"""
        self.select_by_value(self.SORT, option_value)

    def add_to_cart(self, product: str) -> None:
        self.click(self._add_button(product))

    def remove_from_cart(self, product: str) -> None:
        self.click(self._remove_button(product))

    def is_in_cart(self, product: str) -> bool:
        return self.is_visible(self._remove_button(product), 1)

    def open_cart(self) -> None:
        self.click(self.CART_LINK)
        self.wait_for_url_contains("cart")  # clicking returns before navigation finishes

    def open_product(self, product: str) -> None:
        self.click(css(f'[data-test="item-{self._index_of(product)}-title-link"]'))
        self.wait_for_url_contains("inventory-item")

    def _index_of(self, product: str) -> int:
        """Return the site's internal item id for a product name (ids are not sorted by name)."""
        links = self.find_all(css('[data-test$="-title-link"]'))
        for link in links:
            if link.text.strip() == product:
                return int(link.get_attribute("data-test").split("-")[1])
        raise LookupError(f"Product not found on page: {product}")

    def logout(self) -> None:
        self.click(self.MENU_BUTTON)
        self.click(self.LOGOUT_LINK)
        self.find(css("#login-button"))  # wait until the login screen is back

    def reset_app_state(self) -> None:
        self.click(self.MENU_BUTTON)
        self.click(self.RESET_LINK)
