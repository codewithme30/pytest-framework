"""
Module  : tests/data/test_customer_migration_etl.py
Author  : Anil Kalisetti
Purpose : End-to-end ETL validation of the legacy-CRM -> warehouse migration.

Layers of assurance, from broad to narrow:
    1. Reconciliation   counts, schema, keys, aggregates       (nothing lost or invented)
    2. Transformation   every business rule on curated data    (values are RIGHT, not just present)
    3. Data quality     nulls, duplicates, referential integrity
    4. Edge cases       dates, unicode, injection-looking text, boundaries, rejects
    5. Operations       idempotent re-run, empty source, incremental change, volume

The expected values below are written out by hand, independent of the production transform
code. An oracle that reuses the code under test would only prove the code agrees with itself.
"""

from __future__ import annotations

import time
from decimal import Decimal

import pytest

from framework.sample_app.customer_migration import (
    legacy_customer,
    legacy_order,
    load_legacy,
    run_migration,
    transform_customer,
)

pytestmark = pytest.mark.etl  # the "data" layer marker is applied automatically by folder

# --- curated baseline ------------------------------------------------------------------------------
BASELINE_CUSTOMERS = [
    legacy_customer(1, full_name="Priya Nair", email="priya.nair@example.com", phone="(416) 555-0101",
                    country="Canada", signup_date="05/03/2021", balance_cents=125050, status="A"),
    legacy_customer(2, full_name="  Tom   O'Brien ", email="TOM.OBRIEN@EXAMPLE.COM", phone=None,
                    country="usa", signup_date="29/02/2024", balance_cents=-2500, status="I"),
    legacy_customer(3, full_name="José Müller", email="jose@example.com", phone="+1 905 555 0199",
                    country="de", signup_date="31/12/1999", balance_cents=0, status="A"),
    legacy_customer(4, full_name="张 伟", email="wei.zhang@example.cn", phone="010-5555-0100",
                    country="CN", signup_date="01/01/2020", balance_cents=9_999_999_999, status="A"),
    legacy_customer(5, full_name="Madonna", email="madonna@example.com", phone="0044 0207",
                    country=None, signup_date="01/01/2000", balance_cents=None, status=None),
]  # fmt: skip

BASELINE_ORDERS = [
    legacy_order(101, 1, amount_cents=1999, order_date="01/06/2024"),
    legacy_order(102, 1, amount_cents=25000, order_date="15/06/2024"),
    legacy_order(103, 2, amount_cents=-500, order_date="02/06/2024"),  # refund
    legacy_order(104, 3, amount_cents=0, order_date="03/06/2024"),
    legacy_order(105, 4, amount_cents=1, order_date="04/06/2024"),  # one cent
]

EXPECTED_CUSTOMERS = {
    1: dict(first_name="Priya", last_name="Nair", email="priya.nair@example.com", phone_digits="4165550101",
            country_code="CA", signup_date="2021-03-05", balance=Decimal("1250.50"), is_active=1),
    2: dict(first_name="Tom", last_name="O'Brien", email="tom.obrien@example.com", phone_digits=None,
            country_code="US", signup_date="2024-02-29", balance=Decimal("-25.00"), is_active=0),
    3: dict(first_name="José", last_name="Müller", email="jose@example.com", phone_digits="19055550199",
            country_code="DE", signup_date="1999-12-31", balance=Decimal("0.00"), is_active=1),
    4: dict(first_name="张", last_name="伟", email="wei.zhang@example.cn", phone_digits="01055550100",
            country_code="CN", signup_date="2020-01-01", balance=Decimal("99999999.99"), is_active=1),
    5: dict(first_name="Madonna", last_name="", email="madonna@example.com", phone_digits="00440207",
            country_code="ZZ", signup_date="2000-01-01", balance=Decimal("0.00"), is_active=0),
}  # fmt: skip

EXPECTED_ORDERS = {
    101: dict(customer_id=1, amount=Decimal("19.99"), order_date="2024-06-01"),
    102: dict(customer_id=1, amount=Decimal("250.00"), order_date="2024-06-15"),
    103: dict(customer_id=2, amount=Decimal("-5.00"), order_date="2024-06-02"),
    104: dict(customer_id=3, amount=Decimal("0.00"), order_date="2024-06-03"),
    105: dict(customer_id=4, amount=Decimal("0.01"), order_date="2024-06-04"),
}

CUSTOMER_SQL_SRC = "SELECT * FROM legacy_customers ORDER BY cust_id"
CUSTOMER_SQL_TGT = "SELECT * FROM dim_customer ORDER BY customer_id"
ORDER_SQL_SRC = "SELECT * FROM legacy_orders ORDER BY order_id"
ORDER_SQL_TGT = "SELECT * FROM fact_order ORDER BY order_id"


@pytest.fixture
def migrated(pipeline):
    """Source loaded with the baseline data and the migration already executed."""
    source, target = pipeline
    load_legacy(source, BASELINE_CUSTOMERS, BASELINE_ORDERS)
    stats = run_migration(source, target)
    return source, target, stats


# =====================================================================================================
# 1. Reconciliation
# =====================================================================================================
def test_row_counts_reconcile(migrated, validator):
    validator.row_count("legacy_customers", "dim_customer").assert_passed()
    validator.row_count("legacy_orders", "fact_order").assert_passed()


def test_migration_statistics_match_reality(migrated):
    _, target, stats = migrated
    assert (stats.customers_read, stats.customers_loaded) == (5, 5)
    assert (stats.orders_read, stats.orders_loaded) == (5, 5)
    assert stats.rejects == target.row_count("migration_rejects") == 0


def test_target_schema_contains_every_mapped_column(migrated, validator):
    validator.schema_match(
        "legacy_customers", "dim_customer",
        {"cust_id": "customer_id", "email": "email", "signup_date": "signup_date", "status": "is_active"},
    ).assert_passed()  # fmt: skip


def test_schema_check_detects_a_missing_target_column(migrated, validator):
    result = validator.schema_match("legacy_customers", "dim_customer", {"cust_id": "customer_uuid"})
    assert not result.passed
    assert result.details["missing_target"] == ["customer_uuid"]


def test_no_customer_is_lost_or_invented(migrated, validator):
    result = validator.dataset_diff(
        CUSTOMER_SQL_SRC, CUSTOMER_SQL_TGT, "cust_id", "customer_id", transform=lambda s: {}
    )  # empty transform = key-only comparison
    result.assert_passed()
    assert result.details["compared"] == 5


def test_order_total_reconciles_to_the_cent(migrated, validator):
    validator.aggregate_check(
        "legacy_orders", "SUM(amount_cents) / 100.0", "fact_order", "SUM(amount)", tolerance=Decimal("0.005")
    ).assert_passed()


# =====================================================================================================
# 2. Transformation rules (hand-written oracle)
# =====================================================================================================
def test_every_customer_matches_the_business_rules(migrated, validator):
    validator.dataset_diff(
        CUSTOMER_SQL_SRC, CUSTOMER_SQL_TGT, "cust_id", "customer_id",
        transform=lambda src: EXPECTED_CUSTOMERS[src["cust_id"]],
    ).assert_passed()  # fmt: skip


def test_every_order_is_converted_correctly(migrated, validator):
    validator.dataset_diff(
        ORDER_SQL_SRC, ORDER_SQL_TGT, "order_id",
        transform=lambda src: EXPECTED_ORDERS[src["order_id"]],
    ).assert_passed()  # fmt: skip


def test_dataset_diff_catches_a_wrong_value(migrated, validator):
    _, target, _ = migrated
    target.execute("UPDATE dim_customer SET last_name = 'WRONG' WHERE customer_id = 1")
    result = validator.dataset_diff(
        CUSTOMER_SQL_SRC, CUSTOMER_SQL_TGT, "cust_id", "customer_id",
        transform=lambda src: EXPECTED_CUSTOMERS[src["cust_id"]],
    )  # fmt: skip
    assert not result.passed
    assert result.details["mismatches"][0]["differences"]["last_name"] == {"expected": "Nair", "actual": "WRONG"}


# =====================================================================================================
# 3. Data quality
# =====================================================================================================
def test_mandatory_columns_have_no_nulls_or_blanks(migrated, validator):
    validator.null_check(
        "dim_customer", ["customer_id", "first_name", "email", "country_code", "signup_date", "balance"]
    ).assert_passed()
    validator.null_check("fact_order", ["order_id", "customer_id", "amount", "order_date"]).assert_passed()


def test_no_duplicate_keys_or_emails(migrated, validator):
    validator.duplicate_check("dim_customer", ["customer_id"]).assert_passed()
    validator.duplicate_check("dim_customer", ["email"]).assert_passed()


def test_every_order_belongs_to_a_loaded_customer(migrated, validator):
    validator.orphan_check("fact_order", "customer_id", "dim_customer", "customer_id").assert_passed()


# =====================================================================================================
# 4. Edge cases
# =====================================================================================================
REJECT_CASES = [
    pytest.param({"signup_date": "31/02/2024"}, "INVALID_DATE", id="impossible-date-31-feb"),
    pytest.param({"signup_date": "29/02/2023"}, "INVALID_DATE", id="non-leap-year-29-feb"),
    pytest.param({"signup_date": "12/31/2024"}, "INVALID_DATE", id="us-month-day-order"),
    pytest.param({"signup_date": "2024-03-05"}, "INVALID_DATE", id="iso-date-in-legacy-field"),
    pytest.param({"signup_date": None}, "INVALID_DATE", id="null-date"),
    pytest.param({"full_name": "   "}, "MISSING_NAME", id="blank-name"),
    pytest.param({"full_name": None}, "MISSING_NAME", id="null-name"),
    pytest.param({"email": "no-at-sign"}, "INVALID_EMAIL", id="email-without-at"),
    pytest.param({"email": "missing@tld"}, "INVALID_EMAIL", id="email-without-tld"),
    pytest.param({"email": None}, "INVALID_EMAIL", id="null-email"),
]


@pytest.mark.parametrize(("overrides", "reason"), REJECT_CASES)
def test_bad_records_are_rejected_with_a_reason_not_silently_dropped(pipeline, overrides, reason):
    source, target = pipeline
    load_legacy(source, [legacy_customer(1, **overrides)])
    run_migration(source, target)
    assert target.row_count("dim_customer") == 0
    assert target.fetch_all("SELECT source_table, source_id, reason FROM migration_rejects") == [
        {"source_table": "legacy_customers", "source_id": 1, "reason": reason}
    ]


LOADED_CASES = [
    pytest.param({"signup_date": "29/02/2024"}, {"signup_date": "2024-02-29"}, id="leap-day-accepted"),
    pytest.param({"full_name": "Zoë Åström"}, {"first_name": "Zoë", "last_name": "Åström"}, id="accented-letters"),
    pytest.param({"full_name": "Robert'); DROP TABLE dim_customer;--"},
                 {"first_name": "Robert');", "last_name": "DROP TABLE dim_customer;--"}, id="sql-injection-looking-name"),
    pytest.param({"full_name": "A" * 255}, {"first_name": "A" * 255}, id="255-char-name-not-truncated"),
    pytest.param({"email": "  MiXeD@Example.COM "}, {"email": "mixed@example.com"}, id="email-trimmed-and-lowercased"),
    pytest.param({"phone": "0123"}, {"phone_digits": "0123"}, id="leading-zero-phone-preserved"),
    pytest.param({"phone": "---"}, {"phone_digits": None}, id="symbols-only-phone-becomes-null"),
    pytest.param({"phone": ""}, {"phone_digits": None}, id="empty-phone-becomes-null"),
    pytest.param({"country": "Narnia"}, {"country_code": "ZZ"}, id="unknown-country"),
    pytest.param({"country": " united states "}, {"country_code": "US"}, id="country-name-mapped"),
    pytest.param({"balance_cents": None}, {"balance": Decimal("0.00")}, id="null-balance-is-zero"),
    pytest.param({"balance_cents": -1}, {"balance": Decimal("-0.01")}, id="negative-one-cent"),
    pytest.param({"balance_cents": 9_999_999_999}, {"balance": Decimal("99999999.99")}, id="max-balance"),
    pytest.param({"status": "a"}, {"is_active": 1}, id="lowercase-status-active"),
    pytest.param({"status": "X"}, {"is_active": 0}, id="unknown-status-inactive"),
    pytest.param({"full_name": "Cher"}, {"first_name": "Cher", "last_name": ""}, id="single-word-name"),
]  # fmt: skip


@pytest.mark.parametrize(("overrides", "expected"), LOADED_CASES)
def test_edge_values_are_loaded_exactly_as_specified(pipeline, overrides, expected):
    source, target = pipeline
    load_legacy(source, [legacy_customer(1, **overrides)])
    run_migration(source, target)
    row = target.fetch_one("SELECT * FROM dim_customer WHERE customer_id = 1")
    assert row is not None, "record was unexpectedly rejected"
    for column, value in expected.items():
        actual = row[column]
        assert (Decimal(str(actual)) == value) if isinstance(value, Decimal) else (actual == value), column


def test_duplicate_email_is_case_insensitive_and_first_record_wins(pipeline):
    source, target = pipeline
    load_legacy(source, [
        legacy_customer(1, email="Same@Example.com"),
        legacy_customer(2, email="same@EXAMPLE.COM"),
        legacy_customer(3, email=" SAME@example.com "),
    ])  # fmt: skip
    run_migration(source, target)
    assert [r["customer_id"] for r in target.fetch_all("SELECT customer_id FROM dim_customer")] == [1]
    rejected = target.fetch_all("SELECT source_id, reason FROM migration_rejects ORDER BY source_id")
    assert rejected == [{"source_id": 2, "reason": "DUPLICATE_EMAIL"}, {"source_id": 3, "reason": "DUPLICATE_EMAIL"}]


def test_order_for_unknown_customer_is_rejected_as_orphan(pipeline):
    source, target = pipeline
    load_legacy(source, [legacy_customer(1)], [legacy_order(10, 1), legacy_order(11, 999)])
    run_migration(source, target)
    assert target.row_count("fact_order") == 1
    assert target.fetch_one("SELECT reason FROM migration_rejects WHERE source_id = 11")["reason"] == "ORPHAN_CUSTOMER"


def test_order_of_a_rejected_customer_is_also_rejected(pipeline):
    source, target = pipeline
    load_legacy(source, [legacy_customer(1, signup_date="31/02/2024")], [legacy_order(10, 1)])
    run_migration(source, target)
    assert target.row_count("fact_order") == 0


def test_order_with_invalid_date_is_rejected(pipeline):
    source, target = pipeline
    load_legacy(source, [legacy_customer(1)], [legacy_order(10, 1, order_date="30/02/2024")])
    run_migration(source, target)
    assert target.fetch_one("SELECT reason FROM migration_rejects")["reason"] == "INVALID_DATE"


@pytest.mark.parametrize(
    ("cents", "expected"),
    [(0, "0.00"), (1, "0.01"), (-1, "-0.01"), (99, "0.99"), (100, "1.00"), (123456789, "1234567.89")],
)
def test_order_amount_precision(pipeline, cents, expected):
    source, target = pipeline
    load_legacy(source, [legacy_customer(1)], [legacy_order(10, 1, amount_cents=cents)])
    run_migration(source, target)
    assert Decimal(str(target.scalar("SELECT amount FROM fact_order"))) == Decimal(expected)


# =====================================================================================================
# 5. Operations
# =====================================================================================================
def test_rerunning_the_migration_is_idempotent(migrated, validator):
    source, target, _ = migrated
    before = {t: target.row_count(t) for t in ("dim_customer", "fact_order", "migration_rejects")}
    run_migration(source, target)
    run_migration(source, target)
    assert {t: target.row_count(t) for t in before} == before
    validator.duplicate_check("dim_customer", ["customer_id"]).assert_passed()


def test_empty_source_produces_empty_target_without_error(pipeline):
    source, target = pipeline
    stats = run_migration(source, target)
    assert (stats.customers_read, stats.orders_read, stats.rejects) == (0, 0, 0)
    assert target.row_count("dim_customer") == target.row_count("fact_order") == 0


def test_single_record_migration(pipeline, validator):
    source, target = pipeline
    load_legacy(source, [legacy_customer(1)], [legacy_order(10, 1)])
    run_migration(source, target)
    validator.row_count("legacy_customers", "dim_customer").assert_passed()
    validator.row_count("legacy_orders", "fact_order").assert_passed()


def test_source_changes_flow_through_on_the_next_run(migrated):
    source, target, _ = migrated
    source.execute("UPDATE legacy_customers SET status = 'I', email = 'priya.new@example.com' WHERE cust_id = 1")
    run_migration(source, target)
    row = target.fetch_one("SELECT email, is_active FROM dim_customer WHERE customer_id = 1")
    assert row == {"email": "priya.new@example.com", "is_active": 0}


def test_expected_rejects_are_accounted_for_in_the_row_count(pipeline, validator):
    source, target = pipeline
    load_legacy(source, [legacy_customer(1), legacy_customer(2, email="bad"), legacy_customer(3, full_name="")])
    run_migration(source, target)
    validator.row_count("legacy_customers", "dim_customer", expected_rejects=2).assert_passed()
    assert not validator.row_count("legacy_customers", "dim_customer", expected_rejects=0).passed


@pytest.mark.slow
def test_volume_20k_customers_and_40k_orders_reconcile_within_budget(pipeline, validator):
    source, target = pipeline
    customers = [legacy_customer(i, balance_cents=i * 7) for i in range(1, 20_001)]
    orders = [legacy_order(i, (i % 20_000) + 1, amount_cents=i) for i in range(1, 40_001)]
    load_legacy(source, customers, orders)

    started = time.perf_counter()
    stats = run_migration(source, target, batch_size=2_000)
    elapsed = time.perf_counter() - started

    assert (stats.customers_loaded, stats.orders_loaded, stats.rejects) == (20_000, 40_000, 0)
    assert elapsed < 60, f"migration took {elapsed:.1f}s"  # generous: guards against accidental O(n^2)
    validator.aggregate_check(
        "legacy_orders", "SUM(amount_cents) / 100.0", "fact_order", "SUM(amount)", tolerance=Decimal("0.01")
    ).assert_passed()
    validator.dataset_diff(
        CUSTOMER_SQL_SRC, CUSTOMER_SQL_TGT, "cust_id", "customer_id",
        transform=lambda s: {k: v for k, v in transform_customer(s)[0].items() if k != "customer_id"},
    ).assert_passed()  # fmt: skip
