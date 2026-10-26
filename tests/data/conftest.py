"""
Module  : tests/data/conftest.py
Author  : Anil Kalisetti
Purpose : Fresh in-memory source and target databases for every ETL test.

In-memory SQLite keeps the suite fast and hermetic (no shared state, safe under xdist).
To validate a REAL migration, point ETL_SOURCE_DB_URL / ETL_TARGET_DB_URL at the actual
systems and reuse the same ``ETLValidator`` checks; see docs/ARCHITECTURE.md.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from framework.data.etl_validator import ETLValidator
from framework.db.client import DatabaseClient
from framework.sample_app.customer_migration import create_schemas


@pytest.fixture
def etl_source() -> Iterator[DatabaseClient]:
    db = DatabaseClient("sqlite://")
    yield db
    db.dispose()


@pytest.fixture
def etl_target() -> Iterator[DatabaseClient]:
    db = DatabaseClient("sqlite://")
    yield db
    db.dispose()


@pytest.fixture
def pipeline(etl_source: DatabaseClient, etl_target: DatabaseClient) -> tuple[DatabaseClient, DatabaseClient]:
    """Source and target with the sample schemas created but no rows loaded."""
    create_schemas(etl_source, etl_target)
    return etl_source, etl_target


@pytest.fixture
def validator(pipeline: tuple[DatabaseClient, DatabaseClient]) -> ETLValidator:
    return ETLValidator(*pipeline)
