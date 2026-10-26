"""
Module  : framework.plugins.healing_plugin
Author  : Anil Kalisetti
Purpose : Controller-side handling of self-healing: audit file, terminal notice, record mode
          and the optional ``--fail-on-heal`` release gate.

Main process only (workers just forward ``user_properties``). Outputs
    reports/locator_healing.json     every heal: locator, old -> new selector, score, page
    config/locator_fingerprints.json updated only when --record-locators is used
"""

from __future__ import annotations

import json

import pytest

from framework.config.settings import Settings
from framework.core.logger import get_logger
from framework.plugins.stash import ensure_settings
from framework.ui.healing.fingerprint import ElementFingerprint
from framework.ui.healing.healer import HealEvent
from framework.ui.healing.store import FingerprintStore
from framework.ui.healing.transport import parse_fingerprints, parse_heals

log = get_logger("plugins.healing")


def pytest_configure(config: pytest.Config) -> None:
    if hasattr(config, "workerinput"):  # xdist worker
        return
    config.pluginmanager.register(HealingCollector(ensure_settings(config)), "fw-healing")


class HealingCollector:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.heals: dict[str, list[HealEvent]] = {}  # nodeid -> events
        self.fingerprints: dict[str, ElementFingerprint] = {}

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        events = parse_heals(report.user_properties)
        if events:
            self.heals[report.nodeid] = events
        self.fingerprints.update(parse_fingerprints(report.user_properties))

    def pytest_terminal_summary(self, terminalreporter: pytest.TerminalReporter) -> None:
        if not self.heals:
            return
        terminalreporter.section("self-healing locators (review and fix the selectors)")
        for nodeid, events in self.heals.items():
            for e in events:
                score = "" if e.score is None else f" score={e.score:.2f}"
                terminalreporter.write_line(f"{e.locator}: {e.original} -> {e.healed} [{e.strategy}{score}]  ({nodeid})")

    def pytest_sessionfinish(self, session: pytest.Session) -> None:
        reports_dir = self._settings.reports_path
        if self.heals:
            reports_dir.mkdir(parents=True, exist_ok=True)
            payload = {nodeid: [e.to_dict() for e in events] for nodeid, events in self.heals.items()}
            (reports_dir / "locator_healing.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")

        if self._settings.record_locators and self.fingerprints:
            store = FingerprintStore.load(self._settings.locator_baseline_path)
            store.merge(self.fingerprints)
            store.save()
            log.info("Recorded %d locator fingerprints into %s", len(self.fingerprints), self._settings.locator_baseline_path)

        if self._settings.fail_on_heal and self.heals and session.exitstatus == pytest.ExitCode.OK:
            log.error("--fail-on-heal: %d test(s) needed healed locators", len(self.heals))
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
