"""
Module  : framework.reporting.coverage_report
Author  : Anil Kalisetti
Purpose : Turn the coverage data collected during the run into the outputs the user selected.

pytest-cov must start tracing before plugins load, so it stays on in ``pyproject.toml`` and only
*collects* (``--cov-report=`` prints nothing). This class then reads the collected data and writes
the terminal table / XML / HTML - but only when ``coverage`` was selected in ``REPORTS``.
To skip tracing entirely (fastest run, e.g. in a debugger) pass pytest-cov's own ``--no-cov``.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from pathlib import Path
from typing import Any

from framework.core.logger import get_logger

log = get_logger("reporting.coverage")


class CoverageReporter:
    def __init__(self, reports_dir: Path, newer_than: float) -> None:
        self._reports_dir = reports_dir
        self._newer_than = newer_than  # ignore a data file left behind by an earlier run

    def percent(self) -> float | None:
        """Total line coverage, or None when no fresh data exists (e.g. --no-cov)."""
        cov = self._load()
        return None if cov is None else self._total(cov, io.StringIO())

    def publish(self, write_line: Callable[[str], Any]) -> float | None:
        """Write terminal table, XML and HTML; return the total percentage."""
        cov = self._load()
        if cov is None:
            write_line("coverage: no data collected (was the run started with --no-cov?)")
            return None
        table = io.StringIO()
        total = self._total(cov, table, show_missing=True, skip_covered=True)
        for line in table.getvalue().splitlines():
            write_line(line)
        for label, call in (
            ("XML", lambda: cov.xml_report(outfile=str(self._reports_dir / "coverage.xml"))),
            ("HTML", lambda: cov.html_report(directory=str(self._reports_dir / "coverage-html"))),
        ):
            try:
                call()
            except Exception as exc:  # noqa: BLE001 - a broken report must not fail the test run
                log.warning("coverage %s report failed: %s", label, exc)
        return total

    # --- internals ----------------------------------------------------------------
    def _load(self) -> Any | None:
        try:
            import coverage  # local import: coverage is optional at runtime
        except ImportError:
            return None
        cov = coverage.Coverage(config_file=True)
        try:
            if Path(cov.config.data_file).stat().st_mtime < self._newer_than:
                return None
            cov.load()
        except (OSError, coverage.CoverageException):
            return None
        return cov

    @staticmethod
    def _total(cov: Any, sink: io.StringIO, **kwargs: Any) -> float | None:
        try:
            return float(cov.report(file=sink, **kwargs))
        except Exception:  # noqa: BLE001 - "no data" and similar must not break the summary
            return None
