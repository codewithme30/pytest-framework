"""
Module  : tests/unit/test_customer_transforms.py
Author  : Anil Kalisetti
Purpose : Pure-function checks of each cleansing rule used by the sample CRM migration.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from framework.sample_app.customer_migration import (
    cents_to_amount,
    convert_date,
    normalize_country,
    normalize_email,
    normalize_phone,
    split_name,
    transform_customer,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Priya Nair", ("Priya", "Nair")),
        ("  Tom   O'Brien ", ("Tom", "O'Brien")),
        ("Mary Jane Watson", ("Mary", "Jane Watson")),
        ("Madonna", ("Madonna", "")),
        ("José Müller", ("José", "Müller")),
        ("张 伟", ("张", "伟")),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_split_name(raw, expected):
    assert split_name(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" Priya@Example.COM ", "priya@example.com"),
        ("a@b.co", "a@b.co"),
        ("no-at-sign", None),
        ("two@@signs.com", None),
        ("space in@x.com", None),
        ("missing@tld", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_email(raw, expected):
    assert normalize_email(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("(416) 555-0101", "4165550101"),
        ("+1 905 555 0199", "19055550199"),
        ("0044 0207", "00440207"),  # leading zeros are data, not noise
        ("---", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("ca", "CA"), (" Canada ", "CA"), ("USA", "US"), ("United States", "US"), ("Narnia", "ZZ"), (None, "ZZ"), ("", "ZZ")],
)
def test_normalize_country(raw, expected):
    assert normalize_country(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("05/03/2021", "2021-03-05"),
        ("29/02/2024", "2024-02-29"),  # leap day
        ("29/02/2023", None),  # not a leap year
        ("31/02/2024", None),
        ("31/04/2024", None),
        ("12/31/2024", None),  # US month/day order is not valid here
        ("2024-03-05", None),
        ("", None),
        (None, None),
    ],
)
def test_convert_date(raw, expected):
    assert convert_date(raw) == expected


@pytest.mark.parametrize(
    ("cents", "expected"),
    [(12345, "123.45"), (0, "0.00"), (None, "0.00"), (-250, "-2.50"), (1, "0.01"), (9_999_999_999, "99999999.99")],
)
def test_cents_to_amount_is_exact(cents, expected):
    assert cents_to_amount(cents) == Decimal(expected)


def test_transform_rejects_with_first_failing_rule():
    row = {"cust_id": 1, "full_name": "", "email": "bad", "phone": None, "country": None,
           "signup_date": "31/02/2024", "balance_cents": 0, "status": "A"}  # fmt: skip
    assert transform_customer(row) == (None, "MISSING_NAME")
