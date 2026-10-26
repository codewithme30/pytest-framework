"""
Module  : tests/unit/test_executive_report.py
Author  : Anil Kalisetti
Purpose : Verdict rules, wording and safety of the management summary.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.reporting.executive_report import render_html, render_markdown, write_reports
from framework.reporting.models import CaseResult, RunMetadata, RunSummary


def _results(passed: int = 0, failed: int = 0, layer: str = "api", **failed_kwargs) -> list[CaseResult]:
    ok = [CaseResult(f"tests/{layer}/t.py::ok_{i}", layer, "passed", 0.1) for i in range(passed)]
    bad = [CaseResult(f"tests/{layer}/t.py::bad_{i}", layer, "failed", 0.2, "boom", **failed_kwargs) for i in range(failed)]
    return ok + bad


def _summary(results: list[CaseResult], **kwargs) -> RunSummary:
    return RunSummary(RunMetadata(product="Shop", build_number="7", started_at="2026-10-26 10:00"), results, **kwargs)


@pytest.mark.parametrize(
    ("passed", "failed", "verdict"),
    [
        (100, 0, "GREEN"),
        (95, 5, "GREEN"),  # exactly at the green threshold
        (94, 6, "AMBER"),
        (80, 20, "AMBER"),  # exactly at the amber threshold
        (79, 21, "RED"),
        (0, 5, "RED"),
        (0, 0, "NO DATA"),
    ],
)
def test_verdict_thresholds(passed, failed, verdict):
    assert _summary(_results(passed, failed)).verdict == verdict


def test_one_failed_critical_test_forces_red_even_at_99_percent():
    results = _results(99, 0) + [CaseResult("tests/ui/t.py::pay", "ui", "failed", 1.0, "x", ("critical",))]
    summary = _summary(results)
    assert summary.pass_rate == 99.0
    assert summary.verdict == "RED"
    assert "critical" in summary.headline


def test_skipped_and_xfailed_do_not_change_pass_rate():
    results = _results(9, 1) + [
        CaseResult("t::s", "api", "skipped"),
        CaseResult("t::x", "api", "xfailed"),
    ]
    summary = _summary(results)
    assert summary.executed == 10
    assert summary.pass_rate == 90.0


def test_flaky_means_passed_after_rerun():
    flaky = CaseResult("t::f", "ui", "passed", reruns=2)
    steady = CaseResult("t::s", "ui", "passed")
    assert _summary([flaky, steady]).flaky == [flaky]


def test_headline_names_the_weakest_area():
    results = _results(10, 0, "api") + _results(5, 5, "ui")
    assert "ui" in _summary(results).headline


def test_custom_thresholds_are_respected():
    assert _summary(_results(70, 30), green_threshold=70.0, amber_threshold=60.0).verdict == "GREEN"


def test_html_escapes_untrusted_failure_text(tmp_path):
    hostile = CaseResult("tests/ui/t.py::x", "ui", "failed", 1.0, "<script>alert(1)</script>")
    html = render_html(_summary([hostile]), [], tmp_path)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_html_is_self_contained_and_shows_verdict(tmp_path):
    html = render_html(_summary(_results(10, 0)), [], tmp_path)
    assert "GREEN" in html
    assert "<link " not in html
    assert "src=\"http" not in html


def test_html_links_jira_defects_when_base_url_known(tmp_path):
    failing = CaseResult("tests/ui/t.py::x", "ui", "failed", 1.0, "m", jira_key="QA-142")
    summary = _summary([failing])
    summary.metadata.jira_base_url = "https://acme.atlassian.net"
    assert "https://acme.atlassian.net/browse/QA-142" in render_html(summary, [], tmp_path)


def test_trend_needs_two_points():
    summary = _summary(_results(1, 0))
    assert "after two or more runs" in render_html(summary, [{"pass_rate": 90}], Path("."))


def test_write_reports_creates_all_artifacts_and_rolls_history(tmp_path):
    summary = _summary(_results(9, 1))
    for _ in range(35):  # more runs than the history limit
        paths = write_reports(summary, tmp_path)
    assert {p.name for p in paths.values()} == {
        "executive_summary.html", "summary.md", "summary.json", "history.json",
    }  # fmt: skip
    assert len(json.loads(paths["history"].read_text())) == 30
    data = json.loads(paths["json"].read_text())
    assert data["verdict"] == "AMBER"  # 90% is below green (95) and above amber (80)
    assert data["failures"][0]["layer"] == "api"


def test_markdown_lists_failures_for_ci_job_summary():
    md = render_markdown(_summary(_results(1, 1)))
    assert "bad_0" in md
    assert "Pass rate" in md
