"""
Module  : framework.plugins.report_selection_plugin
Author  : Anil Kalisetti
Purpose : Let the user choose which reports a run produces (``REPORTS`` / ``--reports``).

    pytest --reports html                    # only the pytest-html report
    pytest --reports allure,junit            # Allure results + JUnit XML
    REPORTS=executive,coverage pytest        # same, from the environment (CI friendly)
    pytest --reports none                    # no report files at all
    pytest --list-reports                    # show what exists

How it works: html / junit / allure are written by their own plugins, which read their options in
``pytest_configure``. This plugin runs first and fills in those options for the selected types only.
The executive summary and coverage are written by ExecutiveReportPlugin at the end of the run.
"""

from __future__ import annotations

import pytest

from framework.core.logger import get_logger
from framework.plugins.stash import ensure_settings
from framework.reporting.outputs import apply_selection, describe_all

log = get_logger("plugins.report_selection")
_STATUS: dict[int, tuple[list[str], list[str]]] = {}


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    if config.getoption("list_reports"):
        print("\n".join(["Report types (choose with --reports or REPORTS):", *describe_all()]))  # noqa: T201
        pytest.exit("report listing complete", returncode=0)
    settings = ensure_settings(config)
    settings.reports_path.mkdir(parents=True, exist_ok=True)
    # Idempotent, so xdist workers (which inherit the controller's options) can run it too.
    _STATUS[id(config)] = apply_selection(settings.selected_reports, config.option, settings.reports_path)


def pytest_report_header(config: pytest.Config) -> list[str]:
    enabled, unavailable = _STATUS.get(id(config), ([], []))
    line = f"reports: {', '.join(enabled) or 'none'}"
    if unavailable:
        line += f" (skipped, plugin not installed: {', '.join(unavailable)})"
    return [line]
