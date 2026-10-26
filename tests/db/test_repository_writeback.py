"""
Module  : tests/db/test_repository_writeback.py
Author  : Anil Kalisetti
Purpose : The read-test-data / write-results-back contract, on a private scratch database.
"""

from __future__ import annotations

import pytest

from framework.db.repository import STATUS_FAILED, STATUS_NEW, STATUS_PASSED, DataRepository
from framework.db.sample_data import seed_sample_database


@pytest.fixture
def seeded_repo(scratch_db):
    seed_sample_database(scratch_db)
    return DataRepository(scratch_db)


def test_fetch_cases_returns_only_new_rows_in_id_order(seeded_repo):
    cases = seeded_repo.fetch_cases()
    assert len(cases) == 15
    assert [c["id"] for c in cases] == sorted(c["id"] for c in cases)
    assert {c["status"] for c in cases} == {STATUS_NEW}


def test_limit_restricts_the_batch_size(seeded_repo):
    assert len(seeded_repo.fetch_cases(limit=3)) == 3


def test_pass_result_is_written_back_with_timestamp(seeded_repo):
    seeded_repo.record_result(1, True, actual="113.00")
    row = seeded_repo.fetch_cases(statuses=[STATUS_PASSED])[0]
    assert (row["id"], row["actual_total"], row["error_message"]) == (1, "113.00", None)
    assert row["executed_at"].endswith("+00:00")  # stored in UTC, unambiguous across time zones


def test_fail_result_stores_error_and_leaves_other_rows_untouched(seeded_repo):
    seeded_repo.record_result(2, False, actual="104.99", error="AssertionError: off by one cent")
    summary = seeded_repo.status_summary()
    assert summary == {STATUS_NEW: 14, STATUS_FAILED: 1}
    assert seeded_repo.fetch_cases(statuses=[STATUS_FAILED])[0]["error_message"].startswith("AssertionError")


def test_processed_rows_are_not_picked_up_again(seeded_repo):
    seeded_repo.record_result(1, True, actual="113.00")
    assert 1 not in [c["id"] for c in seeded_repo.fetch_cases()]


def test_very_long_error_text_is_truncated_not_rejected(seeded_repo):
    seeded_repo.record_result(1, False, error="x" * 5_000)
    assert len(seeded_repo.fetch_cases(statuses=[STATUS_FAILED])[0]["error_message"]) == 500


def test_unsafe_table_name_is_rejected(scratch_db):
    with pytest.raises(ValueError, match="Unsafe SQL identifier"):
        DataRepository(scratch_db, table="tax_test_data; DROP TABLE x")


def test_unknown_id_updates_nothing(seeded_repo):
    seeded_repo.record_result(9999, True, actual="1.00")
    assert seeded_repo.status_summary() == {STATUS_NEW: 15}


# --- inheritance: a second team reuses the same mechanics with their own table ----------------------
def test_repository_without_a_table_name_is_rejected(scratch_db):
    from framework.db.repository import ScenarioRepository

    with pytest.raises(TypeError, match="table"):
        ScenarioRepository(scratch_db)


def test_subclass_only_names_its_table(scratch_db):
    from framework.db.repository import ScenarioRepository

    class LoanCaseRepository(ScenarioRepository):
        table = "loan_cases"

    scratch_db.execute(
        "CREATE TABLE loan_cases (id INTEGER PRIMARY KEY, status TEXT, actual_total TEXT, "
        "error_message TEXT, executed_at TEXT)"
    )
    scratch_db.execute("INSERT INTO loan_cases (id, status) VALUES (1, 'NEW')")
    repo = LoanCaseRepository(scratch_db)
    assert [row["id"] for row in repo.fetch_cases()] == [1]
    repo.record_result(1, passed=True, actual="1000.00")
    assert repo.status_summary() == {"PASSED": 1}
