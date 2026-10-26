"""
Module  : tests/db/conftest.py
Author  : Anil Kalisetti
Purpose : Database fixtures: a shared handle to the configured DB, and a scratch in-memory DB.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from framework.config.settings import Settings
from framework.core.parallel import current_db_url
from framework.db.client import DatabaseClient
from framework.db.repository import DataRepository


@pytest.fixture(scope="session")
def db(settings: Settings) -> Iterator[DatabaseClient]:
    """The database from DB_URL (the seeded sample SQLite file by default).

    Under pytest-xdist each worker gets its own SQLite copy, so parallel write-backs are safe.
    """
    client = DatabaseClient(current_db_url(settings.db_url))
    yield client
    client.dispose()


@pytest.fixture
def repo(db: DatabaseClient) -> DataRepository:
    return DataRepository(db)


@pytest.fixture
def scratch_db() -> Iterator[DatabaseClient]:
    """Private in-memory database: tests can create, corrupt and drop anything safely."""
    client = DatabaseClient("sqlite://")
    yield client
    client.dispose()
