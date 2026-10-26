"""
Module  : tests/data/test_etl_validator.py
Author  : Anil Kalisetti
Purpose : Prove the validator itself catches every class of defect ("test the tests").

A validator that never fails is worse than none: it gives false confidence. Each test below
deliberately corrupts a copy of correct data and requires the matching check to FAIL.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from framework.data.etl_validator import ETLValidator, values_equal
from framework.db.client import DatabaseClient

pytestmark = pytest.mark.etl

_DDL = "CREATE TABLE {name} (id INTEGER, name TEXT, amount NUMERIC)"


@pytest.fixture
def twin_tables(etl_source: DatabaseClient, etl_target: DatabaseClient) -> ETLValidator:
    """Identical three-row tables on both sides; tests then corrupt the target."""
    rows = [{"id": 1, "name": "Ann", "amount": "10.50"}, {"id": 2, "name": "Bob", "amount": "20.00"},
            {"id": 3, "name": "Cy", "amount": "5.25"}]  # fmt: skip
    for db, table in ((etl_source, "src"), (etl_target, "tgt")):
        db.execute(_DDL.format(name=table))
        db.execute_many(f"INSERT INTO {table} VALUES (:id, :name, :amount)", rows)
    return ETLValidator(etl_source, etl_target)


def _diff(v: ETLValidator, **kwargs):
    return v.dataset_diff("SELECT * FROM src ORDER BY id", "SELECT * FROM tgt ORDER BY id", "id", **kwargs)


def test_identical_data_passes_every_check(twin_tables):
    assert _diff(twin_tables).passed
    assert twin_tables.row_count("src", "tgt").passed
    assert twin_tables.aggregate_check("src", "SUM(amount)", "tgt", "SUM(amount)").passed
    assert twin_tables.duplicate_check("tgt", ["id"]).passed
    assert twin_tables.null_check("tgt", ["id", "name"]).passed


def test_missing_row_is_reported_with_its_key(twin_tables, etl_target):
    etl_target.execute("DELETE FROM tgt WHERE id = 2")
    result = _diff(twin_tables)
    assert not result.passed
    assert result.details["missing_keys"] == [2]


def test_extra_row_is_reported_with_its_key(twin_tables, etl_target):
    etl_target.execute("INSERT INTO tgt VALUES (99, 'Ghost', '1.00')")
    result = _diff(twin_tables)
    assert not result.passed
    assert result.details["extra_keys"] == [99]


def test_changed_value_is_reported_with_expected_and_actual(twin_tables, etl_target):
    etl_target.execute("UPDATE tgt SET name = 'Bobby' WHERE id = 2")
    result = _diff(twin_tables)
    assert result.details["mismatches"] == [{"id": 2, "differences": {"name": {"expected": "Bob", "actual": "Bobby"}}}]


def test_penny_difference_in_money_is_detected(twin_tables, etl_target):
    etl_target.execute("UPDATE tgt SET amount = '10.51' WHERE id = 1")
    assert not _diff(twin_tables).passed


def test_missing_first_and_last_rows_are_both_found(twin_tables, etl_target):
    etl_target.execute("DELETE FROM tgt WHERE id IN (1, 3)")  # boundary rows are classic merge-join bugs
    assert _diff(twin_tables).details["missing_keys"] == [1, 3]


def test_empty_target_reports_every_source_row_missing(twin_tables, etl_target):
    etl_target.execute("DELETE FROM tgt")
    assert _diff(twin_tables).details["missing"] == 3


def test_empty_source_reports_every_target_row_extra(twin_tables, etl_source):
    etl_source.execute("DELETE FROM src")
    assert _diff(twin_tables).details["extra"] == 3


def test_ignore_keys_excludes_expected_rejects(twin_tables, etl_target):
    etl_target.execute("DELETE FROM tgt WHERE id = 3")
    assert _diff(twin_tables, ignore_keys=[3]).passed


def test_report_is_capped_but_counts_are_complete(twin_tables, etl_target):
    etl_target.execute("DELETE FROM tgt")
    result = _diff(twin_tables, max_reported=1)
    assert len(result.details["missing_keys"]) == 1
    assert result.details["missing"] == 3


def test_transform_defines_expected_target_values(twin_tables, etl_target):
    etl_target.execute("UPDATE tgt SET name = UPPER(name)")
    assert _diff(twin_tables, transform=lambda s: {"name": s["name"].upper()}).passed
    assert not _diff(twin_tables).passed  # without the rule, uppercase looks like corruption


def test_row_count_detects_loss_and_honours_expected_rejects(twin_tables, etl_target):
    etl_target.execute("DELETE FROM tgt WHERE id = 1")
    assert not twin_tables.row_count("src", "tgt").passed
    assert twin_tables.row_count("src", "tgt", expected_rejects=1).passed


def test_aggregate_tolerance(twin_tables, etl_target):
    etl_target.execute("UPDATE tgt SET amount = '10.51' WHERE id = 1")
    assert not twin_tables.aggregate_check("src", "SUM(amount)", "tgt", "SUM(amount)").passed
    assert twin_tables.aggregate_check(
        "src", "SUM(amount)", "tgt", "SUM(amount)", tolerance=Decimal("0.02")
    ).passed


def test_aggregate_filter_limits_each_side(twin_tables):
    result = twin_tables.aggregate_check(
        "src", "SUM(amount)", "tgt", "SUM(amount)", source_where="id <= 2", target_where="id <= 2"
    )
    assert result.passed
    assert result.details["source"] == "30.5"


def test_duplicate_key_is_detected(twin_tables, etl_target):
    etl_target.execute("INSERT INTO tgt VALUES (1, 'Ann again', '1.00')")
    result = twin_tables.duplicate_check("tgt", ["id"])
    assert not result.passed
    assert result.details["duplicates"][0]["id"] == 1


@pytest.mark.parametrize("bad_value", ["NULL", "''", "'   '"], ids=["null", "empty-string", "whitespace"])
def test_null_check_treats_blank_as_missing_unless_told_otherwise(twin_tables, etl_target, bad_value):
    etl_target.execute(f"UPDATE tgt SET name = {bad_value} WHERE id = 1")
    assert not twin_tables.null_check("tgt", ["name"]).passed


def test_null_check_can_ignore_blank_strings(twin_tables, etl_target):
    etl_target.execute("UPDATE tgt SET name = '' WHERE id = 1")
    assert twin_tables.null_check("tgt", ["name"], include_blank=False).passed


def test_orphan_check_finds_child_without_parent(twin_tables, etl_target):
    etl_target.execute("CREATE TABLE child (id INTEGER, tgt_id INTEGER)")
    etl_target.execute("INSERT INTO child VALUES (1, 1), (2, 42), (3, NULL)")
    result = twin_tables.orphan_check("child", "tgt_id", "tgt", "id")
    assert not result.passed
    assert result.details["orphans"] == 1  # NULL foreign keys are not orphans


def test_identifiers_are_validated_against_sql_injection(twin_tables):
    with pytest.raises(ValueError, match="Unsafe SQL identifier"):
        twin_tables.null_check("tgt; DROP TABLE tgt", ["name"])
    with pytest.raises(ValueError, match="Unsafe SQL identifier"):
        twin_tables.duplicate_check("tgt", ["id) --"])


@pytest.mark.parametrize(
    ("expected", "actual", "equal"),
    [
        (Decimal("12.30"), 12.3, True),
        (Decimal("0.10"), "0.1", True),
        (Decimal("0.1"), 0.1 + 0.2 - 0.2, False),  # binary-float noise must be visible
        ("a", "a", True),
        (1, 1.0, True),
        (None, None, True),
        (None, "", False),
        (Decimal("1"), "not-a-number", False),
    ],
)
def test_values_equal(expected, actual, equal):
    assert values_equal(expected, actual) is equal
