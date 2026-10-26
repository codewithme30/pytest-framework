"""
Module  : tests/ui/test_cart.py
Author  : Anil Kalisetti
Purpose : Shopping cart behaviour: add, remove, badge count, persistence, boundaries.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.network


@pytest.mark.smoke
def test_adding_an_item_updates_the_badge_and_the_button(inventory_page, products):
    assert inventory_page.cart_count == 0
    inventory_page.add_to_cart(products[0])
    assert inventory_page.cart_count == 1
    assert inventory_page.is_in_cart(products[0])  # "Add to cart" turned into "Remove"


@pytest.mark.regression
@pytest.mark.parametrize("quantity", [1, 2, 3, 6], ids=lambda n: f"{n}-items")
def test_badge_counts_every_added_item(inventory_page, products, quantity):
    for product in products[:quantity]:
        inventory_page.add_to_cart(product)
    assert inventory_page.cart_count == quantity


@pytest.mark.regression
def test_cart_page_lists_exactly_the_added_items(inventory_page, cart_page, products):
    chosen = [products[0], products[3]]
    for product in chosen:
        inventory_page.add_to_cart(product)
    inventory_page.open_cart()
    assert sorted(cart_page.item_names) == sorted(chosen)


@pytest.mark.regression
def test_removing_from_the_product_page_clears_the_badge(inventory_page, products):
    inventory_page.add_to_cart(products[1])
    inventory_page.remove_from_cart(products[1])
    assert inventory_page.cart_count == 0
    assert not inventory_page.is_in_cart(products[1])


@pytest.mark.regression
def test_removing_from_the_cart_page_updates_the_list(inventory_page, cart_page, products):
    inventory_page.add_to_cart(products[0])
    inventory_page.add_to_cart(products[1])
    inventory_page.open_cart()
    cart_page.remove(products[0])
    assert cart_page.item_names == [products[1]]


@pytest.mark.regression
def test_empty_cart_page_shows_no_items(inventory_page, cart_page):
    inventory_page.open_cart()
    assert cart_page.item_names == []


@pytest.mark.regression
def test_cart_survives_navigation_and_page_refresh(inventory_page, cart_page, products):
    inventory_page.add_to_cart(products[2])
    inventory_page.open_cart()
    cart_page.continue_shopping()
    assert inventory_page.cart_count == 1
    inventory_page.refresh()
    assert inventory_page.cart_count == 1


@pytest.mark.regression
def test_add_button_is_replaced_by_remove_so_duplicates_are_impossible(inventory_page, products):
    inventory_page.add_to_cart(products[0])
    assert inventory_page.is_in_cart(products[0])
    assert inventory_page.cart_count == 1
