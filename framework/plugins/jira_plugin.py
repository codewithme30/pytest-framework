"""
Module  : framework.plugins.jira_plugin
Author  : Anil Kalisetti
Purpose : Raise one Jira bug per failed test at the end of the run (main process only).

Modes
    off       default; nothing is sent anywhere
    dry-run   Jira enabled but credentials missing -> writes ``jira_defects_preview.json``
              so engineers can review exactly what WOULD be created
    live      enabled + credentials present -> creates bugs, or comments on an open duplicate

Enable with ``--raise-jira-defects`` or ``JIRA_ENABLED=true``. Failures that are already
tracked can be annotated ``@pytest.mark.known_defect("QA-123")`` so no new bug is created.

Safety rails: a cap on new bugs per run (``--jira-max-defects``) so an environment outage that
fails 400 tests does not flood the backlog, and Jira errors never change the pytest exit code.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pytest

from framework.config.settings import Settings
from framework.core.ci_info import detect_build_info
from framework.core.exceptions import IntegrationError
from framework.core.logger import get_logger
from framework.integrations.jira_client import JiraClient, fingerprint
from framework.plugins.stash import ensure_settings

log = get_logger("plugins.jira")
PLUGIN_NAME = "fw-jira"
_TRACE_LIMIT = 3_000


@dataclass
class FailureInfo:
    nodeid: str
    message: str
    trace: str
    screenshot: str = ""
    known_defect: str = ""


def pytest_configure(config: pytest.Config) -> None:
    if hasattr(config, "workerinput"):  # xdist worker: the main process owns Jira
        return
    settings = ensure_settings(config)
    enabled = config.getoption("raise_jira_defects") or settings.jira_enabled
    config.pluginmanager.register(
        JiraDefectPlugin(settings, enabled, config.getoption("jira_max_defects")), PLUGIN_NAME
    )


class JiraDefectPlugin:
    def __init__(self, settings: Settings, enabled: bool, max_new: int) -> None:
        self.settings = settings
        self.enabled = enabled
        self.max_new = max_new
        self.created: dict[str, str] = {}  # nodeid -> Jira key (read by the executive report)
        self._failures: dict[str, FailureInfo] = {}
        self._known: dict[str, str] = {}  # nodeid -> Jira key from @pytest.mark.known_defect

    # --- collect ------------------------------------------------------------------------
    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.when not in ("setup", "call") or hasattr(report, "wasxfail"):
            return
        props = dict(report.user_properties)
        if "known_defect" in props:  # arrives on the setup report, before any call failure
            self._known[report.nodeid] = props["known_defect"]
        if report.failed:
            crash = getattr(report.longrepr, "reprcrash", None)
            message = crash.message if crash else str(report.longrepr)
            self._failures[report.nodeid] = FailureInfo(
                report.nodeid,
                " ".join(message.split())[:300],
                report.longreprtext[-_TRACE_LIMIT:],
                props.get("screenshot", ""),
                self._known.get(report.nodeid, ""),
            )

    # --- act ------------------------------------------------------------------------------------
    def pytest_sessionfinish(self, session: pytest.Session) -> None:
        if not self.enabled or not self._failures:
            return
        if not self.settings.jira_configured:
            self._write_preview()
            return
        self._file_defects()

    def _description(self, f: FailureInfo) -> list[str]:
        build = detect_build_info()
        return [
            f"Automated test failed: {f.nodeid}",
            f"Environment: {self.settings.env} | Execution: {self.settings.execution_mode}"
            f" | Browser: {self.settings.browser}",
            f"Build: {build.provider} #{build.build_number} {build.branch} {build.commit}",
            f"Build URL: {build.build_url or 'n/a'}",
            f"Failure: {f.message}",
            "Stack trace (tail):",
            f.trace,
        ]

    def _write_preview(self) -> None:
        path = self.settings.reports_path / "jira_defects_preview.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {**asdict(f), "label": fingerprint(f.nodeid), "would_create": not f.known_defect}
            for f in self._failures.values()
        ]
        path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        log.warning("Jira credentials not configured; dry-run preview written to %s", path)

    def _file_defects(self) -> None:
        s = self.settings
        client = JiraClient(
            s.jira_base_url, s.jira_user_email, s.jira_api_token, s.jira_project_key, s.jira_issue_type
        )
        base_labels = [label.strip() for label in s.jira_labels.split(",") if label.strip()]
        new_count = 0
        for nodeid, f in self._failures.items():
            if f.known_defect:
                self.created[nodeid] = f.known_defect
                continue
            label = fingerprint(nodeid)
            try:
                existing = client.find_open_defect(label)
                if existing:
                    client.add_comment(existing, ["Failed again.", *self._description(f)[:5]])
                    self.created[nodeid] = existing
                    continue
                if new_count >= self.max_new:
                    log.warning("Jira cap of %d new defects reached; skipping %s", self.max_new, nodeid)
                    continue
                key = client.create_defect(
                    summary=f"[Auto] {nodeid.rsplit('::', 1)[-1]} failed on {s.env}",
                    description_lines=self._description(f),
                    labels=[*base_labels, label],
                )
                new_count += 1
                self.created[nodeid] = key
                if f.screenshot and Path(f.screenshot).exists():
                    client.attach_file(key, Path(f.screenshot))
            except IntegrationError as exc:
                log.error("Jira update failed for %s: %s", nodeid, exc)
