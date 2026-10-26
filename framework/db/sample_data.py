"""
Module  : framework.db.sample_data
Author  : Anil Kalisetti
Purpose : Create and seed the sample ``tax_test_data`` table used by the DB-driven tests.

Scenario: a Canadian retailer verifies that checkout adds the right provincial sales tax.
Amounts are TEXT on purpose: SQLite has no exact DECIMAL type, and money must never pass
through binary floating point. In PostgreSQL/Oracle/SQL Server use NUMERIC(12,2).

Rate sources should be confirmed with the Canada Revenue Agency before real use.
"""

from __future__ import annotations

from framework.db.client import DatabaseClient

_DDL = """
CREATE TABLE tax_test_data (
    id              INTEGER PRIMARY KEY,
    scenario        TEXT    NOT NULL,
    province        TEXT    NOT NULL,
    subtotal        TEXT    NOT NULL,
    expected_total  TEXT,
    expected_error  TEXT,
    status          TEXT    NOT NULL DEFAULT 'NEW',
    actual_total    TEXT,
    error_message   TEXT,
    executed_at     TEXT
)
"""

# (scenario, province, subtotal, expected_total, expected_error)
_SEED_ROWS: list[tuple[str, str, str, str | None, str | None]] = [
    ("Ontario HST 13% on $100", "ON", "100.00", "113.00", None),
    ("Alberta GST 5% on $100", "AB", "100.00", "105.00", None),
    ("British Columbia GST+PST 12% on $100", "BC", "100.00", "112.00", None),
    ("Quebec GST+QST 14.975% on $100", "QC", "100.00", "114.98", None),
    ("Zero subtotal costs nothing", "ON", "0.00", "0.00", None),
    ("One cent: tax rounds down to zero", "ON", "0.01", "0.01", None),
    ("Rounding up: $19.99 in Ontario", "ON", "19.99", "22.59", None),
    ("Quebec rounding: $19.99", "QC", "19.99", "22.98", None),
    ("Half-cent rounds UP: $0.50 in Alberta", "AB", "0.50", "0.53", None),
    ("Large order: $1,000,000 in Ontario", "ON", "1000000.00", "1130000.00", None),
    ("BC repeating decimal: $33.33", "BC", "33.33", "37.33", None),
    ("Lowercase province code accepted", "on", "10.00", "11.30", None),
    ("Negative subtotal is rejected", "ON", "-5.00", None, "ValueError"),
    ("Unknown province is rejected", "ZZ", "10.00", None, "ValueError"),
    ("Non-numeric subtotal is rejected", "ON", "ten dollars", None, "ValueError"),
]


def seed_sample_database(db: DatabaseClient) -> None:
    """Drop and recreate the sample table so every session starts from a known state."""
    db.execute("DROP TABLE IF EXISTS tax_test_data")
    db.execute(_DDL)
    db.execute_many(
        "INSERT INTO tax_test_data (scenario, province, subtotal, expected_total, expected_error) "
        "VALUES (:scenario, :province, :subtotal, :expected_total, :expected_error)",
        [
            {
                "scenario": s,
                "province": p,
                "subtotal": sub,
                "expected_total": total,
                "expected_error": err,
            }
            for s, p, sub, total, err in _SEED_ROWS
        ],
    )
