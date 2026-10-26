"""
Module  : framework.reporting.outputs
Author  : Anil Kalisetti
Purpose : The report types a user can choose between, as one small class each.

Two kinds of report exist:
    * PluginReport    - produced by a pytest plugin (pytest-html, JUnit, Allure). We only switch it
                        on by filling in that plugin's own command-line options before it starts.
    * GeneratedReport - produced by this framework after the run (executive summary, coverage).

Real-life example: a developer wants only ``html`` to look at locally; the build server wants
``junit,coverage`` for its dashboards; the release manager wants ``executive``. Same suite, same
command, one setting (``REPORTS`` / ``--reports``) - nothing is hard-wired in ``pyproject.toml``.

Adding a report type: subclass PluginReport (give it ``name``, ``probe`` and ``options``) or
GeneratedReport, add its name to ``REPORT_NAMES`` in settings.py. A unit test fails if they drift.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar

_MISSING = object()


class ReportOutput(ABC):
    """Base class; every concrete subclass with a ``name`` registers itself (open/closed)."""

    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    produces: ClassVar[str] = ""  # relative to the reports directory, for --list-reports
    _registry: ClassVar[dict[str, type[ReportOutput]]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.name:  # abstract intermediates leave ``name`` empty
            ReportOutput._registry[cls.name] = cls

    @classmethod
    def names(cls) -> tuple[str, ...]:
        return tuple(cls._registry)

    @classmethod
    def create(cls, name: str) -> ReportOutput:
        return cls._registry[name]()

    @abstractmethod
    def configure(self, option: Any, reports_dir: Path) -> bool:
        """Prepare this report. Return False when it cannot be produced (plugin not installed)."""


class PluginReport(ReportOutput):
    """A report written by a third-party pytest plugin, enabled through that plugin's options."""

    probe: ClassVar[str] = ""  # an option that only exists while the plugin is installed

    @abstractmethod
    def options(self, reports_dir: Path) -> dict[str, Any]:
        """Option name -> value that switches the plugin on."""

    def configure(self, option: Any, reports_dir: Path) -> bool:
        current = getattr(option, self.probe, _MISSING)
        if current is _MISSING:
            return False  # plugin not installed
        if current:
            return True  # the user passed the plugin's own flag; their choice wins
        for key, value in self.options(reports_dir).items():
            setattr(option, key, value)
        return True


class GeneratedReport(ReportOutput):
    """A report this framework writes itself at the end of the run (nothing to switch on early)."""

    def configure(self, option: Any, reports_dir: Path) -> bool:
        return True


class JUnitReport(PluginReport):
    name = "junit"
    description = "JUnit XML for CI dashboards (Jenkins, GitLab, Azure DevOps, GitHub)"
    produces = "junit.xml"
    probe = "xmlpath"

    def options(self, reports_dir: Path) -> dict[str, Any]:
        return {"xmlpath": str(reports_dir / "junit.xml")}


class HtmlReport(PluginReport):
    name = "html"
    description = "pytest-html: one self-contained HTML file with screenshots"
    produces = "report.html"
    probe = "htmlpath"

    def options(self, reports_dir: Path) -> dict[str, Any]:
        return {"htmlpath": str(reports_dir / "report.html"), "self_contained_html": True}


class AllureReport(PluginReport):
    name = "allure"
    description = "Allure results (open with the Allure CLI: make allure)"
    produces = "allure-results/"
    probe = "allure_report_dir"

    def options(self, reports_dir: Path) -> dict[str, Any]:
        return {"allure_report_dir": str(reports_dir / "allure-results"), "clean_alluredir": True}


class ExecutiveReport(GeneratedReport):
    name = "executive"
    description = "Management summary: GREEN/AMBER/RED verdict, by area/tag/browser (HTML, Markdown, JSON)"
    produces = "executive_summary.html, summary.md, summary.json"


class CoverageReport(GeneratedReport):
    name = "coverage"
    description = "Code coverage of framework/: terminal table, XML and HTML"
    produces = "coverage.xml, coverage-html/"


def apply_selection(selected: tuple[str, ...], option: Any, reports_dir: Path) -> tuple[list[str], list[str]]:
    """Configure every selected report; return (enabled, unavailable) names."""
    enabled: list[str] = []
    unavailable: list[str] = []
    for name in selected:
        (enabled if ReportOutput.create(name).configure(option, reports_dir) else unavailable).append(name)
    return enabled, unavailable


def describe_all() -> list[str]:
    """Lines for ``--list-reports``."""
    return [f"  {n:<10} {c.description}  [{c.produces}]" for n, c in ReportOutput._registry.items()]
