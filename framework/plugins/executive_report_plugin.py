"""
Module  : framework.plugins.executive_report_plugin
Author  : Anil Kalisetti
Purpose : Collect every test outcome and publish the management summary after the run.

Main process only. Reports are generated in ``pytest_terminal_summary`` (as late as
possible) so that pytest-cov has already written ``coverage.xml`` and the Jira plugin has
already created its defects, letting the summary show both coverage and defect links.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import pytest

from framework.config.settings import Settings
from framework.core.ci_info import detect_build_info
from framework.core.logger import get_logger
from framework.plugins.jira_plugin import PLUGIN_NAME as JIRA_PLUGIN_NAME
from framework.plugins.stash import ensure_settings
from framework.reporting.executive_report import write_reports
from framework.reporting.models import CaseResult, RunMetadata, RunSummary

log = get_logger("plugins.executive")


def pytest_configure(config: pytest.Config) -> None:
    if hasattr(config, "workerinput"):  # xdist worker
        return
    config.pluginmanager.register(
        ExecutiveReportPlugin(ensure_settings(config)), "fw-executive-report"
    )


def _layer_of(nodeid: str) -> str:
    """tests/api/test_posts.py::test_x -> 'api' (first folder under tests/)."""
    parts = nodeid.split("::", 1)[0].split("/")
    return parts[1] if len(parts) > 2 and parts[0] == "tests" else "other"


def _short_message(report: pytest.TestReport) -> str:
    longrepr = report.longrepr
    if isinstance(longrepr, tuple):  # skip reports: (path, lineno, reason)
        text = str(longrepr[2])
    else:
        crash = getattr(longrepr, "reprcrash", None)
        text = crash.message if crash else str(longrepr or "")
    return " ".join(text.split())[:300]


def read_coverage_percent(path: Path, newer_than: float) -> float | None:
    """Line coverage from Cobertura XML, ignoring a stale file left by a previous run."""
    try:
        if path.stat().st_mtime < newer_than:
            return None
        return float(ET.parse(path).getroot().attrib["line-rate"]) * 100  # noqa: S314 - own file
    except (OSError, ET.ParseError, KeyError, ValueError):
        return None


class ExecutiveReportPlugin:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._records: dict[str, CaseResult] = {}
        self._reruns: dict[str, int] = {}
        self._started = time.time()
        self._started_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        nodeid = report.nodeid
        if report.outcome == "rerun":  # pytest-rerunfailures: an attempt that will be retried
            self._reruns[nodeid] = self._reruns.get(nodeid, 0) + 1
            return

        props = dict(report.user_properties)
        if report.when == "setup":
            self._records[nodeid] = CaseResult(
                nodeid,
                _layer_of(nodeid),
                "passed",
                markers=tuple(filter(None, props.get("markers", "").split(","))),
            )
        record = self._records.setdefault(nodeid, CaseResult(nodeid, _layer_of(nodeid), "passed"))
        record.duration += report.duration
        if props.get("screenshot"):
            record.screenshot = props["screenshot"]

        if report.when == "setup" and not report.passed:
            record.outcome = "skipped" if report.skipped else "error"
            record.message = _short_message(report)
        elif report.when == "call":
            if hasattr(report, "wasxfail"):
                record.outcome = "xpassed" if report.passed else "xfailed"
            else:
                record.outcome = report.outcome  # passed | failed | skipped
            if not report.passed:
                record.message = _short_message(report)
        elif report.when == "teardown" and report.failed and record.outcome == "passed":
            record.outcome, record.message = "error", _short_message(report)

    @pytest.hookimpl(trylast=True)
    def pytest_terminal_summary(
        self, terminalreporter: pytest.TerminalReporter, config: pytest.Config
    ) -> None:
        jira = config.pluginmanager.get_plugin(JIRA_PLUGIN_NAME)
        for nodeid, record in self._records.items():
            record.reruns = self._reruns.get(nodeid, 0)
            if jira is not None:
                record.jira_key = jira.created.get(nodeid, "")

        s, build = self.settings, detect_build_info()
        metadata = RunMetadata(
            product=s.product_name,
            environment=s.env,
            provider=build.provider,
            build_number=build.build_number,
            branch=build.branch,
            commit=build.commit,
            build_url=build.build_url,
            execution_mode=s.execution_mode,
            browser=s.browser,
            started_at=self._started_at,
            duration_seconds=time.time() - self._started,
            jira_base_url=s.jira_base_url,
        )
        summary = RunSummary(
            metadata,
            list(self._records.values()),
            s.pass_rate_green,
            s.pass_rate_amber,
            read_coverage_percent(s.reports_path / "coverage.xml", self._started),
        )
        paths = write_reports(summary, s.reports_path)
        terminalreporter.write_sep("=", "Executive summary")
        terminalreporter.write_line(f"{summary.verdict}: {summary.headline}")
        terminalreporter.write_line(f"HTML summary: {paths['html']}")
