"""
Module  : framework.core.parallel
Author  : Anil Kalisetti
Purpose : Helpers that keep parallel runs (pytest-xdist ``-n``) from stepping on each other.

Shared mutable resources are the usual cause of "passes alone, fails in parallel":
    * one SQLite file that every worker writes to        -> one file per worker
    * one log file opened by every worker                -> one log file per worker
Real-life example: two testers running the same regression at once against one shared
spreadsheet would overwrite each other's results; each gets their own copy.

All functions are pure (environment passed in) so they are trivial to unit test.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

MAIN_PROCESS = "main"
_SQLITE_PREFIX = "sqlite:///"


def worker_id(environ: Mapping[str, str] | None = None) -> str:
    """xdist worker name (``gw0``, ``gw1``...) or ``main`` when not running in parallel."""
    env = os.environ if environ is None else environ
    return env.get("PYTEST_XDIST_WORKER", MAIN_PROCESS)


def worker_db_url(db_url: str, worker: str) -> str:
    """Give each xdist worker its own SQLite file; leave every other database untouched.

    sqlite:///reports/sample.db  + gw1  ->  sqlite:///reports/sample_gw1.db
    sqlite://  (in memory)              ->  unchanged (already private to the process)
    postgresql://...                    ->  unchanged (shared server: partition your test data instead)

    TODO(future): for a shared server database (Postgres, Oracle) give each worker its own
    schema or a slice of the test-data table, e.g. ``WHERE MOD(id, :workers) = :worker_index``.
    """
    if worker == MAIN_PROCESS or not db_url.startswith(_SQLITE_PREFIX):
        return db_url
    path = db_url[len(_SQLITE_PREFIX) :]
    if path in ("", ":memory:") or path.startswith("file:"):
        return db_url
    root, extension = os.path.splitext(path)
    return f"{_SQLITE_PREFIX}{root}_{worker}{extension}"


def current_db_url(db_url: str) -> str:
    """``db_url`` adjusted for the process we are in (controller or one xdist worker)."""
    return worker_db_url(db_url, worker_id())


def worker_log_path(reports_dir: Path, worker: str) -> Path:
    """Per-worker log file so parallel workers never overwrite each other's log."""
    return reports_dir / "logs" / f"pytest-{worker}.log"
