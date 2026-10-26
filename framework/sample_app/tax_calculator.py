"""
Module  : framework.sample_app.tax_calculator
Author  : Anil Kalisetti
Purpose : Sample system under test: order total including Canadian provincial sales tax.

Rates are combined GST/HST/PST figures for illustration; confirm with the CRA before real use.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

PROVINCE_TAX_RATES: dict[str, Decimal] = {
    "ON": Decimal("0.13"),  # HST
    "AB": Decimal("0.05"),  # GST only
    "BC": Decimal("0.12"),  # GST 5% + PST 7%
    "QC": Decimal("0.14975"),  # GST 5% + QST 9.975%
    "MB": Decimal("0.12"),  # GST 5% + PST 7%
    "SK": Decimal("0.11"),  # GST 5% + PST 6%
}

_CENT = Decimal("0.01")


def calculate_total(subtotal: Decimal | str, province: str) -> Decimal:
    """Return ``subtotal + tax``, tax rounded half-up to the cent (as invoices do).

    Raises ``ValueError`` for negative or non-numeric subtotals and unknown provinces.
    """
    try:
        amount = Decimal(str(subtotal))
    except InvalidOperation as exc:
        raise ValueError(f"Subtotal is not a number: {subtotal!r}") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"Subtotal must be a non-negative number, got {subtotal!r}")

    rate = PROVINCE_TAX_RATES.get(province.strip().upper())
    if rate is None:
        raise ValueError(f"Unknown province code: {province!r}")

    tax = (amount * rate).quantize(_CENT, rounding=ROUND_HALF_UP)
    return amount.quantize(_CENT, rounding=ROUND_HALF_UP) + tax
