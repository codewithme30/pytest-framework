"""
Module  : framework.db.client
Author  : Anil Kalisetti
Purpose : One small client that works with any SQLAlchemy-supported database.

Switching databases is a connection-string change (install the matching driver first):
    sqlite:///reports/sample_test.db                          (built in)
    postgresql+psycopg2://user:***@host:5432/orders           (pip install psycopg2-binary)
    mysql+pymysql://user:***@host:3306/orders                 (pip install pymysql)
    mssql+pyodbc://user:***@dsn                               (pip install pyodbc)
    oracle+oracledb://user:***@host:1521/?service_name=ORCL   (pip install oracledb)

Safety rules enforced here:
    * Values are ALWAYS bound parameters (``:name``), never string-formatted -> no SQL injection.
    * Table/column names cannot be bound, so they pass through ``safe_identifier`` first.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine

from framework.core.logger import get_logger

log = get_logger("db.client")

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


def safe_identifier(name: str) -> str:
    """Allow only ``table`` or ``schema.table`` style names; raise ``ValueError`` otherwise."""
    if not _IDENTIFIER.match(name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return name


class DatabaseClient:
    def __init__(self, url: str, **engine_kwargs: Any) -> None:
        if url.startswith("sqlite"):
            # Parallel (xdist) workers share one SQLite file: wait for locks instead of failing.
            engine_kwargs.setdefault("connect_args", {"timeout": 30})
        self._engine: Engine = create_engine(url, pool_pre_ping=True, **engine_kwargs)
        self.dialect = self._engine.dialect.name

    def _adapt(self, params: Mapping[str, Any] | None) -> dict[str, Any]:
        """Prepare bind values. SQLite cannot bind ``Decimal``; store it as exact text instead.

        Other drivers (psycopg2, oracledb, pyodbc...) accept ``Decimal`` natively and keep
        full precision, so values pass through untouched there.
        """
        values = dict(params or {})
        if self.dialect == "sqlite":
            values = {k: str(v) if isinstance(v, Decimal) else v for k, v in values.items()}
        return values

    # --- reads --------------------------------------------------------------------------
    def fetch_all(self, sql: str, params: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        """Return every row as a dict. For big result sets use ``stream`` instead."""
        with self._engine.connect() as conn:
            return [dict(row) for row in conn.execute(text(sql), self._adapt(params)).mappings()]

    def fetch_one(self, sql: str, params: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
        with self._engine.connect() as conn:
            row = conn.execute(text(sql), self._adapt(params)).mappings().first()
            return dict(row) if row is not None else None

    def scalar(self, sql: str, params: Mapping[str, Any] | None = None) -> Any:
        with self._engine.connect() as conn:
            return conn.execute(text(sql), self._adapt(params)).scalar()

    def stream(
        self, sql: str, params: Mapping[str, Any] | None = None, chunk_size: int = 1000
    ) -> Iterator[dict[str, Any]]:
        """Yield rows lazily in chunks so memory stays flat for million-row tables."""
        with self._engine.connect().execution_options(stream_results=True) as conn:
            result = conn.execute(text(sql), self._adapt(params))
            for partition in result.mappings().partitions(chunk_size):
                for row in partition:
                    yield dict(row)

    # --- writes -----------------------------------------------------------------------------
    def execute(self, sql: str, params: Mapping[str, Any] | None = None) -> int:
        """Run one statement in its own transaction; return the affected row count."""
        with self._engine.begin() as conn:
            return conn.execute(text(sql), self._adapt(params)).rowcount

    def execute_many(self, sql: str, rows: Sequence[Mapping[str, Any]]) -> int:
        """Bulk insert/update with a list of parameter dicts (one round trip per batch)."""
        if not rows:
            return 0
        with self._engine.begin() as conn:
            return conn.execute(text(sql), [self._adapt(r) for r in rows]).rowcount

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        """Group several statements; commits on success, rolls back on any exception."""
        with self._engine.begin() as conn:
            yield conn

    # --- metadata ------------------------------------------------------------------------------
    def table_exists(self, table: str) -> bool:
        return inspect(self._engine).has_table(table)

    def columns(self, table: str) -> list[dict[str, Any]]:
        """Column metadata: ``[{'name': 'id', 'type': INTEGER(), 'nullable': False, ...}]``."""
        return inspect(self._engine).get_columns(table)

    def row_count(self, table: str) -> int:
        return int(self.scalar(f"SELECT COUNT(*) FROM {safe_identifier(table)}"))

    def dispose(self) -> None:
        self._engine.dispose()
