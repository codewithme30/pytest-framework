"""
Module  : framework.sample_app.customer_migration
Author  : Anil Kalisetti
Purpose : Sample system under test: migrate a legacy CRM into a reporting warehouse.

Real-life scenario: a retailer retires its 15-year-old CRM. Customers and orders are moved to a
new warehouse, cleaning data on the way. Anything that cannot be cleaned is NOT dropped
silently; it is written to ``migration_rejects`` with a reason so the business can follow up.

Transformation rules
    full_name     trimmed, inner whitespace collapsed, split into first / last name
    email         trimmed + lower-cased; invalid -> reject; duplicate (case-insensitive) -> reject
    phone         digits only (leading zeros kept); empty -> NULL
    country       2-letter codes upper-cased, common names mapped, unknown -> 'ZZ'
    signup_date   DD/MM/YYYY -> ISO 8601 (YYYY-MM-DD); impossible dates -> reject
    balance_cents integer cents -> decimal amount ("12345" -> 123.45); NULL -> 0.00
    status        'A' -> is_active 1, anything else -> 0
    orders        amount_cents -> amount; unknown / rejected customer -> reject (orphan)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # keeps the pure transform functions importable without a database driver
    from framework.db.client import DatabaseClient

LEGACY_DDL = (
    """CREATE TABLE legacy_customers (
        cust_id INTEGER PRIMARY KEY, full_name TEXT, email TEXT, phone TEXT,
        country TEXT, signup_date TEXT, balance_cents INTEGER, status TEXT)""",
    """CREATE TABLE legacy_orders (
        order_id INTEGER PRIMARY KEY, cust_id INTEGER, amount_cents INTEGER, order_date TEXT)""",
)

TARGET_DDL = (
    """CREATE TABLE dim_customer (
        customer_id INTEGER PRIMARY KEY, first_name TEXT NOT NULL, last_name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE, phone_digits TEXT, country_code TEXT NOT NULL,
        signup_date TEXT NOT NULL, balance NUMERIC NOT NULL, is_active INTEGER NOT NULL)""",
    """CREATE TABLE fact_order (
        order_id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL,
        amount NUMERIC NOT NULL, order_date TEXT NOT NULL)""",
    """CREATE TABLE migration_rejects (
        source_table TEXT NOT NULL, source_id INTEGER NOT NULL, reason TEXT NOT NULL)""",
)

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_COUNTRY_NAMES = {"CANADA": "CA", "USA": "US", "UNITED STATES": "US", "UK": "GB", "ENGLAND": "GB"}
_CENT = Decimal("0.01")


# --- pure transformation helpers (no I/O, trivially unit-testable) ------------------------------
def split_name(full_name: str | None) -> tuple[str, str] | None:
    cleaned = " ".join((full_name or "").split())
    if not cleaned:
        return None
    first, _, last = cleaned.partition(" ")
    return first, last


def normalize_email(email: str | None) -> str | None:
    value = (email or "").strip().lower()
    return value if _EMAIL.match(value) else None


def normalize_phone(phone: str | None) -> str | None:
    digits = re.sub(r"\D", "", phone or "")
    return digits or None


def normalize_country(country: str | None) -> str:
    value = (country or "").strip().upper()
    if len(value) == 2 and value.isalpha():
        return value
    return _COUNTRY_NAMES.get(value, "ZZ")


def convert_date(legacy_date: str | None) -> str | None:
    """'29/02/2024' -> '2024-02-29'; impossible dates (31/02, 29/02/2023) return None."""
    try:
        return datetime.strptime((legacy_date or "").strip(), "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def cents_to_amount(cents: int | None) -> Decimal:
    return (Decimal(cents or 0) / 100).quantize(_CENT)


def transform_customer(row: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Return ``(target_row, None)`` or ``(None, reject_reason)``."""
    name = split_name(row["full_name"])
    if name is None:
        return None, "MISSING_NAME"
    email = normalize_email(row["email"])
    if email is None:
        return None, "INVALID_EMAIL"
    signup = convert_date(row["signup_date"])
    if signup is None:
        return None, "INVALID_DATE"
    return {
        "customer_id": row["cust_id"],
        "first_name": name[0],
        "last_name": name[1],
        "email": email,
        "phone_digits": normalize_phone(row["phone"]),
        "country_code": normalize_country(row["country"]),
        "signup_date": signup,
        "balance": cents_to_amount(row["balance_cents"]),
        "is_active": 1 if (row["status"] or "").strip().upper() == "A" else 0,
    }, None


# --- pipeline -----------------------------------------------------------------------------------
@dataclass
class MigrationStats:
    customers_read: int = 0
    customers_loaded: int = 0
    orders_read: int = 0
    orders_loaded: int = 0
    rejects: int = 0


def create_schemas(source: DatabaseClient, target: DatabaseClient) -> None:
    for ddl in LEGACY_DDL:
        source.execute(ddl)
    for ddl in TARGET_DDL:
        target.execute(ddl)


_INSERT_CUSTOMER = (
    "INSERT INTO dim_customer VALUES (:customer_id, :first_name, :last_name, :email, "
    ":phone_digits, :country_code, :signup_date, :balance, :is_active)"
)
_INSERT_ORDER = "INSERT INTO fact_order VALUES (:order_id, :customer_id, :amount, :order_date)"
_INSERT_REJECT = "INSERT INTO migration_rejects VALUES (:source_table, :source_id, :reason)"


def run_migration(
    source: DatabaseClient, target: DatabaseClient, batch_size: int = 1000
) -> MigrationStats:
    """Full refresh: safe to re-run (idempotent) because the target is emptied first.

    Memory: rows are streamed and written in batches. Only the set of accepted customer ids
    and e-mails is kept (needed for orphan / duplicate detection): ~100 bytes per customer.
    TODO(future): incremental loads. Track a ``last_modified`` watermark in a control table and
    MERGE only changed rows instead of reloading everything.
    """
    stats = MigrationStats()
    for table in ("dim_customer", "fact_order", "migration_rejects"):
        target.execute(f"DELETE FROM {table}")

    accepted_ids: set[int] = set()
    seen_emails: set[str] = set()
    customers: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []

    def flush(sql: str, batch: list[dict[str, Any]]) -> None:
        target.execute_many(sql, batch)
        batch.clear()

    for row in source.stream("SELECT * FROM legacy_customers ORDER BY cust_id", chunk_size=batch_size):
        stats.customers_read += 1
        clean, reason = transform_customer(row)
        if clean is not None and clean["email"] in seen_emails:
            clean, reason = None, "DUPLICATE_EMAIL"
        if clean is None:
            rejects.append({"source_table": "legacy_customers", "source_id": row["cust_id"], "reason": reason})
            continue
        seen_emails.add(clean["email"])
        accepted_ids.add(clean["customer_id"])
        customers.append(clean)
        if len(customers) >= batch_size:
            flush(_INSERT_CUSTOMER, customers)
    flush(_INSERT_CUSTOMER, customers)
    stats.customers_loaded = len(accepted_ids)

    orders: list[dict[str, Any]] = []
    for row in source.stream("SELECT * FROM legacy_orders ORDER BY order_id", chunk_size=batch_size):
        stats.orders_read += 1
        order_date = convert_date(row["order_date"])
        reason = (
            "ORPHAN_CUSTOMER" if row["cust_id"] not in accepted_ids
            else "INVALID_DATE" if order_date is None
            else None
        )
        if reason:
            rejects.append({"source_table": "legacy_orders", "source_id": row["order_id"], "reason": reason})
            continue
        orders.append(
            {
                "order_id": row["order_id"],
                "customer_id": row["cust_id"],
                "amount": cents_to_amount(row["amount_cents"]),
                "order_date": order_date,
            }
        )
        stats.orders_loaded += 1
        if len(orders) >= batch_size:
            flush(_INSERT_ORDER, orders)
    flush(_INSERT_ORDER, orders)

    flush(_INSERT_REJECT, rejects)
    stats.rejects = stats.customers_read - stats.customers_loaded + stats.orders_read - stats.orders_loaded
    return stats


# --- test-data helpers (used by the ETL test-suite) ---------------------------------------------
def legacy_customer(cust_id: int, **overrides: Any) -> dict[str, Any]:
    """A valid legacy customer row; override any column to craft an edge case."""
    row: dict[str, Any] = {
        "cust_id": cust_id,
        "full_name": f"Customer {cust_id}",
        "email": f"customer{cust_id}@example.com",
        "phone": "416-555-0100",
        "country": "CA",
        "signup_date": "15/06/2023",
        "balance_cents": 0,
        "status": "A",
    }
    row.update(overrides)
    return row


def legacy_order(order_id: int, cust_id: int, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "order_id": order_id,
        "cust_id": cust_id,
        "amount_cents": 1999,
        "order_date": "01/06/2024",
    }
    row.update(overrides)
    return row


def load_legacy(
    source: DatabaseClient,
    customers: Sequence[dict[str, Any]],
    orders: Sequence[dict[str, Any]] = (),
) -> None:
    source.execute_many(
        "INSERT INTO legacy_customers VALUES (:cust_id, :full_name, :email, :phone, :country, "
        ":signup_date, :balance_cents, :status)",
        customers,
    )
    source.execute_many(
        "INSERT INTO legacy_orders VALUES (:order_id, :cust_id, :amount_cents, :order_date)", orders
    )
