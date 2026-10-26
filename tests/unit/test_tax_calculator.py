"""
Module  : tests/unit/test_tax_calculator.py
Author  : Anil Kalisetti
Purpose : Money-handling edge cases for the sample system under test (provincial sales tax).

Why these cases matter: invoices are legal documents. A one-cent rounding difference
multiplied by thousands of orders becomes an audit finding.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from framework.sample_app.tax_calculator import PROVINCE_TAX_RATES, calculate_total


@pytest.mark.parametrize(
    ("subtotal", "province", "expected"),
    [
        ("100.00", "ON", "113.00"),
        ("100.00", "AB", "105.00"),
        ("100.00", "BC", "112.00"),
        ("100.00", "QC", "114.98"),  # 14.975 -> tax 14.98
        ("0.00", "ON", "0.00"),
        ("0.01", "ON", "0.01"),  # tax 0.0013 rounds to 0.00
        ("0.50", "AB", "0.53"),  # exactly half a cent rounds UP, not to even
        ("19.99", "ON", "22.59"),
        ("1000000.00", "ON", "1130000.00"),
        (Decimal("33.33"), "BC", "37.33"),
        ("10.00", " on ", "11.30"),  # whitespace and case are tolerated
    ],
)
def test_total_includes_rounded_tax(subtotal, province, expected):
    assert calculate_total(subtotal, province) == Decimal(expected)


@pytest.mark.parametrize("bad_subtotal", ["-0.01", "-100", "abc", "", "NaN", "Infinity"])
def test_invalid_subtotal_is_rejected(bad_subtotal):
    with pytest.raises(ValueError, match="[Ss]ubtotal"):
        calculate_total(bad_subtotal, "ON")


@pytest.mark.parametrize("province", ["ZZ", "", "Ontario", "XX"])
def test_unknown_province_is_rejected(province):
    with pytest.raises(ValueError, match="province"):
        calculate_total("10.00", province)


def test_result_is_always_two_decimal_places():
    assert calculate_total("5", "AB").as_tuple().exponent == -2


def test_all_rates_are_exact_decimals_not_floats():
    assert all(isinstance(rate, Decimal) for rate in PROVINCE_TAX_RATES.values())
