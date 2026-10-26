"""
Module  : framework.plugins.options
Author  : Anil Kalisetti
Purpose : Command-line flags that override configuration for a single run.

Examples
    pytest -m smoke --ui-browser firefox --headed
    pytest -m ui --execution-mode saucelabs --build-name release-24.3
    pytest --test-env staging --raise-jira-defects
    pytest --ui-browsers chrome,firefox -m ui       # every UI test once per browser
    pytest --tags "smoke or uat" -n auto            # group by tag, run in parallel
"""

from __future__ import annotations

import pytest

from framework.config.settings import BROWSERS, EXECUTION_MODES, SCREENSHOT_POLICIES


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("framework", "pytest-framework options")
    group.addoption("--test-env", default=None, help="Environment file to load (qa, staging, ...)")
    group.addoption("--ui-browser", default=None, choices=BROWSERS, help="Browser for UI tests")
    group.addoption(
        "--ui-browsers",
        default=None,
        help="Comma separated browsers to run every UI test on (chrome,firefox,edge,safari) or 'all'",
    )
    group.addoption(
        "--tags",
        default=None,
        help="Marker expression, validated against registered markers, e.g. 'smoke or uat'",
    )
    group.addoption(
        "--list-tags", action="store_true", default=False, help="Show how many tests carry each tag, then exit"
    )
    group.addoption("--headed", action="store_true", default=False, help="Show the browser window")
    group.addoption(
        "--execution-mode",
        default=None,
        choices=EXECUTION_MODES,
        help="Where UI tests run: local, remote grid, or a cloud provider",
    )
    group.addoption("--grid-url", default=None, help="Selenium Grid / cloud hub URL override")
    group.addoption("--build-name", default=None, help="Build label shown in cloud dashboards")
    group.addoption(
        "--screenshots", default=None, choices=SCREENSHOT_POLICIES, help="Screenshot capture policy"
    )
    group.addoption(
        "--raise-jira-defects",
        action="store_true",
        default=False,
        help="Create (or update) a Jira bug for each failed test",
    )
    group.addoption(
        "--jira-max-defects",
        type=int,
        default=25,
        help="Safety cap on NEW Jira bugs per run (protects against environment outages)",
    )
