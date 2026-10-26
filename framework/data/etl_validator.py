"""
Module  : framework.data.etl_validator
Author  : Anil Kalisetti
Purpose : Reusable source-to-target validation for ETL, migration and reconciliation tests.

Checks provided (each returns a ``CheckResult``; call ``.assert_passed()`` in a test):

    row_count          source rows - expected rejects == target rows
    schema_match       every mapped column exists on both sides
    null_check         mandatory columns contain no NULL / blank values
    duplicate_check    business key is unique
    orphan_check       child rows all have a parent (referential integrity)
    aggregate_check    SUM / MIN / MAX / AVG / COUNT agree within a tolerance
    dataset_diff       row-by-row comparison: missing, extra and mismatched rows

Performance and memory:
    ``dataset_diff`` is a streaming MERGE JOIN: both sides are read in key order in small
    chunks and walked in lock-step, so memory stays constant whether the table has 1 thousand
    or 100 million rows. Counting and aggregates are pushed down to the database.

Real-life example: after moving 2 million customers from a legacy CRM to a warehouse, run
``dataset_diff`` with a ``transform`` that encodes the business rules; any row that was lost,
invented or altered is reported with the offending key and the expected/actual values.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from framework.db.client import DatabaseClient, safe_identifier

Side = Literal["source", "target"]
RowTransform = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def assert_passed(self) -> None:
        assert self.passed, f"[{self.name}] {self.message}"


def values_equal(expected: Any, actual: Any) -> bool:
    """Compare two cell values. Numbers compare numerically (12.3 == Decimal('12.30'))."""
    if isinstance(expected, Decimal) or isinstance(actual, Decimal):
        try:
            return Decimal(str(expected)) == Decimal(str(actual))
        except (InvalidOperation, ValueError):
            return False
    return expected == actual


class ETLValidator:
    def __init__(self, source: DatabaseClient, target: DatabaseClient) -> None:
        self._source = source
        self._target = target

    def _db(self, side: Side) -> DatabaseClient:
        return self._source if side == "source" else self._target

    # --- counts ----------------------------------------------------------------------
    def row_count(
        self, source_table: str, target_table: str, expected_rejects: int = 0
    ) -> CheckResult:
        src = self._source.row_count(source_table)
        tgt = self._target.row_count(target_table)
        expected = src - expected_rejects
        return CheckResult(
            "row_count",
            tgt == expected,
            f"source={src}, expected rejects={expected_rejects}, expected target={expected}, "
            f"actual target={tgt}",
            {"source": src, "target": tgt, "expected_rejects": expected_rejects},
        )

    # --- structure ----------------------------------------------------------------------------
    def schema_match(
        self, source_table: str, target_table: str, column_map: Mapping[str, str]
    ) -> CheckResult:
        """``column_map`` is ``{source_column: target_column}``; names compare case-insensitively."""
        src_cols = {c["name"].lower() for c in self._source.columns(source_table)}
        tgt_cols = {c["name"].lower() for c in self._target.columns(target_table)}
        missing_src = sorted(c for c in column_map if c.lower() not in src_cols)
        missing_tgt = sorted(c for c in column_map.values() if c.lower() not in tgt_cols)
        return CheckResult(
            "schema_match",
            not (missing_src or missing_tgt),
            f"missing in source: {missing_src}; missing in target: {missing_tgt}",
            {"missing_source": missing_src, "missing_target": missing_tgt},
        )

    # --- data quality ---------------------------------------------------------------------------
    def null_check(
        self, table: str, columns: Sequence[str], side: Side = "target", include_blank: bool = True
    ) -> CheckResult:
        """Count NULL (and optionally empty-string) values in mandatory columns."""
        offenders: dict[str, int] = {}
        for column in columns:
            col = safe_identifier(column)
            condition = f"{col} IS NULL"
            if include_blank:
                condition += f" OR TRIM(CAST({col} AS VARCHAR(4000))) = ''"
            count = int(self._db(side).scalar(f"SELECT COUNT(*) FROM {safe_identifier(table)} WHERE {condition}"))
            if count:
                offenders[column] = count
        return CheckResult("null_check", not offenders, f"NULL/blank counts: {offenders}", offenders)

    def duplicate_check(
        self, table: str, key_columns: Sequence[str], side: Side = "target"
    ) -> CheckResult:
        keys = ", ".join(safe_identifier(c) for c in key_columns)
        rows = self._db(side).fetch_all(
            f"SELECT {keys}, COUNT(*) AS n FROM {safe_identifier(table)} "
            f"GROUP BY {keys} HAVING COUNT(*) > 1"
        )
        return CheckResult(
            "duplicate_check", not rows, f"{len(rows)} duplicated key(s): {rows[:5]}", {"duplicates": rows[:20]}
        )

    def orphan_check(
        self,
        child_table: str,
        child_column: str,
        parent_table: str,
        parent_column: str,
        side: Side = "target",
    ) -> CheckResult:
        """Find child rows whose foreign key has no matching parent (e.g. order without customer)."""
        child, parent = safe_identifier(child_table), safe_identifier(parent_table)
        ccol, pcol = safe_identifier(child_column), safe_identifier(parent_column)
        orphans = int(
            self._db(side).scalar(
                f"SELECT COUNT(*) FROM {child} c LEFT JOIN {parent} p ON c.{ccol} = p.{pcol} "
                f"WHERE c.{ccol} IS NOT NULL AND p.{pcol} IS NULL"
            )
        )
        return CheckResult("orphan_check", orphans == 0, f"{orphans} orphan row(s) in {child}", {"orphans": orphans})

    def aggregate_check(
        self,
        source_table: str,
        source_expression: str,
        target_table: str,
        target_expression: str,
        tolerance: Decimal = Decimal("0"),
        source_where: str = "",
        target_where: str = "",
    ) -> CheckResult:
        """Compare e.g. ``SUM(amount_cents)/100.0`` (source) with ``SUM(amount)`` (target).

        Expressions and ``*_where`` filters are written by the test author (trusted code),
        never by end users. Use ``source_where`` to exclude rows the pipeline is expected to
        reject (e.g. ``"cust_id NOT IN (SELECT ...)"``). Use a tiny tolerance
        (``Decimal('0.005')``) only when a side stores binary floats.
        """
        src_filter = f" WHERE {source_where}" if source_where else ""
        tgt_filter = f" WHERE {target_where}" if target_where else ""
        src = self._source.scalar(
            f"SELECT {source_expression} FROM {safe_identifier(source_table)}{src_filter}"
        )
        tgt = self._target.scalar(
            f"SELECT {target_expression} FROM {safe_identifier(target_table)}{tgt_filter}"
        )
        src_d, tgt_d = Decimal(str(src or 0)), Decimal(str(tgt or 0))
        diff = abs(src_d - tgt_d)
        return CheckResult(
            "aggregate_check",
            diff <= tolerance,
            f"source={src_d}, target={tgt_d}, difference={diff}, tolerance={tolerance}",
            {"source": str(src_d), "target": str(tgt_d), "difference": str(diff)},
        )

    # --- row-level reconciliation --------------------------------------------------------------------
    def dataset_diff(
        self,
        source_sql: str,
        target_sql: str,
        source_key: str,
        target_key: str | None = None,
        transform: RowTransform | None = None,
        max_reported: int = 10,
        chunk_size: int = 1000,
        ignore_keys: Sequence[Any] = (),
    ) -> CheckResult:
        """Compare two result sets row by row.

        Both queries MUST return their key column (``source_key`` / ``target_key``; the target
        name defaults to the source name) and be ``ORDER BY`` that key ascending.
        ``transform`` maps a SOURCE row to the row expected in the TARGET (business rules).
        Only columns present in the transformed row are compared, so audit columns such as
        ``loaded_at`` can simply be left out. ``ignore_keys`` lists source keys that were
        legitimately rejected and so are expected to be absent from the target.

        Caveat for cross-engine comparisons: both databases must sort the key identically.
        Prefer numeric keys, or force a binary collation on text keys.
        """
        skip = set(ignore_keys)
        skey, tkey = source_key, target_key or source_key
        src_rows = self._source.stream(source_sql, chunk_size=chunk_size)
        tgt_rows = self._target.stream(target_sql, chunk_size=chunk_size)

        missing: list[Any] = []
        extra: list[Any] = []
        mismatched: list[dict[str, Any]] = []
        counts = {"missing": 0, "extra": 0, "mismatched": 0, "compared": 0}

        src = next(src_rows, None)
        tgt = next(tgt_rows, None)
        # Classic merge join: advance whichever side has the smaller key. Equal keys are compared.
        while src is not None or tgt is not None:
            if tgt is None or (src is not None and src[skey] < tgt[tkey]):
                if src[skey] not in skip:  # type: ignore[index]
                    counts["missing"] += 1
                    if len(missing) < max_reported:
                        missing.append(src[skey])  # type: ignore[index]
                src = next(src_rows, None)
            elif src is None or tgt[tkey] < src[skey]:
                counts["extra"] += 1
                if len(extra) < max_reported:
                    extra.append(tgt[tkey])
                tgt = next(tgt_rows, None)
            else:
                counts["compared"] += 1
                expected = transform(src) if transform else src
                differences = {
                    col: {"expected": exp, "actual": tgt.get(col)}
                    for col, exp in expected.items()
                    if not values_equal(exp, tgt.get(col))
                }
                if differences:
                    counts["mismatched"] += 1
                    if len(mismatched) < max_reported:
                        mismatched.append({skey: src[skey], "differences": differences})
                src = next(src_rows, None)
                tgt = next(tgt_rows, None)

        passed = not (counts["missing"] or counts["extra"] or counts["mismatched"])
        return CheckResult(
            "dataset_diff",
            passed,
            f"compared={counts['compared']}, missing_in_target={counts['missing']} {missing}, "
            f"extra_in_target={counts['extra']} {extra}, mismatched={counts['mismatched']} {mismatched}",
            {**counts, "missing_keys": missing, "extra_keys": extra, "mismatches": mismatched},
        )
