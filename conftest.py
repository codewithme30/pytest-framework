"""
Module  : conftest (repository root)
Author  : Anil Kalisetti
Purpose : Register framework plugins, auto-tag tests by layer, seed sample data, share fixtures.

Layer-specific fixtures live next to their tests (tests/ui/conftest.py, tests/api/conftest.py,
tests/data/conftest.py) so each layer stays independent and easy to lift into another project.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from framework.config.settings import Settings
from framework.core.parallel import current_db_url, worker_id, worker_log_path
from framework.plugins.stash import ensure_settings

pytest_plugins = [
    "framework.plugins.options",
    "framework.plugins.tags_plugin",
    "framework.plugins.report_selection_plugin",
    "framework.plugins.evidence_plugin",
    "framework.plugins.healing_plugin",
    "framework.plugins.jira_plugin",
    "framework.plugins.executive_report_plugin",
]

_LAYERS = ("ui", "api", "data", "db", "unit")


def pytest_configure(config: pytest.Config) -> None:
    settings = ensure_settings(config)
    settings.reports_path.mkdir(parents=True, exist_ok=True)
    _configure_worker_logging(settings.reports_path)

    # Every process (controller and each xdist worker) seeds ITS OWN database copy, so parallel
    # write-back tests never fight over one SQLite file. Non-SQLite URLs are left to the team.
    db_url = current_db_url(settings.db_url)
    if settings.seed_sample_db and db_url.startswith("sqlite"):
        # Local import: only runs when a database driver is actually needed.
        from framework.db.client import DatabaseClient
        from framework.db.sample_data import seed_sample_database

        db = DatabaseClient(db_url)
        seed_sample_database(db)
        db.dispose()


def _configure_worker_logging(reports_dir: Path) -> None:
    """One log file per process (recipe from the pytest-xdist docs); a shared file is clobbered."""
    log_file = worker_log_path(reports_dir, worker_id())
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_file,
        filemode="w",
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        force=True,
    )


def pytest_report_header(config: pytest.Config) -> list[str]:
    s = ensure_settings(config)
    return [
        f"pytest-framework | env={s.env} | mode={s.execution_mode} | browser={s.browser}"
        f" headless={s.headless} | build={s.build_name}"
    ]


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-apply the layer marker from the folder name so ``-m api`` always works."""
    for item in items:
        try:
            relative = Path(item.path).relative_to(config.rootpath).parts
        except ValueError:
            continue
        if len(relative) > 2 and relative[0] == "tests" and relative[1] in _LAYERS:
            item.add_marker(getattr(pytest.mark, relative[1]))


@pytest.fixture(scope="session")
def settings(request: pytest.FixtureRequest) -> Settings:
    """Active, validated configuration for this run."""
    return ensure_settings(request.config)
