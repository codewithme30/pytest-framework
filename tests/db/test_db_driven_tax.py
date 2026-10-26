"""
Module  : tests/db/test_db_driven_tax.py
Author  : Anil Kalisetti
Purpose : Data-driven testing where the scenarios live IN the database.

Flow (the pattern many QA teams run against a shared test-data table):
    1. Collection time : read every row with status NEW  -> one pytest test per row
    2. Execution       : run the system under test with the row's inputs
    3. Write-back      : record PASSED/FAILED, the actual value and a timestamp on the same row
    4. Assertion       : fail the test if the actual value differs from the expectation

Business analysts can add a scenario with a single INSERT; no code change, no deployment.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import SQLAlchemyError

from framework.config.settings import get_settings
from framework.db.client import DatabaseClient
from framework.db.repository import DataRepository
from framework.sample_app.tax_calculator import calculate_total


def _load_cases() -> list:
    """Runs at collection time. A missing table skips the module instead of erroring the run."""
    client = DatabaseClient(get_settings().db_url)
    try:
        rows = DataRepository(client).fetch_cases()
    except SQLAlchemyError:
        return [pytest.param(None, marks=pytest.mark.skip(reason="tax_test_data table not found"), id="no-data")]
    finally:
        client.dispose()
    return [pytest.param(row, id=f"{row['id']:02d}-{row['scenario']}") for row in rows]


CASES = _load_cases()


@pytest.mark.regression
@pytest.mark.parametrize("case", CASES)
def test_tax_total_matches_database_expectation(case, repo):
    actual, error = None, None
    try:
        actual = str(calculate_total(case["subtotal"], case["province"]))
    except ValueError as exc:
        error = type(exc).__name__

    if case["expected_error"]:
        passed = error == case["expected_error"]
    else:
        passed = actual == case["expected_total"]

    # Write the outcome back BEFORE asserting, so a failing scenario is still recorded.
    repo.record_result(case["id"], passed, actual=actual, error=error)

    expectation = case["expected_error"] or case["expected_total"]
    assert passed, f"{case['scenario']}: expected {expectation}, got {actual or error}"


def test_database_scenarios_were_loaded():
    """Guards against a silently empty table making the whole module look green."""
    assert any(param.values[0] is not None for param in CASES), "no scenarios found in tax_test_data"
