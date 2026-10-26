"""
Package : framework.ui.pages
Author  : Anil Kalisetti
Purpose : Page objects for the sample application (SauceDemo, a public retail demo by Sauce Labs).

Replace these with your own application's pages; keep the same one-class-per-page structure.
"""

from framework.ui.pages.cart_page import CartPage
from framework.ui.pages.checkout_page import CheckoutPage
from framework.ui.pages.inventory_page import InventoryPage
from framework.ui.pages.login_page import LoginPage

__all__ = ["CartPage", "CheckoutPage", "InventoryPage", "LoginPage"]
