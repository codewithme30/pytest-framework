"""
Module  : framework.db.repository
Author  : Anil Kalisetti
Purpose : Read test data FROM a database and write execution results BACK to it.

Real-life pattern: a QA team keeps test scenarios in a table (owned by business analysts),
tests pull the rows marked ``NEW``, run them, then record PASSED/FAILED plus the actual
value so analysts can review outcomes in the same place where they maintain the data.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from framework.db.client import DatabaseClient, safe_identifier

STATUS_NEW = "NEW"
STATUS_PASSED = "PASSED"
STATUS_FAILED = "FAILED"


class DataRepository:
    def __init__(self, db: DatabaseClient, table: str = "tax_test_data") -> None:
        self._db = db
        self._table = safe_identifier(table)

    def fetch_cases(
        self, statuses: Sequence[str] = (STATUS_NEW,), limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Return scenario rows whose status is in ``statuses``, ordered by id."""
        binds = {f"s{i}": status for i, status in enumerate(statuses)}
        placeholders = ", ".join(f":{name}" for name in binds)
        sql = f"SELECT * FROM {self._table} WHERE status IN ({placeholders}) ORDER BY id"
        if limit is not None:
            sql += " LIMIT :limit"  # LIMIT is portable across SQLite/Postgres/MySQL
            binds["limit"] = limit
        return self._db.fetch_all(sql, binds)

    def record_result(
        self, case_id: int, passed: bool, actual: str | None = None, error: str | None = None
    ) -> None:
        """Write the outcome back to the row (the 'update data back to the database' step)."""
        self._db.execute(
            f"UPDATE {self._table} SET status = :status, actual_total = :actual, "
            "error_message = :error, executed_at = :ts WHERE id = :id",
            {
                "status": STATUS_PASSED if passed else STATUS_FAILED,
                "actual": actual,
                "error": (error or "")[:500] or None,
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "id": case_id,
            },
        )

    def status_summary(self) -> dict[str, int]:
        rows = self._db.fetch_all(
            f"SELECT status, COUNT(*) AS n FROM {self._table} GROUP BY status"
        )
        return {row["status"]: int(row["n"]) for row in rows}
