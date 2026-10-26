"""
Module  : tests/unit/test_report_selection.py
Author  : Anil Kalisetti
Purpose : The user picks which reports a run produces; only those are switched on.

Real-life example: the build server runs ``REPORTS=junit,coverage`` and must not pay for (or
publish) an Allure folder nobody reads; a developer runs ``--reports html`` and gets just that.
"""

from __future__ import annotations

import sys
import time
import types
from argparse import Namespace
from pathlib import Path

import pytest

from framework.config.settings import REPORT_NAMES, Settings, load_settings, parse_report_selection
from framework.core.exceptions import ConfigurationError
from framework.reporting.coverage_report import CoverageReporter
from framework.reporting.outputs import ReportOutput, apply_selection, describe_all

pytestmark = pytest.mark.unit


def _all_plugins_installed() -> Namespace:
    """Options as they look when pytest-html, JUnit and allure-pytest are installed and unused."""
    return Namespace(xmlpath=None, htmlpath=None, self_contained_html=False,
                     allure_report_dir=None, clean_alluredir=False)


# --- parsing -------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("all", REPORT_NAMES),
        ("", REPORT_NAMES),
        ("html", ("html",)),
        (" HTML , Allure ", ("html", "allure")),
        ("junit,junit,coverage", ("junit", "coverage")),
        ("none", ()),
    ],
)
def test_parse_report_selection(text, expected):
    assert parse_report_selection(text) == expected


@pytest.mark.parametrize("text", ["alure", "html,pdf", "none,html"])
def test_bad_selection_is_rejected_loudly(text):
    with pytest.raises(ConfigurationError):
        parse_report_selection(text)


def test_settings_validate_reports_and_expose_helpers():
    settings = Settings(reports="junit,coverage")
    assert settings.selected_reports == ("junit", "coverage")
    assert settings.wants_report("junit") and not settings.wants_report("html")
    with pytest.raises(ConfigurationError):
        Settings(reports="alure")


def test_reports_come_from_environment_and_cli_override_wins():
    assert load_settings(environ={"REPORTS": "html"}).selected_reports == ("html",)
    assert load_settings({"reports": "allure"}, environ={"REPORTS": "html"}).selected_reports == ("allure",)


def test_default_keeps_every_report_so_existing_pipelines_are_unchanged():
    assert Settings().selected_reports == REPORT_NAMES


# --- class hierarchy -----------------------------------------------------------------------------
def test_registry_matches_the_names_settings_accept():
    assert set(ReportOutput.names()) == set(REPORT_NAMES)  # fails if one is added without the other


def test_every_report_type_is_described_for_list_reports():
    text = "\n".join(describe_all())
    assert all(name in text for name in REPORT_NAMES)


# --- switching plugins on ------------------------------------------------------------------------
def test_only_selected_plugin_reports_are_switched_on(tmp_path):
    option = _all_plugins_installed()
    enabled, unavailable = apply_selection(("html",), option, tmp_path)
    assert (enabled, unavailable) == (["html"], [])
    assert option.htmlpath == str(tmp_path / "report.html") and option.self_contained_html is True
    assert option.xmlpath is None and option.allure_report_dir is None  # not selected -> untouched


def test_each_plugin_report_sets_its_own_options(tmp_path):
    option = _all_plugins_installed()
    apply_selection(("junit", "allure"), option, tmp_path)
    assert option.xmlpath == str(tmp_path / "junit.xml")
    assert option.allure_report_dir == str(tmp_path / "allure-results") and option.clean_alluredir is True
    assert option.htmlpath is None


def test_missing_plugin_is_reported_not_crashed(tmp_path):
    option = Namespace(xmlpath=None)  # pytest-html and allure-pytest not installed
    enabled, unavailable = apply_selection(("junit", "html", "allure"), option, tmp_path)
    assert enabled == ["junit"] and unavailable == ["html", "allure"]


def test_a_flag_the_user_typed_themselves_is_not_overridden(tmp_path):
    option = _all_plugins_installed()
    option.htmlpath = "custom/mine.html"
    apply_selection(("html",), option, tmp_path)
    assert option.htmlpath == "custom/mine.html"


def test_generated_reports_need_no_plugin_options(tmp_path):
    option = Namespace()
    assert apply_selection(("executive", "coverage"), option, tmp_path) == (["executive", "coverage"], [])
    assert vars(option) == {}


def test_none_selects_nothing(tmp_path):
    option = _all_plugins_installed()
    before = vars(option).copy()
    assert apply_selection((), option, tmp_path) == ([], [])
    assert vars(option) == before


# --- coverage outputs ----------------------------------------------------------------------------
class _FakeCoverage:
    """Stands in for ``coverage.Coverage`` so the logic is tested without tracing anything."""

    data_file = ""
    calls: list[str] = []

    def __init__(self, config_file=True):
        self.config = types.SimpleNamespace(data_file=_FakeCoverage.data_file)

    def load(self):
        _FakeCoverage.calls.append("load")

    def report(self, file, show_missing=False, skip_covered=False):
        file.write("Name  Stmts  Miss  Cover\nTOTAL    10     1    90%\n")
        return 90.0

    def xml_report(self, outfile):
        Path(outfile).write_text("<xml/>")

    def html_report(self, directory):
        Path(directory).mkdir(parents=True, exist_ok=True)


@pytest.fixture
def fake_coverage(tmp_path, monkeypatch):
    data = tmp_path / ".coverage"
    data.write_text("data")
    _FakeCoverage.data_file, _FakeCoverage.calls = str(data), []
    module = types.ModuleType("coverage")
    module.Coverage, module.CoverageException = _FakeCoverage, type("CoverageException", (Exception,), {})
    monkeypatch.setitem(sys.modules, "coverage", module)
    return data


def test_publish_writes_table_xml_and_html(tmp_path, fake_coverage):
    lines: list[str] = []
    total = CoverageReporter(tmp_path, newer_than=0).publish(lines.append)
    assert total == 90.0 and any("TOTAL" in line for line in lines)
    assert (tmp_path / "coverage.xml").exists() and (tmp_path / "coverage-html").is_dir()


def test_percent_alone_writes_nothing(tmp_path, fake_coverage):
    assert CoverageReporter(tmp_path, newer_than=0).percent() == 90.0
    assert not (tmp_path / "coverage.xml").exists()


def test_stale_coverage_data_from_an_earlier_run_is_ignored(tmp_path, fake_coverage):
    assert CoverageReporter(tmp_path, newer_than=time.time() + 60).percent() is None


def test_missing_coverage_data_is_reported_calmly(tmp_path, fake_coverage):
    fake_coverage.unlink()
    lines: list[str] = []
    assert CoverageReporter(tmp_path, newer_than=0).publish(lines.append) is None
    assert "no data collected" in lines[0]


def test_coverage_not_installed_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "coverage", None)  # makes `import coverage` raise ImportError
    assert CoverageReporter(tmp_path, newer_than=0).percent() is None
