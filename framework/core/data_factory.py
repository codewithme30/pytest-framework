"""
Module  : framework.core.data_factory
Author  : Anil Kalisetti
Purpose : Realistic, reproducible random test data (names, addresses, payloads).

Set ``FAKER_SEED`` to replay the exact data of a failed run; otherwise each run differs,
which is how formatting bugs hiding behind "John Smith" get discovered.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from faker import Faker

_faker = Faker("en_CA")
_seed = os.getenv("FAKER_SEED")
if _seed:
    Faker.seed(int(_seed))


@dataclass(frozen=True)
class CheckoutInfo:
    first_name: str
    last_name: str
    postal_code: str


def build_checkout_info() -> CheckoutInfo:
    """Shipping details for a Canadian customer, e.g. ``Priya Nair, M5V 2T6``."""
    return CheckoutInfo(_faker.first_name(), _faker.last_name(), _faker.postcode())


def build_post_payload() -> dict[str, object]:
    """Body for ``POST /posts`` style endpoints."""
    return {
        "title": _faker.sentence(nb_words=5),
        "body": _faker.paragraph(nb_sentences=2),
        "userId": _faker.random_int(min=1, max=10),
    }
