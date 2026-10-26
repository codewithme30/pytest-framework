"""
Module  : framework.plugins.evidence_plugin
Author  : Anil Kalisetti
Purpose : Capture failure evidence and tag every report with metadata for the main process.

Runs in every process (including xdist workers) because that is where the browser lives.
What it does for each test:
    * stores the setup/call/teardown reports on the item (``item.rep_call`` etc.) so fixtures
      can learn the verdict during teardown (used to mark cloud sessions passed/failed);
    * on failure with a ``driver`` fixture: saves a screenshot + page source, embeds the image
      in the pytest-html and Allure reports;
    * adds ``user_properties`` (markers, known defect, screenshot path) which pytest-xdist
      transports to the main process for the executive report and Jira plugin.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from framework.core.logger import get_logger
from framework.plugins.stash import ensure_settings

log = get_logger("plugins.evidence")

_BUILTIN_MARKERS = frozenset(
    {"parametrize", "usefixtures", "skip", "skipif", "xfail", "filterwarnings", "flaky"}
)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):  # type: ignore[type-arg]
    outcome = yield
    report: pytest.TestReport = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)
    settings = ensure_settings(item.config)

    if report.when == "setup":
        names = sorted({m.name for m in item.iter_markers()} - _BUILTIN_MARKERS)
        report.user_properties.append(("markers", ",".join(names)))
        known = item.get_closest_marker("known_defect")
        if known and known.args:
            report.user_properties.append(("known_defect", str(known.args[0])))

    driver = getattr(item, "funcargs", {}).get("driver")
    if driver is None or report.when not in ("setup", "call"):
        return

    expected_failure = hasattr(report, "wasxfail")
    want = (settings.screenshot_policy == "always" and report.when == "call") or (
        settings.screenshot_policy == "on_failure" and report.failed and not expected_failure
    )
    if not want:
        return

    from framework.ui.screenshot import capture_evidence  # lazy: selenium only needed for UI runs

    path = capture_evidence(driver, settings.reports_path / "screenshots", item.nodeid)
    if path is not None:
        report.user_properties.append(("screenshot", str(path)))
        _attach(report, path)


def _attach(report: pytest.TestReport, path: Path) -> None:
    data = path.read_bytes()
    try:
        import allure

        allure.attach(data, name="screenshot", attachment_type=allure.attachment_type.PNG)
    except Exception as exc:  # noqa: BLE001 - evidence must never break reporting
        log.debug("Allure attach skipped: %s", exc)
    try:
        from pytest_html import extras

        existing = getattr(report, "extras", [])
        existing.append(extras.png(base64.b64encode(data).decode("ascii")))
        report.extras = existing
    except ImportError:  # pragma: no cover
        pass
